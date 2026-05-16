"""Tests for the imported LOKI/Hermes swarm plan builder."""

from __future__ import annotations

import json
import sqlite3

from scripts import build_loki_swarm_plan as plan


def test_normalized_plan_references_are_valid() -> None:
    """Every imported task should reference known sources and dependencies."""

    assert plan.validate(plan.TASKS, plan.SOURCES) == []


def test_build_plan_artifacts(tmp_path) -> None:
    """The builder writes JSON, Markdown, and SQLite plan artifacts."""

    pdf_path = tmp_path / "missing.pdf"
    output_dir = tmp_path / "artifacts"

    assert plan.main(["--pdf", str(pdf_path), "--output-dir", str(output_dir), "--check"]) == 0

    json_path = output_dir / "swarm_plan.json"
    markdown_path = output_dir / "swarm_plan.md"
    db_path = output_dir / "library.db"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["source_pdf_present"] is False
    assert len(payload["tasks"]) == len(plan.TASKS)
    assert len(payload["sources"]) == len(plan.SOURCES)
    assert "LOKI/Hermes Swarm Development Plan Import" in markdown_path.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

    assert task_count == len(plan.TASKS)
    assert source_count == len(plan.SOURCES)
