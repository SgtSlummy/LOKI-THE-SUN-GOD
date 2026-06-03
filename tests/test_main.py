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
