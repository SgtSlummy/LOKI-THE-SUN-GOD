from __future__ import annotations

from enum import Enum
from typing import Any

from bot.models.plugin import ToolDefinition


class PluginSlot(str, Enum):
    RELAY_CORE = "relay_core"
    MEDIA_RESOLVER = "media_resolver"
    LLM_CHAT = "llm_chat"
    SERVER_SEARCH = "server_search"
    AUTONOMOUS_CURATOR = "autonomous_curator"
    MUSIC = "music"
    MODERATION_AUDIT = "moderation_audit"
    ADMIN_CONFIG = "admin_config"


class BasePlugin:
    name: str
    slot: PluginSlot
    version: str
    enabled_by_default: bool
    dependencies: list[str]
    config_schema: dict[str, Any]

    async def setup(self, bot: Any, services: dict[str, Any]) -> None:
        return None

    async def teardown(self) -> None:
        return None

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value}

    def commands(self) -> list[Any]:
        return []

    def event_subscriptions(self) -> list[str]:
        return []

    def tools(self) -> list[ToolDefinition]:
        return []

