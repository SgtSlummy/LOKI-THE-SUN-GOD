from __future__ import annotations

import time

from loki_memory.camelot_records import make_camelot_record, upsert_camelot_record
from utils import db, operator_surface


def _init_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "mcp-memory-tools.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_sync()
    return db_path


def _insert_public_memory(*, created_at: int | None = None) -> None:
    now = created_at or int(time.time())
    db.sync_exec(
        """
        INSERT INTO loki_memory_entries(
            guild_id, channel_id, user_id, redacted_content, source_url, confidence, created_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            10,
            20,
            30,
            "Solar DJ keeps token sk-unsafeunsafe and email solar@example.com out of exports.",
            "https://discord.example/private-source",
            0.8,
            now,
        ),
    )


def test_mcp_memory_search_is_redacted_and_excludes_source_urls(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_public_memory()

    payload = operator_surface.loki_memory_search(guild_id=10, query="solar", user_id=30, limit=5)

    assert payload["total"] == 1
    assert payload["source_url_included"] is False
    entry = payload["entries"][0]
    assert "source_url" not in entry
    assert "sk-unsafeunsafe" not in entry["redacted_content"]
    assert "solar@example.com" not in entry["redacted_content"]
    assert "[secret]" in entry["redacted_content"]
    assert "[email]" in entry["redacted_content"]


def test_mcp_memory_search_rejects_sensitive_query_oracles(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_public_memory()

    token_payload = operator_surface.loki_memory_search(guild_id=10, query="sk-unsafeunsafe", user_id=30, limit=5)
    email_payload = operator_surface.loki_memory_search(guild_id=10, query="solar@example.com", user_id=30, limit=5)

    assert token_payload["query"] == "[redacted]"
    assert token_payload["total"] == 0
    assert token_payload["entries"] == []
    assert email_payload["query"] == "[redacted]"
    assert email_payload["total"] == 0
    assert email_payload["entries"] == []


def test_mcp_memory_previews_do_not_mutate_rows_or_create_audit(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_public_memory()

    export_payload = operator_surface.loki_memory_export_preview(guild_id=10, user_id=30, limit=5)
    delete_payload = operator_surface.loki_memory_delete_preview(guild_id=10, user_id=30)

    assert export_payload["entry_count"] == 1
    assert export_payload["audit_receipt_created"] is False
    assert export_payload["source_url_included"] is False
    assert "source_url" not in export_payload["entries"][0]
    assert delete_payload["would_delete_count"] == 1
    assert delete_payload["deleted"] is False
    assert delete_payload["audit_receipt_created"] is False
    assert db.sync_one("SELECT COUNT(*) AS c FROM loki_memory_entries WHERE guild_id=?", (10,))["c"] == 1
    assert db.sync_one("SELECT COUNT(*) AS c FROM loki_audit_receipts WHERE guild_id=?", (10,))["c"] == 0


def test_mcp_camelot_export_uses_non_shadowing_schema_path(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    record = make_camelot_record(
        record_id="concept-mcp-memory-tools",
        name="MCP Memory Tools",
        entity_type="concept",
        summary="Read-only MCP memory preview tools.",
        sources=["tests/test_loki_mcp_memory_tools.py"],
        sector_links=["Knowledge Management and Retrieval"],
        status="active",
    )
    upsert_camelot_record(record)

    payload = operator_surface.loki_camelot_export(entity_type="concept", status="active", limit=5)

    assert payload["schema_path"] == "docs/schemas/camelot-wing.schema.json"
    assert payload["record_count"] == 1
    assert payload["records"][0]["id"] == "concept-mcp-memory-tools"
