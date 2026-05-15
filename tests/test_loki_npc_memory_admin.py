from __future__ import annotations

import asyncio
import json
import time

from cogs.loki_npc import LokiNpc
from loki_engine.permissions import MANAGE_GUILD
from loki_npc.memory import export_user_memory, recent_public_memory_for_user, remember_public_message
from utils import db


def _init_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()


def _ctx(*, permissions: int, interaction=object()):
    class Permissions:
        value = permissions

    class Guild:
        id = 10

    class Author:
        id = 40
        guild_permissions = Permissions()

    class Ctx:
        guild = Guild()
        author = Author()

        def __init__(self):
            self.interaction = interaction
            self.messages: list[str] = []
            self.send_kwargs: list[dict] = []

        async def send(self, message, **kwargs):
            self.messages.append(message)
            self.send_kwargs.append(kwargs)

    return Ctx()


class Member:
    id = 30
    display_name = "Solar DJ"


def _json_payload_from_message(message: str) -> dict:
    return json.loads(message.split("```json\n", 1)[1].split("\n```", 1)[0])


def test_export_user_memory_returns_redacted_rows_and_records_audit(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="email user@example.com token abc.def.ghi")

    payload = export_user_memory(guild_id=10, user_id=30, actor_id=40, limit=10)

    assert payload["guild_id"] == 10
    assert payload["user_id"] == 30
    assert payload["actor_id"] == 40
    assert payload["entry_count"] == 1
    assert payload["entries"][0]["redacted_content"] == "email [email] [secret]"
    assert "user@example.com" not in str(payload)
    assert "abc.def.ghi" not in str(payload)
    receipt = db.sync_one("SELECT * FROM loki_audit_receipts WHERE guild_id=?", (10,))
    assert receipt["actor_id"] == 40
    assert receipt["action"] == "npc_memory_export"
    assert receipt["allowed"] == 1
    assert "user_id=30" in receipt["details"]


def test_export_user_memory_defensively_redacts_legacy_rows(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    db.sync_exec(
        """
        INSERT INTO loki_memory_entries(
            guild_id, channel_id, user_id, redacted_content, source_url, confidence, created_at
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            10,
            20,
            30,
            "legacy user@example.com token abc.def.ghi",
            "https://example.test/?token=secret",
            0.4,
            int(time.time()),
        ),
    )

    payload = export_user_memory(guild_id=10, user_id=30, actor_id=40, limit=10)

    serialized = json.dumps(payload, sort_keys=True)
    assert "user@example.com" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "token=secret" not in serialized
    assert payload["entries"][0]["redacted_content"] == "legacy [email] [secret]"
    assert "source_url" not in payload["entries"][0]


def test_npc_memory_export_command_requires_manage_guild(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=0)

    asyncio.run(LokiNpc.npc_memory_export.callback(npc, ctx, Member()))

    assert "requires" in ctx.messages[-1].lower()
    assert ctx.send_kwargs[-1]["ephemeral"] is True
    assert db.sync_one("SELECT * FROM loki_audit_receipts WHERE guild_id=?", (10,)) is None


def test_npc_memory_export_command_sends_private_redacted_json_and_audit(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="likes modular and user@example.com")
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=MANAGE_GUILD)

    asyncio.run(LokiNpc.npc_memory_export.callback(npc, ctx, Member()))

    output = ctx.messages[-1]
    assert "loki public memory export" in output.lower()
    assert "Solar DJ" in output
    assert "[email]" in output
    assert "user@example.com" not in output
    assert ctx.send_kwargs[-1]["ephemeral"] is True
    assert ctx.send_kwargs[-1]["allowed_mentions"].everyone is False
    exported = _json_payload_from_message(output)
    assert exported["entry_count"] == 1
    assert exported["entries"][0]["redacted_content"] == "likes modular and [email]"
    receipt = db.sync_one("SELECT action FROM loki_audit_receipts WHERE guild_id=?", (10,))
    assert receipt["action"] == "npc_memory_export"


def test_npc_memory_export_command_keeps_large_payload_json_parseable(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    for index in range(20):
        remember_public_message(guild_id=10, channel_id=20, user_id=30, content=f"entry {index} " + "x" * 300)
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=MANAGE_GUILD)

    asyncio.run(LokiNpc.npc_memory_export.callback(npc, ctx, Member()))

    output = ctx.messages[-1]
    exported = _json_payload_from_message(output)
    assert exported["truncated"] is True
    assert exported["entry_count"] == 20
    assert len(output) <= 2000


def test_npc_memory_delete_command_purges_member_memory_and_records_audit(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="delete me")
    remember_public_message(guild_id=10, channel_id=20, user_id=31, content="keep me")
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=MANAGE_GUILD)

    asyncio.run(LokiNpc.npc_memory_delete.callback(npc, ctx, Member()))

    assert "deleted 1" in ctx.messages[-1].lower()
    assert recent_public_memory_for_user(guild_id=10, user_id=30, limit=5) == []
    assert recent_public_memory_for_user(guild_id=10, user_id=31, limit=5) == ["keep me"]
    assert ctx.send_kwargs[-1]["ephemeral"] is True
    receipt = db.sync_one("SELECT * FROM loki_audit_receipts WHERE guild_id=?", (10,))
    assert receipt["action"] == "npc_memory_delete"
    assert "deleted=1" in receipt["details"]


def test_npc_memory_delete_command_requires_manage_guild(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="keep me")
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=0)

    asyncio.run(LokiNpc.npc_memory_delete.callback(npc, ctx, Member()))

    assert "requires" in ctx.messages[-1].lower()
    assert recent_public_memory_for_user(guild_id=10, user_id=30, limit=5) == ["keep me"]
    assert db.sync_one("SELECT * FROM loki_audit_receipts WHERE guild_id=?", (10,)) is None


def test_npc_memory_export_prefix_context_rejected_without_audit(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    npc = LokiNpc.__new__(LokiNpc)
    ctx = _ctx(permissions=MANAGE_GUILD, interaction=None)

    asyncio.run(LokiNpc.npc_memory_export.callback(npc, ctx, Member()))

    assert "use /npc memory-export" in ctx.messages[-1].lower()
    assert db.sync_one("SELECT * FROM loki_audit_receipts WHERE guild_id=?", (10,)) is None
