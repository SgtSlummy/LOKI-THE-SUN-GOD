from __future__ import annotations

import time
from types import SimpleNamespace

import desktop_app
from loki_memory.camelot_records import make_camelot_record, upsert_camelot_record
from utils import db


def _init_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "dashboard-memory-api.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_sync()
    return db_path


def _make_client():
    app = desktop_app.make_app(SimpleNamespace(services={}), {"dashboards": []})
    app.config.update(TESTING=True)
    return app.test_client()


def _insert_public_memory() -> None:
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
            "Solar DJ prefers synthwave and keeps solar@example.com private.",
            "https://discord.example/source-message",
            0.9,
            int(time.time()),
        ),
    )


def _insert_camelot_record() -> None:
    upsert_camelot_record(
        make_camelot_record(
            record_id="user-solar-dj",
            name="Solar DJ",
            entity_type="user",
            summary="Discord member music preference profile.",
            sources=["tests/test_dashboard_memory_api.py"],
            tags=["music", "memory"],
            status="active",
        )
    )


def test_desktop_dashboard_memory_search_api_is_redacted(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_public_memory()
    client = _make_client()

    response = client.get("/api/loki/10/memory/search?q=solar&user_id=30&limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["source_url_included"] is False
    assert "source_url" not in payload["entries"][0]
    assert "solar@example.com" not in payload["entries"][0]["redacted_content"]
    assert "[email]" in payload["entries"][0]["redacted_content"]


def test_desktop_dashboard_memory_preview_apis_are_read_only(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_public_memory()
    client = _make_client()

    export_response = client.get("/api/loki/10/memory/export-preview?user_id=30&limit=5")
    delete_response = client.get("/api/loki/10/memory/delete-preview?user_id=30")

    assert export_response.status_code == 200
    assert delete_response.status_code == 200
    assert export_response.get_json()["audit_receipt_created"] is False
    assert delete_response.get_json()["deleted"] is False
    assert delete_response.get_json()["audit_receipt_created"] is False
    assert db.sync_one("SELECT COUNT(*) AS c FROM loki_memory_entries WHERE guild_id=?", (10,))["c"] == 1
    assert db.sync_one("SELECT COUNT(*) AS c FROM loki_audit_receipts WHERE guild_id=?", (10,))["c"] == 0


def test_desktop_dashboard_camelot_export_api(monkeypatch, tmp_path):
    _init_temp_db(monkeypatch, tmp_path)
    _insert_camelot_record()
    client = _make_client()

    response = client.get("/api/loki/camelot/export?entity_type=user&status=active&limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_path"] == "docs/schemas/camelot-wing.schema.json"
    assert payload["record_count"] == 1
    assert payload["records"][0]["id"] == "user-solar-dj"


def test_desktop_dashboard_exposes_memory_preview_panel():
    client = _make_client()

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Memory previews" in html
    assert "loadMemoryPreviews" in html
    assert "this.loadMemoryPreviews();" not in html
    assert "/memory/export-preview" in html
    assert "/api/loki/camelot/export" in html
