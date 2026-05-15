from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_SOURCE = ROOT / "utils" / "db.py"
SNAPSHOT = ROOT / "docs" / "schemas" / "database-schema-snapshot.json"


def test_database_schema_snapshot_matches_core_schema() -> None:
    core_schema = _core_schema_from_source()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert snapshot["source"] == "utils/db.py:CORE_SCHEMA"
    assert snapshot["sha256"] == hashlib.sha256(core_schema.encode("utf-8")).hexdigest()
    assert snapshot["postgres_converted_sha256"] == hashlib.sha256(
        _postgres_column_type(core_schema).encode("utf-8")
    ).hexdigest()
    assert snapshot["statement_count"] == len(_split_sql_script(core_schema))
    assert snapshot["tables"] == _table_names(core_schema)
    assert snapshot["indexes"] == _index_names(core_schema)
    assert "postgres_converted_sha256" in snapshot


def _core_schema_from_source() -> str:
    tree = ast.parse(DB_SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CORE_SCHEMA":
                    value = ast.literal_eval(node.value)
                    assert isinstance(value, str)
                    return value
    raise AssertionError("utils/db.py is missing CORE_SCHEMA")


def _split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def _table_names(script: str) -> list[str]:
    names = re.findall(r"CREATE TABLE IF NOT EXISTS ([A-Za-z_][A-Za-z0-9_]*)", script)
    return sorted(names)


def _index_names(script: str) -> list[str]:
    names = re.findall(r"CREATE INDEX IF NOT EXISTS ([A-Za-z_][A-Za-z0-9_]*)", script)
    return sorted(names)


def _postgres_column_type(column_type: str) -> str:
    column_type = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        column_type,
        flags=re.IGNORECASE,
    )
    column_type = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\b",
        "BIGINT PRIMARY KEY",
        column_type,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\bINTEGER\b", "BIGINT", column_type, flags=re.IGNORECASE)
