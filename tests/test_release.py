import gzip
import hashlib
import json
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_release import (  # noqa: E402
    PACKAGE_ID,
    build_release,
    validate_legacy_path,
)

PACKAGE_ROOT = ROOT / "Packages" / PACKAGE_ID
VERSION = json.loads((PACKAGE_ROOT / "package.json").read_text(encoding="utf-8"))["version"]
LEGACY_FIXTURE = ROOT / "tests" / "fixtures" / "legacy-guids.json"
META_GUID = re.compile(rb"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)


class ReleaseBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="milfy-eat-ear-release-")
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)

    def copy_repo_fixture(self) -> Path:
        target = Path(tempfile.mkdtemp(prefix="repo-", dir=self.temp_root))
        shutil.copytree(ROOT / "Packages", target / "Packages")
        shutil.copytree(ROOT / "tests" / "fixtures", target / "tests" / "fixtures")
        return target

    def test_vpm_zip_and_legacy_unitypackage_preserve_original_guids(self):
        artifacts = build_release(ROOT, VERSION, self.temp_root / "out")
        zip_path = artifacts["vpm_zip"]
        with zipfile.ZipFile(zip_path) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            expected_names = {
                "package.json", "README.md", "README.md.meta",
                "CHANGELOG.md", "CHANGELOG.md.meta", "Runtime.meta",
            }
            expected_names.update(
                path.relative_to(PACKAGE_ROOT).as_posix()
                for path in (PACKAGE_ROOT / "Runtime").rglob("*")
                if path.is_file()
            )
            self.assertEqual(names, expected_names)
            self.assertIn("package.json", names)
            self.assertNotIn("package.json.meta", names)
            self.assertFalse(any(name.startswith("Packages/") for name in names))
            self.assertFalse(any("ValidationProject~" in name or name.endswith(".py") for name in names))
            manifest = json.loads(archive.read("package.json"))
            self.assertEqual(manifest["name"], PACKAGE_ID)
            self.assertEqual(manifest["version"], VERSION)
            self.assertEqual(manifest["legacyFolders"], {
                r"Assets\SaiEatEar": "e1004d0dadfdc504e87428a6254d3325",
                r"Assets\sai\SaiEatEar": "e1004d0dadfdc504e87428a6254d3325",
            })

        unitypackage_path = artifacts["unitypackage"]
        with gzip.open(unitypackage_path, "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r:") as archive:
                members = archive.getmembers()
                self.assertTrue(members)
                self.assertEqual(len(members) % 3, 0)
                archive_names = {member.name for member in members}
                actual = {}
                for member in members:
                    self.assertEqual(len(Path(member.name).parts), 2)
                    guid, kind = member.name.split("/", 1)
                    self.assertRegex(guid, r"^[0-9a-f]{32}$")
                    self.assertIn(kind, {"asset", "asset.meta", "pathname"})
                    if kind == "pathname":
                        pathname = archive.extractfile(member).read().decode("utf-8")
                        self.assertEqual(validate_legacy_path(pathname), pathname)
                        self.assertNotIn(pathname, actual)
                        actual[pathname] = guid
                        meta_bytes = archive.extractfile(f"{guid}/asset.meta").read()
                        found = META_GUID.findall(meta_bytes)
                        self.assertEqual(found, [guid.encode("ascii")])
                        asset = archive.getmember(f"{guid}/asset")
                        self.assertEqual(asset.isdir(), pathname in {
                            "Assets/SaiEatEar",
                            "Assets/SaiEatEar/Animation",
                            "Assets/SaiEatEar/FBX",
                        })
                self.assertEqual(len(archive_names), 3 * len(actual))
                old = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
                expected = old.copy()
                expected["Assets/SaiEatEar/README.md"] = self.meta_guid(PACKAGE_ROOT / "README.md.meta")
                expected["Assets/SaiEatEar/CHANGELOG.md"] = self.meta_guid(PACKAGE_ROOT / "CHANGELOG.md.meta")
                self.assertEqual(actual, expected)
                prefab_path = "Assets/SaiEatEar/EatEar.prefab"
                prefab_guid = actual[prefab_path]
                prefab_asset = archive.extractfile(f"{prefab_guid}/asset").read()
                self.assertEqual(prefab_asset, (PACKAGE_ROOT / "Runtime" / "EatEar.prefab").read_bytes())
                self.assertEqual(archive.extractfile(f"{prefab_guid}/asset.meta").read(), (PACKAGE_ROOT / "Runtime" / "EatEar.prefab.meta").read_bytes())
                self.assertTrue(all(name.split("/", 1)[0] in actual.values() for name in archive_names))

        sums = self.parse_sums(artifacts["checksums"])
        self.assertEqual(set(sums), {zip_path.name, unitypackage_path.name})
        for name, digest in sums.items():
            artifact = artifacts["vpm_zip"] if name == zip_path.name else unitypackage_path
            self.assertEqual(self.sha256(artifact), digest)

    def test_compat_controller_is_shipped_with_its_original_guid_and_closed_reference(self):
        artifacts = build_release(ROOT, VERSION, self.temp_root / "compat-controller")
        legacy_path = "Assets/SaiEatEar/Animation/Milfy_250326a.controller"
        fixture = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
        controller_guid = fixture[legacy_path]
        controller = PACKAGE_ROOT / "Runtime" / "Animation" / "Milfy_250326a.controller"
        controller_meta = Path(f"{controller}.meta")
        controller_bytes = controller.read_bytes()
        expected_animation_guid = fixture[
            "Assets/SaiEatEar/Animation/EnableParticle_L.anim"
        ]
        references = {
            guid.decode("ascii").lower()
            for guid in re.findall(rb"\bguid:\s*([0-9a-fA-F]{32})\b", controller_bytes)
        }
        self.assertEqual(references, {expected_animation_guid})

        with zipfile.ZipFile(artifacts["vpm_zip"]) as archive:
            self.assertEqual(
                archive.read("Runtime/Animation/Milfy_250326a.controller"),
                controller_bytes,
            )
            controller_meta_bytes = archive.read(
                "Runtime/Animation/Milfy_250326a.controller.meta"
            )
            self.assertEqual(controller_meta_bytes, controller_meta.read_bytes())
            self.assertEqual(
                META_GUID.findall(controller_meta_bytes),
                [controller_guid.encode("ascii")],
            )
            animation_meta = archive.read(
                "Runtime/Animation/EnableParticle_L.anim.meta"
            )
            self.assertEqual(
                META_GUID.findall(animation_meta),
                [expected_animation_guid.encode("ascii")],
            )

        with gzip.open(artifacts["unitypackage"], "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r:") as archive:
                pathname_to_guid = {
                    archive.extractfile(member).read().decode("utf-8"): member.name.split("/", 1)[0]
                    for member in archive.getmembers()
                    if member.name.endswith("/pathname")
                }
                self.assertEqual(pathname_to_guid[legacy_path], controller_guid)
                self.assertEqual(
                    archive.extractfile(f"{controller_guid}/asset").read(),
                    controller_bytes,
                )
                self.assertEqual(
                    archive.extractfile(f"{controller_guid}/asset.meta").read(),
                    controller_meta.read_bytes(),
                )
                self.assertEqual(
                    pathname_to_guid[
                        "Assets/SaiEatEar/Animation/EnableParticle_L.anim"
                    ],
                    expected_animation_guid,
                )
                self.assertTrue(references.issubset(set(pathname_to_guid.values())))

    def test_build_is_byte_reproducible_and_checksums_match(self):
        first = build_release(ROOT, VERSION, self.temp_root / "first")
        second = build_release(ROOT, VERSION, self.temp_root / "second")
        for key in ("vpm_zip", "unitypackage", "checksums"):
            self.assertEqual(first[key].read_bytes(), second[key].read_bytes(), key)

    def test_missing_and_duplicate_meta_guids_are_rejected(self):
        missing_repo = self.copy_repo_fixture()
        missing = missing_repo / "Packages" / PACKAGE_ID / "Runtime" / "Particle.mat.meta"
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or unsafe Unity .meta"):
            build_release(missing_repo, VERSION, self.temp_root / "missing")

        duplicate_repo = self.copy_repo_fixture()
        package = duplicate_repo / "Packages" / PACKAGE_ID
        particle_meta = package / "Runtime" / "Particle.mat.meta"
        prefab_meta = package / "Runtime" / "EatEar.prefab.meta"
        replacement = self.meta_guid(prefab_meta)
        text = particle_meta.read_text(encoding="utf-8")
        text, count = re.subn(r"(?m)^guid:\s*[0-9a-fA-F]{32}\s*$", f"guid: {replacement}", text, count=1)
        self.assertEqual(count, 1)
        particle_meta.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate Unity GUID"):
            build_release(duplicate_repo, VERSION, self.temp_root / "duplicate")

    def test_unapproved_external_guid_reference_fails_closed(self):
        fixture_repo = self.copy_repo_fixture()
        prefab = fixture_repo / "Packages" / PACKAGE_ID / "Runtime" / "EatEar.prefab"
        text = prefab.read_text(encoding="utf-8")
        old = "guid: 29ff6b7da63048e4bbaafcc6b8fe2ea6"
        self.assertIn(old, text)
        prefab.write_text(text.replace(old, "guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unapproved external GUID"):
            build_release(fixture_repo, VERSION, self.temp_root / "unknown-guid")

    def test_legacy_archive_paths_reject_traversal_and_noncanonical_paths(self):
        self.assertEqual(validate_legacy_path("Assets/SaiEatEar/Animation/EatEar_L.anim"),
                         "Assets/SaiEatEar/Animation/EatEar_L.anim")
        for path in (
            "../Assets/SaiEatEar/evil",
            "Assets/SaiEatEar/../escape",
            "Assets//SaiEatEar/EatEar.prefab",
            "Assets/SaiEatEar/./Animation",
            "/Assets/SaiEatEar/absolute",
            r"Assets\SaiEatEar\EatEar.prefab",
            "Assets/Other/avatar.prefab",
            "C:/Assets/SaiEatEar/file",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_legacy_path(path)

    @staticmethod
    def meta_guid(path: Path) -> str:
        match = META_GUID.findall(path.read_bytes())
        if len(match) != 1:
            raise AssertionError(f"Expected one meta GUID in {path}")
        return match[0].decode("ascii").lower()

    @staticmethod
    def parse_sums(path: Path) -> dict[str, str]:
        parsed = {}
        for line in path.read_text(encoding="ascii").splitlines():
            digest, separator, name = line.partition("  ")
            if not separator or len(digest) != 64:
                raise AssertionError(f"Invalid SHA256SUMS line: {line!r}")
            parsed[name] = digest
        return parsed

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
