from __future__ import annotations

import json

import pytest

from loki_memory.camelot_records import (
    CamelotRecordError,
    export_camelot_records,
    get_camelot_record,
    import_camelot_records,
    make_camelot_record,
    member_snapshot_to_camelot_record,
    upsert_camelot_record,
    validate_camelot_record,
)
from loki_npc.memory import member_memory_snapshot, remember_public_message
from utils import db


def _init_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()


def _record(**overrides):
    base = make_camelot_record(
        record_id="discord-member-10-30",
        name="Solar DJ",
        entity_type="user",
        summary="Discord member public memory profile.",
        details="Likes modular synths.",
        sources=["loki_memory_entries:redacted_public_messages"],
        related_entities=["discord-guild-10"],
        tags=["discord-member", "camelot"],
        retrieval_keywords=["30", "Solar DJ"],
        sector_links=["Camelot Memory Palace"],
        upgrade_relevance=6,
        priority_score=5,
        confidence_score=7,
        risk_score=3,
        status="active",
        action_items=[],
        test_links=["tests/test_camelot_records.py"],
        commit_links=[],
        created_at="2026-05-16T00:00:00Z",
        updated_at="2026-05-16T00:00:00Z",
        last_reviewed_at="2026-05-16T00:00:00Z",
    )
    base.update(overrides)
    return base


def test_validate_camelot_record_matches_schema_shape_and_redacts():
    record = _record(
        summary="email user@example.com token abc.def.ghi",
        sources=["https://example.test/?token abc.def.ghi"],
        confidence_score=99,
        risk_score=-4,
    )

    normalized = validate_camelot_record(record)

    assert set(normalized) == {
        "id",
        "name",
        "entity_type",
        "summary",
        "details",
        "sources",
        "related_entities",
        "tags",
        "retrieval_keywords",
        "sector_links",
        "upgrade_relevance",
        "priority_score",
        "confidence_score",
        "risk_score",
        "status",
        "action_items",
        "test_links",
        "commit_links",
        "created_at",
        "updated_at",
        "last_reviewed_at",
    }
    serialized = json.dumps(normalized, sort_keys=True)
    assert "user@example.com" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "[email]" in serialized
    assert "[secret]" in serialized
    assert normalized["confidence_score"] == 10
    assert normalized["risk_score"] == 0


@pytest.mark.parametrize(
    "bad_update, expected",
    [
        ({"entity_type": "private_dm"}, "unsupported Camelot entity_type"),
        ({"status": "leaky"}, "unsupported Camelot status"),
        ({"unexpected": "field"}, "unexpected Camelot fields"),
    ],
)
def test_validate_camelot_record_rejects_schema_drift(bad_update, expected):
    record = _record(**bad_update)

    with pytest.raises(CamelotRecordError, match=expected):
        validate_camelot_record(record)


def test_upsert_get_export_and_import_camelot_records(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    stored = upsert_camelot_record(_record(), actor_id=40)

    assert get_camelot_record(stored["id"]) == stored
    row = db.sync_one("SELECT actor_id, payload_json FROM loki_camelot_records WHERE id=?", (stored["id"],))
    assert row["actor_id"] == 40
    assert json.loads(row["payload_json"])["name"] == "Solar DJ"

    exported = export_camelot_records(entity_type="user")
    assert exported["schema"] == "docs/schemas/camelot-wing.schema.json"
    assert exported["record_count"] == 1
    assert exported["records"][0]["id"] == stored["id"]

    imported = import_camelot_records(exported, actor_id=41)
    assert imported == {"imported_count": 1, "record_ids": [stored["id"]]}
    row = db.sync_one("SELECT actor_id FROM loki_camelot_records WHERE id=?", (stored["id"],))
    assert row["actor_id"] == 41


def test_member_snapshot_to_camelot_record_uses_only_redacted_public_memory(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="likes synthwave user@example.com")
    remember_public_message(guild_id=10, channel_id=20, user_id=30, content="token abc.def.ghi")
    snapshot = member_memory_snapshot(guild_id=10, user_id=30)

    record = member_snapshot_to_camelot_record(guild_id=10, user_id=30, display_name="Solar DJ", snapshot=snapshot)
    stored = upsert_camelot_record(record)

    assert stored["id"] == "discord-member-10-30"
    assert stored["entity_type"] == "user"
    assert stored["status"] == "active"
    assert "2 redacted snippets" in stored["summary"]
    serialized = json.dumps(stored, sort_keys=True)
    assert "user@example.com" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "[email]" in serialized
    assert "[secret]" in serialized
    assert stored["sources"] == ["loki_memory_entries:redacted_public_messages"]
    assert "Camelot Memory Palace" in stored["sector_links"]


def test_import_camelot_records_requires_records_list(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)

    with pytest.raises(CamelotRecordError, match="records list"):
        import_camelot_records({"records": "not-a-list"})


def test_import_camelot_records_prevalidates_batch_before_writing(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    good = _record(id="good-record")
    bad = _record(id="bad-record", status="invalid")

    with pytest.raises(CamelotRecordError, match="unsupported Camelot status"):
        import_camelot_records({"records": [good, bad]}, actor_id=40)

    assert get_camelot_record("good-record") is None
    assert db.sync_one("SELECT * FROM loki_camelot_records") is None


def test_member_snapshot_to_camelot_record_rejects_mismatched_snapshot_identity():
    snapshot = {"guild_id": 999, "user_id": 30, "entry_count": 0, "recent": []}

    with pytest.raises(CamelotRecordError, match="guild_id"):
        member_snapshot_to_camelot_record(guild_id=10, user_id=30, display_name="Solar DJ", snapshot=snapshot)
