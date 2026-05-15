from __future__ import annotations

import asyncio
import inspect
import json

import dashboard_app
from cogs.loki_npc import LokiNpc
from loki_engine.permissions import MANAGE_GUILD
from loki_npc.memory import member_memory_snapshot, recent_public_memory_for_user, remember_public_message
from utils import db


def _init_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()


def test_dashboard_npc_page_does_not_create_default_disabled_settings_row():
    source = inspect.getsource(dashboard_app.guild_npc)

    assert "INSERT OR IGNORE INTO loki_npc_settings" not in source
    assert "LOKI_NPC_ENABLED" in source


def test_npc_runtime_prefers_dashboard_enabled_setting_over_env(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LOKI_NPC_ENABLED", "true")
    db.sync_exec("INSERT INTO loki_npc_settings(guild_id, enabled) VALUES(?,?)", (10, 0))

    npc = LokiNpc.__new__(LokiNpc)

    assert not npc.enabled_for_guild(10)
    assert npc.enabled_for_guild(999)


def test_npc_runtime_prefers_dashboard_channel_allowlist_over_env(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LOKI_NPC_ALLOWED_CHANNEL_IDS", "999")
    db.sync_exec(
        "INSERT INTO loki_npc_settings(guild_id, enabled, channel_allowlist) VALUES(?,?,?)",
        (10, 1, "222, 333"),
    )

    class Channel:
        id = 222
        parent_id = None
        category_id = None
        parent = None
        category = None

    npc = LokiNpc.__new__(LokiNpc)

    assert npc._channel_allowed(Channel(), guild_id=10)
    assert not npc._channel_allowed(Channel(), guild_id=999)


def test_npc_reset_clears_persisted_persona_without_changing_enabled(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    db.sync_exec(
        "INSERT INTO loki_npc_settings(guild_id, enabled, persona_json) VALUES(?,?,?)",
        (10, 1, json.dumps({"name": "Custom LOKI", "tone": "too custom"})),
    )

    class Permissions:
        value = MANAGE_GUILD

    class Author:
        id = 42
        guild_permissions = Permissions()

    class Guild:
        id = 10

    class Ctx:
        author = Author()
        guild = Guild()

        def __init__(self):
            self.messages: list[str] = []

        async def send(self, message):
            self.messages.append(message)

    npc = LokiNpc.__new__(LokiNpc)
    ctx = Ctx()

    asyncio.run(LokiNpc.npc_reset.callback(npc, ctx))

    row = db.sync_one("SELECT enabled, persona_json FROM loki_npc_settings WHERE guild_id=?", (10,))
    assert row["persona_json"] == ""
    assert row["enabled"] == 1
    assert "reset" in ctx.messages[-1].lower()


def test_npc_reset_without_existing_row_preserves_env_fallback(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LOKI_NPC_ENABLED", "true")

    class Permissions:
        value = MANAGE_GUILD

    class Author:
        id = 42
        guild_permissions = Permissions()

    class Guild:
        id = 10

    class Ctx:
        author = Author()
        guild = Guild()

        def __init__(self):
            self.messages: list[str] = []

        async def send(self, message):
            self.messages.append(message)

    npc = LokiNpc.__new__(LokiNpc)
    ctx = Ctx()

    assert npc.enabled_for_guild(10)
    asyncio.run(LokiNpc.npc_reset.callback(npc, ctx))

    assert db.sync_one("SELECT * FROM loki_npc_settings WHERE guild_id=?", (10,)) is None
    assert npc.enabled_for_guild(10)
    assert "reset" in ctx.messages[-1].lower()


def test_npc_status_reports_guild_database_state(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LOKI_NPC_ENABLED", "true")
    db.sync_exec("INSERT INTO loki_npc_settings(guild_id, enabled) VALUES(?,?)", (10, 0))

    class Guild:
        id = 10

    class Ctx:
        guild = Guild()

        def __init__(self):
            self.messages: list[str] = []

        async def send(self, message):
            self.messages.append(message)

    npc = LokiNpc.__new__(LokiNpc)
    ctx = Ctx()

    asyncio.run(LokiNpc.npc_status.callback(npc, ctx))

    assert "**disabled**" in ctx.messages[-1]


def test_member_memory_snapshot_is_redacted_bounded_and_user_scoped(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)

    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="likes synthwave and token abc.def.ghi")
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="email me at user@example.com")
    remember_public_message(guild_id=10, channel_id=20, user_id=31, content="other member")

    recent = recent_public_memory_for_user(guild_id=10, user_id=30, limit=1)
    snapshot = member_memory_snapshot(guild_id=10, user_id=30, limit=5)

    assert len(recent) == 1
    assert snapshot["guild_id"] == 10
    assert snapshot["user_id"] == 30
    assert snapshot["entry_count"] == 2
    assert len(snapshot["recent"]) == 2
    assert "other member" not in " ".join(snapshot["recent"])
    assert "user@example.com" not in " ".join(snapshot["recent"])
    assert "abc.def.ghi" not in " ".join(snapshot["recent"])
    assert "[email]" in " ".join(snapshot["recent"])
    assert "[secret]" in " ".join(snapshot["recent"])
