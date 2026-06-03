from __future__ import annotations

from bot.plugins.base import BasePlugin, PluginSlot


class AutonomousCuratorPlugin(BasePlugin):
    name = "autonomous_curator"
    slot = PluginSlot.AUTONOMOUS_CURATOR
    version = "0.1.0"
    enabled_by_default = False
    dependencies = ["server_search", "llm_chat"]
    config_schema = {
        "review_channel_required": True,
        "autopost_default": False,
        "rate_limits": {"cooldown_minutes": 60},
    }

    async def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "stub": True}

