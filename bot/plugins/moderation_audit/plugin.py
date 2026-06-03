from __future__ import annotations

from typing import Any

from bot.plugins.base import BasePlugin, PluginSlot


class ModerationAuditPlugin(BasePlugin):
    name = "moderation_audit"
    slot = PluginSlot.MODERATION_AUDIT
    version = "0.1.0"
    enabled_by_default = True
    dependencies: list[str] = []
    config_schema = {"audit_log": {"type": "boolean", "default": True}}

    async def setup(self, bot: Any, services: dict[str, Any]) -> None:
        database = services.get("database")
        if database is not None:
            await database.audit(event_type="plugin_started", details={"plugin": self.name})

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value}

