from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLES = [
    ROOT / ".env.example",
    ROOT / "services" / "activity-bridge" / ".env.example",
]

SENSITIVE_KEY = re.compile(
    r"(^|_)(TOKEN|SECRET|PASSWORD|API_KEY|CLIENT_SECRET|PRIVATE_KEY|WEBHOOK|ACCESS_TOKEN|DATABASE_URL)($|_)",
    re.IGNORECASE,
)
REAL_SECRET_PATTERNS = [
    re.compile(r"\b[MNO][A-Za-z\d_-]{20,}\.[A-Za-z\d_-]{6,}\.[A-Za-z\d_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"^[A-Za-z0-9._~+/=-]{32,}$"),
]
SAFE_PLACEHOLDERS = {
    "000000000000000000",
    "change_me",
    "changeme",
    "replace_me",
    "replace_me_or_leave_blank_for_local_testing",
    "replace-this-with-a-long-random-secret",
    "replace_with_shared_dashboard_bridge_token",
    "your-discord-application-client-secret",
    "your-discord-bot-token",
    "youshallnotpass",
}


def test_env_examples_exist() -> None:
    missing = [str(path.relative_to(ROOT)) for path in ENV_EXAMPLES if not path.exists()]
    assert not missing, f"Missing env examples: {missing}"


def test_sensitive_env_examples_use_placeholders() -> None:
    failures: list[str] = []
    for path in ENV_EXAMPLES:
        for line_number, key, value in _iter_env_values(path):
            if not SENSITIVE_KEY.search(key):
                continue
            if _is_safe_placeholder(value):
                continue
            if _looks_like_real_secret(value):
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {key} looks like a real secret")
                continue
            failures.append(f"{path.relative_to(ROOT)}:{line_number}: {key} should use a clear placeholder")

    assert not failures, "\n".join(failures)


def _iter_env_values(path: Path) -> list[tuple[int, str, str]]:
    values: list[tuple[int, str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.append((line_number, key.strip(), value.strip().strip("'\"")))
    return values


def _is_safe_placeholder(value: str) -> bool:
    if not value:
        return True

    normalized = value.lower()
    return normalized in SAFE_PLACEHOLDERS


def _looks_like_real_secret(value: str) -> bool:
    if not value:
        return False
    return any(pattern.search(value) for pattern in REAL_SECRET_PATTERNS)


if __name__ == "__main__":
    test_env_examples_exist()
    test_sensitive_env_examples_use_placeholders()
    print("env example contracts passed")
