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
MILFY_MATERIAL_FIXTURE = ROOT / "tests" / "fixtures" / "milfy-material-reference.json"
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

    def test_vpm_zip_and_unitypackage_include_current_assets(self):
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
                expected = {"Assets/SaiEatEar": self.meta_guid(PACKAGE_ROOT / "Runtime.meta")}
                for source in (PACKAGE_ROOT / "Runtime").rglob("*"):
                    if source.name.endswith(".meta"):
                        continue
                    path = "Assets/SaiEatEar/" + source.relative_to(PACKAGE_ROOT / "Runtime").as_posix()
                    expected[path] = self.meta_guid(Path(f"{source}.meta"))
                for name in ("README.md", "CHANGELOG.md"):
                    expected[f"Assets/SaiEatEar/{name}"] = self.meta_guid(PACKAGE_ROOT / f"{name}.meta")
                self.assertEqual(actual, expected)
                prefab_path = "Assets/SaiEatEar/Milfy_EatEar.prefab"
                prefab_guid = actual[prefab_path]
                prefab_asset = archive.extractfile(f"{prefab_guid}/asset").read()
                self.assertEqual(prefab_asset, (PACKAGE_ROOT / "Runtime" / "Milfy_EatEar.prefab").read_bytes())
                self.assertEqual(archive.extractfile(f"{prefab_guid}/asset.meta").read(), (PACKAGE_ROOT / "Runtime" / "Milfy_EatEar.prefab.meta").read_bytes())
                self.assertTrue(all(name.split("/", 1)[0] in actual.values() for name in archive_names))

        sums = self.parse_sums(artifacts["checksums"])
        self.assertEqual(set(sums), {zip_path.name, unitypackage_path.name})
        for name, digest in sums.items():
            artifact = artifacts["vpm_zip"] if name == zip_path.name else unitypackage_path
            self.assertEqual(self.sha256(artifact), digest)

    def test_ear_mesh_uv_assignments_match_milfy(self):
        # Confirmed against the ear UV regions in the original Milfy 1.5.0 model.
        expected = {
            "EatEar_L": ("145876726828247544", "d9dcb949759a3f14d9e2598f6812e5f1"),
            "EatEar_R": ("-3176753397780858161", "7a159063dc7faa84c9966dbf0a2083f8"),
        }
        text = (PACKAGE_ROOT / "Runtime" / "Milfy_EatEar.prefab").read_text(encoding="utf-8")
        actual = {}
        for block in re.split(r"(?m)^--- !u!1001 &", text)[1:]:
            block = block.split("\n---", 1)[0]
            name = re.search(r"propertyPath: m_Name\s+value: (EatEar_[LR])\b", block)
            if name is None:
                continue
            mesh = re.search(
                r"propertyPath: m_Mesh\s+value:\s+objectReference: "
                r"\{fileID: (-?\d+), guid: ([0-9a-f]{32}),", block,
            )
            self.assertIsNotNone(mesh, f"Missing explicit mesh assignment for {name[1]}")
            actual[name[1]] = mesh.groups()
        self.assertEqual(actual, expected)

    def test_milfy_material_overrides_stay_external_in_both_archives(self):
        material_fixture = json.loads(
            MILFY_MATERIAL_FIXTURE.read_text(encoding="utf-8")
        )
        material_guid = material_fixture["originalEatEarMaterialGuid"].lower()
        material_path = material_fixture["materials"][material_guid]
        self.assertEqual(
            material_path,
            "Assets/PLUSONE/Milfy/Materials/kaihen(Another)/Hair_Another.mat",
        )

        prefab_path = PACKAGE_ROOT / "Runtime" / "Milfy_EatEar.prefab"
        prefab_bytes = prefab_path.read_bytes()
        prefab_text = prefab_bytes.decode("utf-8")
        material_overrides = re.findall(
            r"propertyPath: m_Materials\.Array\.data\[0\]\s+value:\s+"
            r"objectReference: \{fileID: 2100000, guid: ([0-9a-fA-F]{32}), type: 2\}",
            prefab_text,
        )
        self.assertEqual(
            [guid.lower() for guid in material_overrides],
            [material_guid, material_guid],
            "Both ear material overrides must retain the original Milfy material GUID",
        )

        artifacts = build_release(ROOT, VERSION, self.temp_root / "milfy-material")
        with zipfile.ZipFile(artifacts["vpm_zip"]) as archive:
            vpm_names = set(archive.namelist())
            self.assertEqual(archive.read("Runtime/Milfy_EatEar.prefab"), prefab_bytes)
            self.assertNotIn(material_guid, {
                guid.decode("ascii").lower()
                for name in vpm_names
                if name.endswith(".meta")
                for guid in META_GUID.findall(archive.read(name))
            })
            self.assertFalse(any("PLUSONE/Milfy/" in name for name in vpm_names))
            self.assertNotIn(Path(material_path).name, {Path(name).name for name in vpm_names})
            self.assertFalse(any(
                Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".tga", ".psd", ".tif", ".tiff"}
                for name in vpm_names
            ), "Milfy texture files must not be bundled in the VPM archive")

        with gzip.open(artifacts["unitypackage"], "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r:") as archive:
                pathname_to_guid = {
                    archive.extractfile(member).read().decode("utf-8"): member.name.split("/", 1)[0]
                    for member in archive.getmembers()
                    if member.name.endswith("/pathname")
                }
                legacy_prefab_path = "Assets/SaiEatEar/Milfy_EatEar.prefab"
                prefab_guid = pathname_to_guid[legacy_prefab_path]
                self.assertEqual(
                    archive.extractfile(f"{prefab_guid}/asset").read(), prefab_bytes
                )
                self.assertNotIn(material_guid, pathname_to_guid.values())
                self.assertFalse(any(
                    path.startswith("Assets/PLUSONE/Milfy/")
                    for path in pathname_to_guid
                ))
                self.assertNotIn(
                    Path(material_path).name,
                    {Path(path).name for path in pathname_to_guid},
                )
                self.assertFalse(any(
                    Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".tga", ".psd", ".tif", ".tiff"}
                    for path in pathname_to_guid
                ), "Milfy texture files must not be bundled in the legacy archive")

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
        prefab_meta = package / "Runtime" / "Milfy_EatEar.prefab.meta"
        replacement = self.meta_guid(prefab_meta)
        text = particle_meta.read_text(encoding="utf-8")
        text, count = re.subn(r"(?m)^guid:\s*[0-9a-fA-F]{32}\s*$", f"guid: {replacement}", text, count=1)
        self.assertEqual(count, 1)
        particle_meta.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate Unity GUID"):
            build_release(duplicate_repo, VERSION, self.temp_root / "duplicate")

    def test_unapproved_external_guid_reference_fails_closed(self):
        fixture_repo = self.copy_repo_fixture()
        prefab = fixture_repo / "Packages" / PACKAGE_ID / "Runtime" / "Milfy_EatEar.prefab"
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
            "Assets//SaiEatEar/Milfy_EatEar.prefab",
            "Assets/SaiEatEar/./Animation",
            "/Assets/SaiEatEar/absolute",
            r"Assets\SaiEatEar\Milfy_EatEar.prefab",
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
