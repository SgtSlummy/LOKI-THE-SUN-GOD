from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError

from bot.settings import Settings


def _safe_int(value: Any, *, default: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(0, parsed)
    if maximum is not None:
        parsed = min(parsed, max(0, maximum))
    return parsed


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
        return await self._post_run(
            prompt=prompt,
            context={
                "source": "discord",
                "user_id": user_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
            },
            execute=self.settings.faust_agi_execute,
        )

    async def run_continuation(
        self,
        *,
        prompt: str,
        parent_run_id: str | None,
        guild_id: int | None,
        channel_id: int | None,
    ) -> dict[str, Any]:
        return await self._post_run(
            prompt=prompt,
            context={
                "source": "discord_unprompted",
                "user_id": None,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "parent_run_id": parent_run_id,
            },
            execute=False,
        )

    async def run_maintenance(
        self,
        *,
        prompt: str,
        user_id: int | None,
        guild_id: int | None,
        channel_id: int | None,
    ) -> dict[str, Any]:
        return await self._post_run(
            prompt=prompt,
            context={
                "source": "discord_admin_maintenance",
                "user_id": user_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
            },
            execute=True,
            target_component=self.settings.faust_agi_admin_target_component,
            active_workspace=self.settings.faust_agi_admin_workspace,
        )

    async def _post_run(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        execute: bool,
        target_component: str | None = None,
        active_workspace: str | None = None,
    ) -> dict[str, Any]:
        if not self.available:
            raise FaustAGIError("FAUST_AGI_BASE_URL is not configured.")

        base_url = self.settings.faust_agi_base_url.rstrip("/")
        run_path = self.settings.faust_agi_run_path or "/api/faust/run"
        url = f"{base_url}{run_path if run_path.startswith('/') else '/' + run_path}"
        payload = {
            "prompt": prompt,
            "context": context,
            "selected_mode": "chat",
            "active_workspace": active_workspace if active_workspace is not None else "",
            "target_component": target_component if target_component is not None else self.settings.faust_agi_target_component,
            "provider": self.settings.faust_agi_provider,
            "route_mode": self.settings.faust_agi_route_mode,
            "execute": execute,
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
            "continue_unprompted": data.get("continue_unprompted") is True,
            "continuation_prompt": data.get("continuation_prompt") or None,
            "continuation_delay_seconds": _safe_int(
                data.get("continuation_delay_seconds"), maximum=self.settings.faust_agi_unprompted_max_delay_seconds
            ),
        }
