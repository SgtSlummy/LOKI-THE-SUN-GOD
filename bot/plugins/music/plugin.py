from __future__ import annotations

from bot.plugins.base import BasePlugin, PluginSlot


class MusicPlugin(BasePlugin):
    name = "music"
    slot = PluginSlot.MUSIC
    version = "0.1.0"
    enabled_by_default = False
    dependencies: list[str] = []
    config_schema = {
        "voice": True,
        "queue": True,
        "controls": ["play", "pause", "skip", "volume"],
        "provider_adapters": [],
        "implemented": False,
    }

    async def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "stub": True}

