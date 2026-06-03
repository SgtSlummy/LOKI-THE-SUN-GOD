from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from bot.settings import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def responses_create(self, *, input_text: str, tools: list[dict[str, Any]] | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        return await self._client.responses.create(
            model=self.settings.openai_model,
            input=input_text,
            tools=tools or [],
        )

