"""Fail if LOKI service logs contain managed secrets or OAuth credential patterns."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote_plus

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import credential_store  # noqa: E402

OAUTH_PATTERNS = {
    "oauth-query-credential": re.compile(
        r'''(?ix)
        (?<![A-Za-z0-9_])["']?(?:access_token|client_secret|authorization_code|refresh_token|code)["']?
        (?![A-Za-z0-9_])
        \s*(?:=|:)\s*(?:["'][^"'\r\n]+["']|[^\s&,;}]+)
        '''
    ),
    "authorization-credential": re.compile(r"(?i)authorization\s*[:=]\s*(?:bearer|bot)\s+\S+"),
}

SECRET_NAME_PATTERN = re.compile(
    r"(?i)(?:^|_)(?:TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_KEY|PRIVATE_KEY|SIGNING_KEY|ENCRYPTION_KEY|DATABASE_URL)(?:$|_)"
)


def _is_secret_bearing_name(name: str) -> bool:
    return bool(SECRET_NAME_PATTERN.search(name))


def _secret_values(env_path: Path | None) -> dict[str, set[str]]:
    values = {name: set() for name in credential_store.SUPPORTED_SECRET_NAMES}
    if env_path is not None:
        if not env_path.is_file():
            raise FileNotFoundError("stable environment config is missing")
        configured = dotenv_values(env_path)
        for name, value in configured.items():
            if name not in values and not _is_secret_bearing_name(name):
                continue
            if isinstance(value, str) and value:
                values.setdefault(name, set()).add(value)
    for name, process_value in os.environ.items():
        if name not in values and not _is_secret_bearing_name(name):
            continue
        if process_value:
            values.setdefault(name, set()).add(process_value)
    if os.name == "nt" and credential_store.win32cred is None:
        raise RuntimeError("Credential Manager support is unavailable")
    for name in credential_store.SUPPORTED_SECRET_NAMES:
        managed_value = credential_store.read_credential(name)
        if managed_value:
            values[name].add(managed_value)
    return values


def _content_views(content: str) -> set[str]:
    views = {content, content.replace(r'\"', '"')}
    decoded = content
    for _ in range(2):
        decoded = unquote_plus(decoded)
        views.add(decoded)
        views.add(decoded.replace(r'\"', '"'))
    return views


def _encoded_secret_values(value: str) -> set[str]:
    encoded = {
        value,
        quote(value, safe=""),
        quote_plus(value, safe=""),
        json.dumps(value)[1:-1],
    }
    encoded.add(quote(quote(value, safe=""), safe=""))
    encoded.add(quote_plus(quote_plus(value, safe=""), safe=""))
    return encoded


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
        views = _content_views(content)
        for name, values in credentials.items():
            if any(
                encoded in view
                for value in values
                for encoded in _encoded_secret_values(value)
                for view in views
            ):
                credential_hits.add(name)
        for label, pattern in OAUTH_PATTERNS.items():
            if any(pattern.search(view) for view in views):
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
