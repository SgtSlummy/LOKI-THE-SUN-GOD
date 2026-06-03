from __future__ import annotations

from typing import Any

from bot.plugins.base import BasePlugin, PluginSlot


class MediaResolverPlugin(BasePlugin):
    name = "media_resolver"
    slot = PluginSlot.MEDIA_RESOLVER
    version = "0.1.0"
    enabled_by_default = True
    dependencies: list[str] = []
    config_schema = {
        "media_mode": {"type": "string", "enum": ["clean", "button", "native_unfurl"]},
        "media_link_buttons": {"type": "boolean"},
    }

    async def setup(self, bot: Any, services: dict[str, Any]) -> None:
        return None

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "resolver": "ready"}

