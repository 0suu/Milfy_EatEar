#!/usr/bin/env python3
"""Build deterministic VPM and legacy Unity package archives from one package source."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import tarfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

PACKAGE_ID = "jp.suu.eat-ear"
PACKAGE_DIRECTORY = Path("Packages") / PACKAGE_ID
LEGACY_ROOT = "Assets/SaiEatEar"
SERIALIZED_EXTENSIONS = {".prefab", ".anim", ".controller", ".mat", ".asset"}
GUID_PATTERN = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
REFERENCE_PATTERN = re.compile(r"\bguid:\s*([0-9a-fA-F]{32})\b")
VERSION_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
EXPECTED_PACKAGE_FILES = {
    "package.json",
    "package.json.meta",
    "README.md",
    "README.md.meta",
    "CHANGELOG.md",
    "CHANGELOG.md.meta",
    "Runtime",
    "Runtime.meta",
}


@dataclass(frozen=True)
class LegacyAsset:
    path: str
    source: Path
    meta: Path
    guid: str
    is_directory: bool


def validate_legacy_path(value: str) -> str:
    """Return a canonical legacy Unity path or reject unsafe archive paths."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe legacy asset path: {value!r}")
    path = PurePosixPath(value)
    if path.as_posix() != value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe legacy asset path: {value!r}")
    if len(path.parts) < 2 or path.parts[0] != "Assets" or path.parts[1] != "SaiEatEar":
        raise ValueError(f"Legacy path is outside {LEGACY_ROOT}: {value!r}")
    return path.as_posix()


def read_guid(meta_path: Path) -> str:
    if not meta_path.is_file() or meta_path.is_symlink():
        raise ValueError(f"Missing or unsafe Unity .meta file: {meta_path}")
    try:
        text = meta_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Unity .meta is not UTF-8: {meta_path}") from error
    matches = GUID_PATTERN.findall(text)
    if len(matches) != 1:
        raise ValueError(f"Expected one 32-character GUID in {meta_path}, found {len(matches)}")
    return matches[0].lower()


def package_root_for(repository_root: Path) -> Path:
    return repository_root / PACKAGE_DIRECTORY


def iter_source_files(package_root: Path) -> list[Path]:
    if not package_root.is_dir() or package_root.is_symlink():
        raise ValueError(f"Package source directory is missing or unsafe: {package_root}")
    top_level = {child.name for child in package_root.iterdir()}
    if top_level != EXPECTED_PACKAGE_FILES:
        extra = sorted(top_level - EXPECTED_PACKAGE_FILES)
        missing = sorted(EXPECTED_PACKAGE_FILES - top_level)
        raise ValueError(f"Unexpected package source entries; extra={extra}, missing={missing}")

    files = []
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in package source: {path}")
        if path.is_file():
            files.append(path)
    for required in ("package.json", "README.md", "README.md.meta", "CHANGELOG.md", "CHANGELOG.md.meta"):
        if not (package_root / required).is_file():
            raise ValueError(f"Required package file is missing: {package_root / required}")
    return sorted(files, key=lambda path: path.relative_to(package_root).as_posix())


def load_manifest(package_root: Path, version: str) -> dict:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid release version: {version!r}")
    manifest_path = package_root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read package manifest: {manifest_path}") from error
    if not isinstance(manifest, dict) or manifest.get("name") != PACKAGE_ID:
        raise ValueError(f"package.json name must be {PACKAGE_ID}")
    if manifest.get("version") != version:
        raise ValueError(
            f"Release version {version} does not match package.json version "
            f"{manifest.get('version')!r}"
        )
    expected_url = (
        f"https://github.com/0suu/Milfy_EatEar/releases/download/{version}/"
        f"{PACKAGE_ID}-{version}.zip"
    )
    if manifest.get("url") != expected_url:
        raise ValueError(f"package.json url must be {expected_url}")
    return manifest


def legacy_assets(package_root: Path) -> list[LegacyAsset]:
    source_assets: list[tuple[Path, str, bool]] = []
    runtime = package_root / "Runtime"
    if not runtime.is_dir():
        raise ValueError(f"Runtime directory is missing: {runtime}")
    source_assets.append((runtime, LEGACY_ROOT, True))
    for path in runtime.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in Runtime: {path}")
        if path.is_dir():
            rel = path.relative_to(package_root).as_posix()
            source_assets.append((path, f"{LEGACY_ROOT}/{rel.removeprefix('Runtime/')}", True))
        elif path.is_file() and not path.name.endswith(".meta"):
            rel = path.relative_to(package_root).as_posix()
            source_assets.append((path, f"{LEGACY_ROOT}/{rel.removeprefix('Runtime/')}", False))

    for doc_name in ("README.md", "CHANGELOG.md"):
        source_assets.append((package_root / doc_name, f"{LEGACY_ROOT}/{doc_name}", False))

    records = []
    seen_guids: dict[str, str] = {}
    seen_paths: set[str] = set()
    for source, legacy_path, is_directory in source_assets:
        legacy_path = validate_legacy_path(legacy_path)
        if legacy_path in seen_paths:
            raise ValueError(f"Duplicate legacy asset path: {legacy_path}")
        seen_paths.add(legacy_path)
        relative = source.relative_to(package_root)
        meta = package_root / "Runtime.meta" if relative.as_posix() == "Runtime" else Path(f"{source}.meta")
        if not source.exists() or source.is_symlink():
            raise ValueError(f"Missing or unsafe Unity asset: {source}")
        guid = read_guid(meta)
        if guid in seen_guids:
            raise ValueError(
                f"Duplicate Unity GUID {guid}: {seen_guids[guid]} and {legacy_path}"
            )
        seen_guids[guid] = legacy_path
        records.append(LegacyAsset(legacy_path, source, meta, guid, is_directory))

    # The checked-in fixture is the BOOTH package's original GUID/path inventory.
    fixture_path = package_root.parents[1] / "tests" / "fixtures" / "legacy-guids.json"
    try:
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read legacy GUID fixture: {fixture_path}") from error
    expected = {path: guid.lower() for path, guid in original.items()}
    actual = {record.path: record.guid for record in records if record.path.startswith(f"{LEGACY_ROOT}/") or record.path == LEGACY_ROOT}
    for path, guid in expected.items():
        if actual.get(path) != guid:
            raise ValueError(
                f"Original BOOTH GUID mismatch at {path}: expected {guid}, got {actual.get(path)!r}"
            )
    manifest = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    root_guid = actual.get(LEGACY_ROOT)
    expected_legacy_folders = {
        "Assets\\SaiEatEar": root_guid,
        "Assets\\sai\\SaiEatEar": root_guid,
    }
    if manifest.get("legacyFolders") != expected_legacy_folders:
        raise ValueError("package.json legacyFolders must preserve both original folder aliases and root GUID")
    for path in actual:
        if path not in expected and path not in {
            f"{LEGACY_ROOT}/README.md",
            f"{LEGACY_ROOT}/CHANGELOG.md",
        }:
            raise ValueError(f"Unexpected legacy asset not present in original GUID fixture: {path}")
    return sorted(records, key=lambda record: (record.guid, record.path))


