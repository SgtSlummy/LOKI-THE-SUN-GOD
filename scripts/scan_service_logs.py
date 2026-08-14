"""Fail if LOKI service logs contain managed secrets or OAuth credential patterns."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import credential_store  # noqa: E402

OAUTH_PATTERNS = {
    "oauth-query-credential": re.compile(
        r"(?i)(?:[?&](?:access_token|client_secret|code|refresh_token)=|authorization\s*[:=]\s*bearer\s+)"
    ),
}


def _secret_values(env_path: Path | None) -> dict[str, set[str]]:
    values = {name: set() for name in credential_store.SUPPORTED_SECRET_NAMES}
    if env_path is not None:
        if not env_path.is_file():
            raise FileNotFoundError("stable environment config is missing")
        configured = dotenv_values(env_path)
        for name in values:
            value = configured.get(name)
            if isinstance(value, str) and value:
                values[name].add(value)
    for name in values:
        process_value = os.environ.get(name)
        if process_value:
            values[name].add(process_value)
    if os.name == "nt" and credential_store.win32cred is None:
        raise RuntimeError("Credential Manager support is unavailable")
    for name in values:
        managed_value = credential_store.read_credential(name)
        if managed_value:
            values[name].add(managed_value)
    return values


def scan_logs(paths: list[Path], env_path: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    missing: list[str] = []
    credential_hits: set[str] = set()
    pattern_hits: set[str] = set()
    credentials = _secret_values(env_path)
    for path in paths:
        if not path.is_file():
            missing.append(path.name)
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for name, values in credentials.items():
            if any(value in content for value in values):
                credential_hits.add(name)
        for label, pattern in OAUTH_PATTERNS.items():
            if pattern.search(content):
                pattern_hits.add(label)
    return sorted(missing), sorted(credential_hits), sorted(pattern_hits)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--env-path")
    args = parser.parse_args(argv)
    paths = [Path(value).expanduser().resolve() for value in args.logs]
    env_path = Path(args.env_path).expanduser().resolve() if args.env_path else None
    try:
        missing, credential_hits, pattern_hits = scan_logs(paths, env_path)
    except Exception as error:
        parser.exit(2, f"Service log scan failed ({type(error).__name__}); no log content was emitted.\n")
    failures: list[str] = []
    if missing:
        failures.append("missing logs: " + ", ".join(missing))
    if credential_hits:
        failures.append("managed credential names detected: " + ", ".join(credential_hits))
    if pattern_hits:
        failures.append("OAuth credential patterns detected: " + ", ".join(pattern_hits))
    if failures:
        print("Service log verification failed; " + "; ".join(failures) + ".", file=sys.stderr)
        return 1
    print(f"Service logs passed redacted credential scan ({len(paths)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
