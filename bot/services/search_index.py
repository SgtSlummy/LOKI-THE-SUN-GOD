from __future__ import annotations

from typing import Any


class SearchIndex:
    def __init__(self, *, enabled: bool):
        self.enabled = enabled

    async def index_message(self, **payload: Any) -> None:
        if not self.enabled:
            return None
        return None

    async def search(self, query: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        return []

