"""Build and verify immutable LOKI release archives from committed Git bytes."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import zipfile
from ctypes import wintypes
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MANIFEST_NAME = "release-manifest.json"
SCHEMA = "loki-release-manifest/v1"
SIDECAR_SCHEMA = "loki-release-archive-digest/v1"
_CACHE_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "data",
        "dist",
        "handoff",
        "logs",
        "runtime-logs",
    }
)


class ManifestError(RuntimeError):
    """Release evidence is missing, malformed, or does not bind exact bytes."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_sidecar_path(archive: Path) -> Path:
    return Path(f"{archive}.sha256.json")


def archive_text_digest_path(archive: Path) -> Path:
    return Path(f"{archive}.sha256")


def _git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(f"Git command failed ({arguments[0]}): {detail or 'no diagnostic'}")
    return result.stdout


def _git_text(root: Path, *arguments: str) -> str:
    return _git(root, *arguments).decode("utf-8", errors="strict").strip()


def assert_clean_source(root: Path) -> None:
    status = _git_text(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=no")
    if status:
        count = len(status.splitlines())
        raise ManifestError(f"Source tree must be clean before release build ({count} changed or untracked paths)")


def _safe_relative_path(value: str) -> str:
    if "\\" in value or "\0" in value:
        raise ManifestError("Archive path uses an unsafe separator or NUL")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ManifestError(f"Unsafe archive path: {value!r}")
    for part in path.parts:
        if ":" in part or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved():
            raise ManifestError(f"Unsafe Windows archive path: {value!r}")
    return path.as_posix()


class _WIN32_FIND_STREAM_DATA(ctypes.Structure):
    _fields_ = (
        ("stream_size", ctypes.c_longlong),
        ("stream_name", ctypes.c_wchar * 296),
    )


def _alternate_data_streams(path: Path) -> tuple[str, ...]:
    if os.name != "nt":
        return ()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(_WIN32_FIND_STREAM_DATA),
        wintypes.DWORD,
    )
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_WIN32_FIND_STREAM_DATA))
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = (wintypes.HANDLE,)
    find_close.restype = wintypes.BOOL

    data = _WIN32_FIND_STREAM_DATA()
    handle = find_first(str(path), 0, ctypes.byref(data), 0)
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        error_code = ctypes.get_last_error()
        if error_code == 38:  # ERROR_HANDLE_EOF: the filesystem exposes no streams.
            return ()
        raise OSError(error_code, f"Unable to enumerate file streams for {path.name}")
    names: list[str] = []
    try:
        names.append(data.stream_name)
        while find_next(handle, ctypes.byref(data)):
            names.append(data.stream_name)
        error_code = ctypes.get_last_error()
        if error_code != 38:  # ERROR_HANDLE_EOF is the expected terminal result.
            raise OSError(error_code, f"Unable to finish file-stream enumeration for {path.name}")
    finally:
        find_close(handle)
    return tuple(name for name in names if name != "::$DATA")


def _assert_no_alternate_data_streams(root: Path) -> None:
    if os.name != "nt":
        return
    for path in (root, *root.rglob("*")):
        streams = _alternate_data_streams(path)
        if streams:
            relative = "." if path == root else path.relative_to(root).as_posix()
            raise ManifestError(f"Release directory contains alternate data stream: {relative}")


def is_forbidden_payload_path(value: str) -> bool:
    path = PurePosixPath(_safe_relative_path(value))
    lowered = tuple(part.casefold() for part in path.parts)
    if path.suffix.casefold() == ".log":
        return True
    if any(part in _CACHE_PARTS for part in lowered):
        return True
    if any(part == "venv" or part.startswith(("venv-", ".venv")) for part in lowered):
        return True
    for part in lowered:
        if part == ".env" or (part.startswith(".env.") and part != ".env.example"):
            return True
    return False


