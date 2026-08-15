from __future__ import annotations

import os
import sys
from pathlib import Path

from utils import credential_store

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))


def app_root() -> Path:
    override = os.getenv("LOKI_APP_ROOT")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def bundle_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def app_path(*parts: str) -> Path:
    return app_root().joinpath(*parts)


def stable_env_path() -> Path | None:
    if os.name != "nt":
        return None
    program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / "Loki" / "config" / "lokithesungod.env"


def env_candidates() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    explicit = os.getenv("LOKI_ENV_PATH")
    for candidate in (
        Path(explicit) if explicit else None,
        stable_env_path(),
        app_path(".env"),
        Path.cwd() / ".env",
        bundle_path(".env"),
    ):
        if candidate is None:
            continue
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(candidate)
    return candidates


def load_app_dotenv(*, override: bool = False) -> Path | None:
    """Load config, then overlay approved Credential Manager secrets.

    ``override`` remains accepted for legacy callers, but the managed precedence
    policy never permits a dotenv value to replace a preexisting process value.
    """

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    loaded_path: Path | None = None
    if load_dotenv is not None:
        for candidate in env_candidates():
            if candidate.exists():
                load_dotenv(candidate, override=False)
                loaded_path = candidate
                break
        else:
            load_dotenv(override=False)

    os.environ.update(credential_store.load_credentials())
    return loaded_path
