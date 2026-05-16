from __future__ import annotations

import json
import re
import time
from typing import Any

from utils import db

CAMLOT_RECORD_ENTITY_TYPES = {
    "user",
    "bot",
    "concept",
    "idea",
    "repo",
    "skill",
    "plugin",
    "media",
    "upgrade",
    "test",
    "deployment",
    "mutation",
    "rollback",
}
CAMLOT_RECORD_STATUSES = {"new", "reviewed", "active", "deprecated", "blocked", "complete"}
CAMLOT_REQUIRED_FIELDS = {
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
_LIST_FIELDS = {
    "sources",
    "related_entities",
    "tags",
    "retrieval_keywords",
    "sector_links",
    "action_items",
    "test_links",
    "commit_links",
}
_SCORE_FIELDS = {"upgrade_relevance", "priority_score", "confidence_score", "risk_score"}
_TEXT_FIELDS = {
    "id",
    "name",
    "entity_type",
    "summary",
    "details",
    "status",
    "created_at",
    "updated_at",
    "last_reviewed_at",
}
_SECRETISH_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}|token\s+[A-Za-z0-9._-]+)"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class CamelotRecordError(ValueError):
    """Raised when a Camelot record fails the checked-in schema contract."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _redact_text(value: Any) -> str:
    text = str(value or "")
    text = _EMAIL_RE.sub("[email]", text)
    return _SECRETISH_RE.sub("[secret]", text)


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    else:
        try:
            raw_items = list(value)
        except TypeError:
            raw_items = [value]
    cleaned: list[str] = []
    for item in raw_items:
        text = _redact_text(item).strip()
        if text:
            cleaned.append(text[:500])
    return cleaned


def _score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(10.0, number))


def validate_camelot_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a schema-shaped, redacted Camelot wing record or raise.

    The checked-in JSON schema is intentionally dependency-free at runtime, so this
    validator enforces the same required fields, enum values, array shapes, score
    bounds, and no-extra-properties rule directly.
    """
    unknown = set(record) - CAMLOT_REQUIRED_FIELDS
    if unknown:
        raise CamelotRecordError(f"unexpected Camelot fields: {', '.join(sorted(unknown))}")

    missing = CAMLOT_REQUIRED_FIELDS - set(record)
    if missing:
        raise CamelotRecordError(f"missing Camelot fields: {', '.join(sorted(missing))}")

    normalized: dict[str, Any] = {}
    for field in sorted(_TEXT_FIELDS):
        normalized[field] = _redact_text(record[field]).strip()

    if not normalized["id"]:
        raise CamelotRecordError("Camelot record id is required")
    if not normalized["name"]:
        raise CamelotRecordError("Camelot record name is required")
    if normalized["entity_type"] not in CAMLOT_RECORD_ENTITY_TYPES:
        raise CamelotRecordError(f"unsupported Camelot entity_type: {normalized['entity_type']}")
    if normalized["status"] not in CAMLOT_RECORD_STATUSES:
        raise CamelotRecordError(f"unsupported Camelot status: {normalized['status']}")

    for field in sorted(_LIST_FIELDS):
        normalized[field] = _clean_list(record[field])
    for field in sorted(_SCORE_FIELDS):
        normalized[field] = _score(record[field])

    return {field: normalized[field] for field in sorted(CAMLOT_REQUIRED_FIELDS)}


