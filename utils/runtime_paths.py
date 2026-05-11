from __future__ import annotations

import os
import sys
from pathlib import Path

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


def env_candidates() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    explicit = os.getenv("LOKI_ENV_PATH")
    for candidate in (
        Path(explicit) if explicit else None,
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
    from dotenv import load_dotenv

    for candidate in env_candidates():
        if candidate.exists():
            load_dotenv(candidate, override=override)
            return candidate
    load_dotenv(override=override)
    return None