def _committed_files(root: Path, commit_id: str) -> list[tuple[str, bytes]]:
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit_id)
    payload: list[tuple[str, bytes]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, separator, encoded_path = record.partition(b"\t")
        if not separator:
            raise ManifestError("Git tree returned a malformed record")
        fields = metadata.split()
        if len(fields) != 3:
            raise ManifestError("Git tree returned malformed metadata")
        _mode, object_type, object_id = fields
        if object_type != b"blob":
            raise ManifestError("Submodules and non-blob Git entries are not supported in release archives")
        try:
            name = encoded_path.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ManifestError("Release paths must be valid UTF-8") from error
        safe_name = _safe_relative_path(name)
        if safe_name == MANIFEST_NAME:
            raise ManifestError(f"Tracked source cannot replace reserved {MANIFEST_NAME}")
        if is_forbidden_payload_path(safe_name):
            continue
        content = _git(root, "cat-file", "blob", object_id.decode("ascii"))
        payload.append((safe_name, content))
    return sorted(payload, key=lambda item: item[0])


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_release_archive(
    source_root: str | Path,
    archive_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(source_root).expanduser().resolve()
    archive = Path(archive_path).expanduser().resolve()
    if not root.is_dir():
        raise ManifestError(f"Source root does not exist: {root}")
    assert_clean_source(root)
    commit_id = _git_text(root, "rev-parse", "HEAD")
    tree_id = _git_text(root, "rev-parse", "HEAD^{tree}")
    candidate_id = f"loki-{commit_id[:12]}"
    files = _committed_files(root, commit_id)
    if not files:
        raise ManifestError("Committed release payload is empty")

    entries = [
        {
            "path": name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        for name, content in files
    ]
    manifest = {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "commit_id": commit_id,
        "tree_id": tree_id,
        "files": entries,
    }
    sidecar = archive_sidecar_path(archive)
    text_digest = archive_text_digest_path(archive)
    targets = (archive, sidecar, text_digest)
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        raise ManifestError(f"Release artifact already exists: {existing[0]}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    for path in existing:
        path.unlink()

    try:
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, content in files:
                bundle.writestr(_zip_info(name), content)
            bundle.writestr(_zip_info(MANIFEST_NAME), _manifest_bytes(manifest))
        archive_hash = sha256_file(archive)
        evidence = {
            "schema": SIDECAR_SCHEMA,
            "candidate_id": candidate_id,
            "commit_id": commit_id,
            "tree_id": tree_id,
            "archive_name": archive.name,
            "archive_sha256": archive_hash,
            "archive_size": archive.stat().st_size,
        }
        sidecar.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        text_digest.write_text(f"{archive_hash}  {archive.name}\n", encoding="ascii")
        verify_archive(archive, sidecar)
    except Exception:
        for path in targets:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return {
        **evidence,
        "archive_path": str(archive),
        "sidecar_path": str(sidecar),
        "text_digest_path": str(text_digest),
        "file_count": len(entries),
    }


def _load_manifest_bytes(raw: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError("Release manifest is not valid UTF-8 JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ManifestError("Release manifest schema is missing or unsupported")
    for field in ("candidate_id", "commit_id", "tree_id", "files"):
        if field not in manifest:
            raise ManifestError(f"Release manifest is missing {field}")
    if not isinstance(manifest["files"], list):
        raise ManifestError("Release manifest files must be a list")
    return manifest


def _expected_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    windows_names: set[str] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ManifestError("Release manifest contains a malformed file record")
        name = _safe_relative_path(str(item.get("path", "")))
        if name == MANIFEST_NAME or is_forbidden_payload_path(name):
            raise ManifestError(f"Release manifest contains forbidden path: {name}")
        if name in expected:
            raise ManifestError(f"Release manifest contains duplicate path: {name}")
        if name.casefold() in windows_names:
            raise ManifestError(f"Release manifest contains a Windows path collision: {name}")
        digest = item.get("sha256")
        size = item.get("size")
        if not isinstance(digest, str) or len(digest) != 64 or not isinstance(size, int) or size < 0:
            raise ManifestError(f"Release manifest has invalid digest or size for {name}")
        expected[name] = item
        windows_names.add(name.casefold())
    return expected


def verify_archive(
    archive_path: str | Path,
    sidecar_path: str | Path | None = None,
) -> dict[str, Any]:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise ManifestError(f"Release archive does not exist: {archive}")
    with zipfile.ZipFile(archive, "r") as bundle:
        if any(info.is_dir() for info in bundle.infolist()):
            raise ManifestError("Release archive contains unexpected directory entries")
        names = [_safe_relative_path(info.filename) for info in bundle.infolist()]
        if len(names) != len(set(names)):
            raise ManifestError("Release archive contains duplicate paths")
        if len(names) != len({name.casefold() for name in names}):
            raise ManifestError("Release archive contains Windows path collisions")
        if MANIFEST_NAME not in names:
            raise ManifestError(f"Release archive is missing {MANIFEST_NAME}")
        manifest = _load_manifest_bytes(bundle.read(MANIFEST_NAME))
        expected = _expected_entries(manifest)
        actual_payload = set(names) - {MANIFEST_NAME}
        if actual_payload != set(expected):
            raise ManifestError("Release archive payload does not exactly match its manifest")
        for name, item in expected.items():
            content = bundle.read(name)
            if len(content) != item["size"]:
                raise ManifestError(f"Release file size mismatch: {name}")
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ManifestError(f"Release file digest mismatch: {name}")

    if sidecar_path is not None:
        sidecar = Path(sidecar_path).expanduser().resolve()
        try:
            evidence = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestError("Archive SHA-256 sidecar is missing or invalid") from error
        if evidence.get("schema") != SIDECAR_SCHEMA:
            raise ManifestError("Archive SHA-256 sidecar schema is unsupported")
        checks = {
            "archive_name": archive.name,
            "archive_sha256": sha256_file(archive),
            "archive_size": archive.stat().st_size,
            "candidate_id": manifest["candidate_id"],
            "commit_id": manifest["commit_id"],
            "tree_id": manifest["tree_id"],
        }
        for key, value in checks.items():
            if evidence.get(key) != value:
                raise ManifestError(f"Archive SHA-256 sidecar mismatch: {key}")
    return manifest


def verify_directory(release_root: str | Path) -> dict[str, Any]:
    root = Path(release_root).expanduser().resolve()
    if not root.is_dir():
        raise ManifestError(f"Release root does not exist: {root}")
    _assert_no_alternate_data_streams(root)
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = _load_manifest_bytes(manifest_path.read_bytes())
    except OSError as error:
        raise ManifestError(f"Release root is missing {MANIFEST_NAME}") from error
    expected = _expected_entries(manifest)
    actual: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        actual.add(_safe_relative_path(relative))
    if actual != set(expected) | {MANIFEST_NAME}:
        raise ManifestError("Extracted release payload does not exactly match its manifest")
    for name, item in expected.items():
        path = (root / Path(*PurePosixPath(name).parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ManifestError(f"Release path escapes root: {name}") from error
        if path.stat().st_size != item["size"]:
            raise ManifestError(f"Release file size mismatch: {name}")
        if sha256_file(path) != item["sha256"]:
            raise ManifestError(f"Release file digest mismatch: {name}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build an exact committed-tree release archive")
    build.add_argument("--source", required=True)
    build.add_argument("--archive", required=True)
    build.add_argument("--force", action="store_true")
    verify_zip = subparsers.add_parser("verify-archive", help="Verify archive payload and external digest")
    verify_zip.add_argument("--archive", required=True)
    verify_zip.add_argument("--sidecar")
    verify_dir = subparsers.add_parser("verify-directory", help="Verify an extracted immutable release")
    verify_dir.add_argument("--root", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            result = build_release_archive(args.source, args.archive, force=args.force)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verify-archive":
            result = verify_archive(args.archive, args.sidecar)
            print(json.dumps({key: result[key] for key in ("candidate_id", "commit_id", "tree_id")}, sort_keys=True))
        else:
            result = verify_directory(args.root)
            print(json.dumps({key: result[key] for key in ("candidate_id", "commit_id", "tree_id")}, sort_keys=True))
    except (ManifestError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"release verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
