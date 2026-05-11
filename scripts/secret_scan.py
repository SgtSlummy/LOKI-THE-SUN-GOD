from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".venv", ".mythos", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build"}
SECRET_PATTERNS = [
    re.compile(r"(?i)\bdiscord[_-]?token\s*=\s*[^\s#]+"),
    re.compile(r"\b[MNO][A-Za-z\d_-]{20,}\.[A-Za-z\d_-]{6,}\.[A-Za-z\d_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(client_secret|api_key|password)\s*=\s*['\"]?[A-Za-z0-9._-]{16,}"),
]


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".dll"}:
            continue
        files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        relative = path.relative_to(ROOT)
        if relative in {
            Path("scripts/dashboard_smoke_test.py"),
            Path("scripts/setup_env.ps1"),
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for index, line in enumerate(text.splitlines(), start=1):
            if "your-discord-bot-token" in line or "replace-this" in line or "youshallnotpass" in line:
                continue
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                findings.append(f"{path.relative_to(ROOT)}:{index}: possible secret")
    if findings:
        print("\n".join(findings))
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
