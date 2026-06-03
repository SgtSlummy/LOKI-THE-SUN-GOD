from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class Scheduler:
    def __init__(self):
        self._tasks: list[asyncio.Task[object]] = []

    def create_task(self, coro_factory: Callable[[], Awaitable[object]]) -> None:
        self._tasks.append(asyncio.create_task(coro_factory()))

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

