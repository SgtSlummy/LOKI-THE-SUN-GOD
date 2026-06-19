import logging

import pytest

import bot.main as main
from bot.settings import Settings


class FakeForbidden(Exception):
    pass


class FakeCommandTree:
    def __init__(self):
        self.copied_guild_id = None
        self.sync_calls = []

    def copy_global_to(self, *, guild):
        self.copied_guild_id = guild.id

    async def sync(self, *, guild=None):
        self.sync_calls.append(guild)
        if guild is not None:
            raise FakeForbidden("missing access")
        return ["global-command"]


class FakeDatabase:
    async def healthcheck(self):
        return True


class FakeLlmClient:
    available = True


class FakeFaustClient:
    available = True


class FakeRegistry:
    def active_plugin_names(self):
        return ["relay_core", "llm_chat"]

    async def healthcheck(self):
        return {"relay_core": {"ok": True}, "llm_chat": {"ok": True}}


class FakeBot:
    def is_closed(self):
        return False

    def is_ready(self):
        return True


@pytest.mark.asyncio
async def test_guild_command_sync_forbidden_falls_back_to_global_sync(monkeypatch):
    monkeypatch.setattr(main.discord, "Forbidden", FakeForbidden)
    tree = FakeCommandTree()

    synced = await main.sync_application_commands(
        tree=tree,
        settings=Settings(discord_guild_id=123),
        logger=logging.getLogger("test"),
    )

    assert tree.copied_guild_id == 123
    assert len(tree.sync_calls) == 2
    assert tree.sync_calls[0].id == 123
    assert tree.sync_calls[1] is None
    assert synced == ["global-command"]


@pytest.mark.asyncio
async def test_health_payload_includes_safe_llm_status():
    payload = await main.build_health_payload(
        bot=FakeBot(),
        services={"database": FakeDatabase(), "llm_client": FakeLlmClient(), "faust_agi_client": FakeFaustClient()},
        registry=FakeRegistry(),
        settings=Settings(openai_model="gpt-5.5", faust_agi_enabled=True, faust_agi_route_mode="cloud_first"),
    )

    assert payload["ok"] is True
    assert payload["discord_connected"] is True
    assert payload["db_connected"] is True
    assert payload["active_plugins"] == ["relay_core", "llm_chat"]
    assert payload["llm"] == {
        "provider": "openai",
        "configured": True,
        "model": "gpt-5.5",
    }
    assert payload["faust_agi"] == {
        "configured": True,
        "enabled": True,
        "route_mode": "cloud_first",
        "provider": "",
    }
