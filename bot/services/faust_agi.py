from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError

from bot.settings import Settings


class FaustAGIError(RuntimeError):
    pass


class FaustAGIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return self.settings.faust_agi_enabled and bool(self.settings.faust_agi_base_url)

    async def run_council(
        self,
        *,
        prompt: str,
        user_id: int | None,
        guild_id: int | None,
        channel_id: int | None,
    ) -> dict[str, Any]:
        if not self.available:
            raise FaustAGIError("FAUST_AGI_BASE_URL is not configured.")

        base_url = self.settings.faust_agi_base_url.rstrip("/")
        run_path = self.settings.faust_agi_run_path or "/api/faust/run"
        url = f"{base_url}{run_path if run_path.startswith('/') else '/' + run_path}"
        payload = {
            "prompt": prompt,
            "context": {
                "source": "discord",
                "user_id": user_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
            },
            "selected_mode": "chat",
            "active_workspace": "",
            "target_component": self.settings.faust_agi_target_component,
            "provider": self.settings.faust_agi_provider,
            "route_mode": self.settings.faust_agi_route_mode,
            "execute": self.settings.faust_agi_execute,
        }
        headers = {"Accept": "application/json"}
        if self.settings.faust_agi_api_key:
            headers["Authorization"] = f"Bearer {self.settings.faust_agi_api_key}"

        timeout = ClientTimeout(total=self.settings.faust_agi_timeout_seconds)
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    if response.status >= 400:
                        raise FaustAGIError(
                            f"Faust AGI request failed with status {response.status}: {response_text[:500]}"
                        )
                    try:
                        data = await response.json()
                    except (ContentTypeError, ValueError) as exc:
                        raise FaustAGIError("Faust AGI returned a non-JSON response.") from exc
        except asyncio.TimeoutError as exc:
            raise FaustAGIError("Faust AGI request timed out.") from exc
        except ClientError as exc:
            raise FaustAGIError(f"Faust AGI request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise FaustAGIError("Faust AGI returned an unexpected response shape.")
        return self._normalize_response(data)

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        text = data.get("output") or data.get("response") or "Faust AGI completed without text output."
        return {
            "text": str(text),
            "run_id": data.get("run_id"),
            "fallback_used": bool(data.get("fallback_used")),
        }