def make_camelot_record(
    *,
    record_id: str,
    name: str,
    entity_type: str,
    summary: str,
    details: str = "",
    sources: list[str] | None = None,
    related_entities: list[str] | None = None,
    tags: list[str] | None = None,
    retrieval_keywords: list[str] | None = None,
    sector_links: list[str] | None = None,
    upgrade_relevance: float = 0,
    priority_score: float = 0,
    confidence_score: float = 0,
    risk_score: float = 0,
    status: str = "new",
    action_items: list[str] | None = None,
    test_links: list[str] | None = None,
    commit_links: list[str] | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    last_reviewed_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or _now()
    return validate_camelot_record(
        {
            "id": record_id,
            "name": name,
            "entity_type": entity_type,
            "summary": summary,
            "details": details,
            "sources": sources or [],
            "related_entities": related_entities or [],
            "tags": tags or [],
            "retrieval_keywords": retrieval_keywords or [],
            "sector_links": sector_links or [],
            "upgrade_relevance": upgrade_relevance,
            "priority_score": priority_score,
            "confidence_score": confidence_score,
            "risk_score": risk_score,
            "status": status,
            "action_items": action_items or [],
            "test_links": test_links or [],
            "commit_links": commit_links or [],
            "created_at": timestamp,
            "updated_at": updated_at or timestamp,
            "last_reviewed_at": last_reviewed_at or timestamp,
        }
    )


def _json_field(record: dict[str, Any], field: str) -> str:
    return json.dumps(record[field], sort_keys=True, separators=(",", ":"))


def upsert_camelot_record(record: dict[str, Any], *, actor_id: int | None = None) -> dict[str, Any]:
    """Validate and store a Camelot record; returns the stored record."""
    normalized = validate_camelot_record(record)
    db.sync_exec(
        """
        INSERT OR REPLACE INTO loki_camelot_records(
            id, name, entity_type, summary, details, sources_json, related_entities_json,
            tags_json, retrieval_keywords_json, sector_links_json, upgrade_relevance,
            priority_score, confidence_score, risk_score, status, action_items_json,
            test_links_json, commit_links_json, created_at, updated_at, last_reviewed_at,
            actor_id, payload_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            normalized["id"],
            normalized["name"],
            normalized["entity_type"],
            normalized["summary"],
            normalized["details"],
            _json_field(normalized, "sources"),
            _json_field(normalized, "related_entities"),
            _json_field(normalized, "tags"),
            _json_field(normalized, "retrieval_keywords"),
            _json_field(normalized, "sector_links"),
            normalized["upgrade_relevance"],
            normalized["priority_score"],
            normalized["confidence_score"],
            normalized["risk_score"],
            normalized["status"],
            _json_field(normalized, "action_items"),
            _json_field(normalized, "test_links"),
            _json_field(normalized, "commit_links"),
            normalized["created_at"],
            normalized["updated_at"],
            normalized["last_reviewed_at"],
            actor_id,
            json.dumps(normalized, sort_keys=True),
        ),
    )
    return normalized


def camelot_record_from_row(row: Any) -> dict[str, Any]:
    payload = json.loads(row["payload_json"] or "{}")
    return validate_camelot_record(payload)


def get_camelot_record(record_id: str) -> dict[str, Any] | None:
    row = db.sync_one("SELECT payload_json FROM loki_camelot_records WHERE id=?", (record_id,))
    return camelot_record_from_row(row) if row else None


def list_camelot_records(
    *, entity_type: str | None = None, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if entity_type:
        clauses.append("entity_type=?")
        params.append(entity_type)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(200, limit)))
    rows = db.sync_all(
        f"SELECT payload_json FROM loki_camelot_records {where} ORDER BY updated_at DESC, id ASC LIMIT ?",
        tuple(params),
    )
    return [camelot_record_from_row(row) for row in rows]


def export_camelot_records(
    *, entity_type: str | None = None, status: str | None = None, limit: int = 50
) -> dict[str, Any]:
    records = list_camelot_records(entity_type=entity_type, status=status, limit=limit)
    return {"schema": "docs/schemas/camelot-wing.schema.json", "record_count": len(records), "records": records}


def import_camelot_records(payload: dict[str, Any], *, actor_id: int | None = None) -> dict[str, Any]:
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise CamelotRecordError("Camelot import payload must contain a records list")

    normalized_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise CamelotRecordError("Camelot import records must be objects")
        normalized_records.append(validate_camelot_record(record))

    imported: list[str] = []
    for record in normalized_records:
        imported.append(upsert_camelot_record(record, actor_id=actor_id)["id"])
    return {"imported_count": len(imported), "record_ids": imported}


def member_snapshot_to_camelot_record(
    *, guild_id: int, user_id: int, display_name: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    if snapshot.get("guild_id") not in (None, guild_id):
        raise CamelotRecordError("member snapshot guild_id does not match Camelot record guild_id")
    if snapshot.get("user_id") not in (None, user_id):
        raise CamelotRecordError("member snapshot user_id does not match Camelot record user_id")

    snippets = _clean_list(snapshot.get("recent", []))
    details = "\n".join(f"- {snippet}" for snippet in snippets) or "No public memory snippets stored."
    entry_count = int(snapshot.get("entry_count") or 0)
    confidence = 2.0 if entry_count == 0 else min(8.0, 3.0 + entry_count)
    return make_camelot_record(
        record_id=f"discord-member-{guild_id}-{user_id}",
        name=display_name,
        entity_type="user",
        summary=f"Discord member public-memory profile with {entry_count} redacted snippets.",
        details=details,
        sources=["loki_memory_entries:redacted_public_messages"],
        related_entities=[f"discord-guild-{guild_id}"],
        tags=["discord-member", "public-memory", "camelot"],
        retrieval_keywords=[str(user_id), display_name, "member memory"],
        sector_links=["Camelot Memory Palace", "Knowledge Management and Retrieval"],
        upgrade_relevance=6,
        priority_score=5,
        confidence_score=confidence,
        risk_score=3,
        status="active" if entry_count else "new",
        action_items=[],
        test_links=["tests/test_camelot_records.py"],
        commit_links=[],
    )
