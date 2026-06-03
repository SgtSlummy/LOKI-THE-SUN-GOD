from __future__ import annotations

import logging
from typing import Any

from bot.plugins.base import BasePlugin, PluginSlot
from bot.settings import Settings


class PluginRegistryError(RuntimeError):
    pass


class PluginRegistry:
    def __init__(self, *, settings: Settings, services: dict[str, Any], plugins: list[BasePlugin]):
        self.settings = settings
        self.services = services
        self.plugins = plugins
        self.active_plugins: list[BasePlugin] = []
        self.logger = logging.getLogger("loki.plugins")

    def resolve_active_plugins(self) -> list[BasePlugin]:
        if self.settings.enabled_plugins_override is not None:
            enabled_names = self.settings.enabled_plugins_override
            active = [plugin for plugin in self.plugins if plugin.name in enabled_names]
        else:
            enabled_names = self.settings.enabled_plugin_names or set()
            active = [
                plugin
                for plugin in self.plugins
                if plugin.enabled_by_default or plugin.name in enabled_names
            ]

        if len(active) > self.settings.max_active_plugins:
            raise PluginRegistryError(
                f"{len(active)} plugins enabled, exceeding MAX_ACTIVE_PLUGINS={self.settings.max_active_plugins}."
            )

        by_slot: dict[PluginSlot, BasePlugin] = {}
        for plugin in active:
            existing = by_slot.get(plugin.slot)
            if existing is not None:
                raise PluginRegistryError(
                    f"Plugin slot conflict for slot {plugin.slot.value}: {existing.name} and {plugin.name}."
                )
            by_slot[plugin.slot] = plugin

        self._validate_dependencies(active)
        self.active_plugins = active
        return active

    async def setup_plugins(self, bot: Any) -> None:
        active = self.resolve_active_plugins()
        database = self.services.get("database")
        for plugin in active:
            self.logger.info("Setting up plugin %s in slot %s", plugin.name, plugin.slot.value)
            await plugin.setup(bot, self.services)
            if database is not None:
                await database.upsert_plugin_state(
                    plugin_name=plugin.name,
                    slot=plugin.slot.value,
                    enabled=True,
                    config=plugin.config_schema,
                )

    async def teardown_plugins(self) -> None:
        for plugin in reversed(self.active_plugins):
            await plugin.teardown()

    async def healthcheck(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for plugin in self.active_plugins:
            try:
                checks.append(await plugin.healthcheck())
            except Exception as exc:
                checks.append({"ok": False, "plugin": plugin.name, "error": str(exc)})
        return checks

    async def reload_plugin(self, plugin_name: str, bot: Any) -> dict[str, Any]:
        if self.settings.bot_env != "development":
            return {"ok": False, "message": "Hot reload is only enabled in development."}
        plugin = next((item for item in self.active_plugins if item.name == plugin_name), None)
        if plugin is None:
            return {"ok": False, "message": f"Plugin {plugin_name} is not active."}
        await plugin.teardown()
        await plugin.setup(bot, self.services)
        return {"ok": True, "message": f"Reloaded {plugin_name}."}

    def active_plugin_names(self) -> list[str]:
        return [plugin.name for plugin in self.active_plugins]

    def _validate_dependencies(self, active: list[BasePlugin]) -> None:
        active_names = {plugin.name for plugin in active}
        for plugin in active:
            missing = [dependency for dependency in plugin.dependencies if dependency not in active_names]
            if missing:
                raise PluginRegistryError(f"Plugin {plugin.name} is missing dependencies: {', '.join(missing)}")
