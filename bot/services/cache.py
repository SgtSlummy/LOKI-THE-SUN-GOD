from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float | None


class MemoryCache:
    def __init__(self):
        self._values: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at < monotonic():
            self._values.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        expires_at = monotonic() + ttl_seconds if ttl_seconds is not None else None
        self._values[key] = CacheEntry(value=value, expires_at=expires_at)