def allowed_external_guids(repository_root: Path) -> set[str]:
    path = repository_root / "tests" / "fixtures" / "allowed-external-guids.json"
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read allowed external GUID fixture: {path}") from error
    if not isinstance(values, dict):
        raise ValueError(f"Allowed external GUID fixture must be an object: {path}")
    for guid, reason in values.items():
        if not re.fullmatch(r"[0-9a-fA-F]{32}", guid) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Invalid allowed external GUID record: {guid!r}")
    return {guid.lower() for guid in values}


def validate_references(repository_root: Path, package_root: Path, records: list[LegacyAsset]) -> None:
    internal = {record.guid for record in records}
    allowed = allowed_external_guids(repository_root)
    references: set[str] = set()
    for path in package_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SERIALIZED_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Serialized Unity asset is not UTF-8: {path}") from error
        references.update(guid.lower() for guid in REFERENCE_PATTERN.findall(text))
    unknown = sorted(references - internal - allowed)
    if unknown:
        raise ValueError(
            "Unapproved external GUID references found (personal assets must not be included): "
            + ", ".join(unknown)
        )


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info


def write_vpm_zip(package_root: Path, files: list[Path], output_path: Path) -> None:
    included = [
        package_root / name
        for name in (
            "package.json",
            "README.md",
            "README.md.meta",
            "CHANGELOG.md",
            "CHANGELOG.md.meta",
            "Runtime.meta",
        )
    ]
    included.extend(
        path for path in files
        if path.relative_to(package_root).as_posix().startswith("Runtime/")
    )
    with zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source in sorted(included, key=lambda path: path.relative_to(package_root).as_posix()):
            name = source.relative_to(package_root).as_posix()
            archive.writestr(zip_info(name), source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def tar_info(name: str, data: bytes = b"", is_directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    info.type = tarfile.DIRTYPE if is_directory else tarfile.REGTYPE
    info.mode = 0o755 if is_directory else 0o644
    info.size = 0 if is_directory else len(data)
    return info


def write_unitypackage(records: list[LegacyAsset], output_path: Path) -> None:
    with output_path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0
        ) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
            ) as archive:
                for record in records:
                    base = record.guid
                    if record.is_directory:
                        archive.addfile(tar_info(f"{base}/asset", is_directory=True))
                        meta_bytes = record.meta.read_bytes()
                    else:
                        asset_bytes = record.source.read_bytes()
                        archive.addfile(tar_info(f"{base}/asset", asset_bytes), BytesIO(asset_bytes))
                        meta_bytes = record.meta.read_bytes()
                    archive.addfile(
                        tar_info(f"{base}/asset.meta", meta_bytes), BytesIO(meta_bytes)
                    )
                    pathname = validate_legacy_path(record.path).encode("utf-8")
                    archive.addfile(
                        tar_info(f"{base}/pathname", pathname), BytesIO(pathname)
                    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_release(repository_root: Path, version: str, output_dir: Path) -> dict[str, Path]:
    repository_root = repository_root.resolve()
    package_root = package_root_for(repository_root)
    files = iter_source_files(package_root)
    load_manifest(package_root, version)
    records = legacy_assets(package_root)
    validate_references(repository_root, package_root, records)

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{PACKAGE_ID}-{version}.zip"
    unitypackage_path = output_dir / f"{PACKAGE_ID}-{version}.unitypackage"
    write_vpm_zip(package_root, files, zip_path)
    write_unitypackage(records, unitypackage_path)

    sums_path = output_dir / "SHA256SUMS"
    lines = [
        f"{sha256(path)}  {path.name}"
        for path in sorted((zip_path, unitypackage_path), key=lambda item: item.name)
    ]
    sums_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return {"vpm_zip": zip_path, "unitypackage": unitypackage_path, "checksums": sums_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Must match Packages/jp.suu.eat-ear/package.json")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        artifacts = build_release(Path(__file__).resolve().parents[1], args.version, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, tarfile.TarError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    for label, path in artifacts.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
