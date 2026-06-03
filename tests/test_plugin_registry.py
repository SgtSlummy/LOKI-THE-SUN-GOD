import pytest

from bot.plugins.base import BasePlugin, PluginSlot
from bot.plugins.registry import PluginRegistry, PluginRegistryError
from bot.settings import Settings


class DummyPlugin(BasePlugin):
    def __init__(self, name: str, slot: PluginSlot, enabled: bool = True):
        self.name = name
        self.slot = slot
        self.version = "0.1.0"
        self.enabled_by_default = enabled
        self.dependencies = []
        self.config_schema = {}


def test_registry_rejects_more_than_max_active_plugins():
    settings = Settings(discord_token="token", max_active_plugins=2)
    plugins = [
        DummyPlugin("relay_core", PluginSlot.RELAY_CORE),
        DummyPlugin("media_resolver", PluginSlot.MEDIA_RESOLVER),
        DummyPlugin("admin_config", PluginSlot.ADMIN_CONFIG),
    ]

    registry = PluginRegistry(settings=settings, services={}, plugins=plugins)

    with pytest.raises(PluginRegistryError, match="MAX_ACTIVE_PLUGINS"):
        registry.resolve_active_plugins()


def test_registry_rejects_slot_conflicts():
    settings = Settings(discord_token="token")
    plugins = [
        DummyPlugin("media_resolver_a", PluginSlot.MEDIA_RESOLVER),
        DummyPlugin("media_resolver_b", PluginSlot.MEDIA_RESOLVER),
    ]

    registry = PluginRegistry(settings=settings, services={}, plugins=plugins)

    with pytest.raises(PluginRegistryError, match="slot"):
        registry.resolve_active_plugins()


def test_registry_includes_exactly_eight_default_slots():
    assert [slot.value for slot in PluginSlot] == [
        "relay_core",
        "media_resolver",
        "llm_chat",
        "server_search",
        "autonomous_curator",
        "music",
        "moderation_audit",
        "admin_config",
    ]

