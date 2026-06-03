from __future__ import annotations

from bot.models.plugin import ToolDefinition
from bot.plugins.base import BasePlugin, PluginSlot


class LLMChatPlugin(BasePlugin):
    name = "llm_chat"
    slot = PluginSlot.LLM_CHAT
    version = "0.1.0"
    enabled_by_default = False
    dependencies: list[str] = []
    config_schema = {
        "commands": ["/ask", "/talk", "/summarize"],
        "openai_responses_api": True,
    }

    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="discord_server_lookup",
                description="Future controlled lookup over permitted Discord server content.",
                parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "stub": True}

