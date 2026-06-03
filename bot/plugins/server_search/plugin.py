from __future__ import annotations

from bot.models.plugin import ToolDefinition
from bot.plugins.base import BasePlugin, PluginSlot


class ServerSearchPlugin(BasePlugin):
    name = "server_search"
    slot = PluginSlot.SERVER_SEARCH
    version = "0.1.0"
    enabled_by_default = False
    dependencies: list[str] = []
    config_schema = {
        "commands": ["/search", "/find"],
        "stores": ["indexed_messages"],
        "requires_explicit_enable": True,
    }

    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_discord_messages",
                description="Future permission-aware search over indexed Discord messages.",
                parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "stub": True}

