"""Interactively seed one approved LOKI secret into Windows Credential Manager."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    import win32api
    import win32con
    import win32security
except ImportError:  # pragma: no cover - Windows-only commissioning path
    win32api = None
    win32con = None
    win32security = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import credential_store  # noqa: E402

SERVICE_IDENTITY = r"LOKI\Administrator"


def _candidate_pythons() -> list[Path]:
    manifest_path = ROOT / "release-manifest.json"
    try:
        candidate_id = str(json.loads(manifest_path.read_text(encoding="utf-8"))["candidate_id"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return []
    program_data = Path(r"C:\ProgramData")
    expected_root = program_data / "Loki" / "releases" / candidate_id
    if os.path.normcase(str(ROOT.resolve())) != os.path.normcase(str(expected_root.resolve())):
        return []
    return [program_data / "Loki" / "venvs" / candidate_id / "Scripts" / "python.exe"]


def maybe_reexec_with_pywin32(*, platform_name: str | None = None, pywin32_ready: bool | None = None) -> None:
    """Keep the documented py command usable without mutating global Python."""

    platform_name = os.name if platform_name is None else platform_name
    if pywin32_ready is None:
        pywin32_ready = win32api is not None and win32con is not None and win32security is not None
    if platform_name != "nt" or pywin32_ready:
        return
    current = Path(sys.executable).resolve()
    for candidate in _candidate_pythons():
        candidate = candidate.expanduser().resolve()
        if candidate == current or not candidate.is_file():
            continue
        check = subprocess.run(
            [str(candidate), "-I", "-B", "-c", "import win32api, win32con, win32cred, win32security"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if check.returncode == 0:
            child = subprocess.run(
                [str(candidate), "-I", "-B", str(Path(__file__).resolve()), *sys.argv[1:]],
                check=False,
            )
            raise SystemExit(child.returncode)


def assert_service_identity() -> str:
    """Fail before prompting unless this process is the selected service identity."""

    if os.name != "nt":
        raise RuntimeError("Credential setup is supported only on Windows")
    if win32api is None or win32con is None or win32security is None:
        raise RuntimeError("Token-backed Windows identity validation requires pywin32")
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid, _attributes = win32security.GetTokenInformation(token, win32security.TokenUser)
        username, domain, _account_type = win32security.LookupAccountSid(None, sid)
    finally:
        token.Close()
    actual = f"{domain}\\{username}"
    if actual.casefold() != SERVICE_IDENTITY.casefold():
        raise RuntimeError(f"Run this command as {SERVICE_IDENTITY}; current identity is not authorized")
    return SERVICE_IDENTITY


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_parser = subparsers.add_parser("set", help="Set one approved Generic Credential")
    set_parser.add_argument("name", choices=credential_store.SUPPORTED_SECRET_NAMES)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        assert_service_identity()
        target = credential_store.credential_target(args.name)
        value = getpass.getpass(f"Enter {args.name}: ")
        confirmation = getpass.getpass(f"Confirm {args.name}: ")
        if not value:
            raise ValueError("credential value is empty")
        if value != confirmation:
            raise ValueError("credential confirmation did not match")
        credential_store.write_credential(args.name, value)
    except Exception as error:
        value = None
        confirmation = None
        parser.exit(1, f"Credential operation failed for {args.name} ({type(error).__name__}); no value was written.\n")
    finally:
        value = None
        confirmation = None
    print(f"Stored {args.name} at {target} for {SERVICE_IDENTITY}.")
    return 0


if __name__ == "__main__":
    maybe_reexec_with_pywin32()
    raise SystemExit(main())
