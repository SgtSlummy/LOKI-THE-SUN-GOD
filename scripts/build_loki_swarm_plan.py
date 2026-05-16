"""Build the imported LOKI/Hermes swarm construction plan artifacts.

This script ports the operator PDF plan into repository-local artifacts that are
safe for LOKI/Hermes automation to consume. It creates a small SQLite knowledge
library plus Markdown and JSON reports with citations, tasks, pass structure,
quality gates, schedules, and a redacted environment snapshot.

The script intentionally stores environment variable names and presence only;
it never stores secret values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_OUTPUT_DIR = Path("data/loki_swarm_plan")
DEFAULT_SOURCE_PDF = Path("C:/Users/carme/OneDrive/Documents/Hermes plan.pdf")


@dataclass(frozen=True)
class Source:
    """Citation metadata for a plan source."""

    key: str
    title: str
    url: str
    topic: str
    confidence: float


@dataclass(frozen=True)
class Task:
    """A deterministic task imported from the PDF/backlog plan."""

    task_id: str
    pass_name: str
    sector: str
    title: str
    summary: str
    references: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    gate: str = "pytest, ruff, release_check, secret_scan, git diff --check"
    status: str = "planned"
    priority: str = "P1"
    risk: str = "medium"


SOURCES: tuple[Source, ...] = (
    Source(
        key="mission-control",
        title="Mission Control — Hermes Agent Multi-Agent & Orchestration",
        url="https://hermesatlas.com/projects/builderz-labs/mission-control",
        topic="agent fleet orchestration, telemetry, approval gates",
        confidence=0.8,
    ),
    Source(
        key="swarmclaw",
        title="SwarmClaw — Hermes Agent Multi-Agent & Orchestration",
        url="https://hermesatlas.com/projects/swarmclawai/swarmclaw",
        topic="self-hosted swarms, delegation, memory, scheduled tasks",
        confidence=0.8,
    ),
    Source(
        key="opencode-hermes-multiagent",
        title="OpenCode Hermes Multi-Agent Pipeline",
        url="https://hermesatlas.com/projects/1ilkhamov/opencode-hermes-multiagent",
        topic="specialist agents, pipeline roles, mandatory quality gates",
        confidence=0.8,
    ),
    Source(
        key="hermes-watchers",
        title="Hermes Watchers — Poll RSS, JSON APIs, and GitHub with watermark dedup",
        url="https://hermes-agent.nousresearch.com/docs/user-guide/skills/optional/devops/devops-watchers",
        topic="watch scripts, watermark deduplication, cron-safe output",
        confidence=0.9,
    ),
    Source(
        key="pep8",
        title="PEP 8 — Style Guide for Python Code",
        url="https://peps.python.org/pep-0008/",
        topic="Python formatting, naming, indentation, wrapping",
        confidence=0.95,
    ),
    Source(
        key="google-pyguide",
        title="Google Python Style Guide",
        url="https://google.github.io/styleguide/pyguide.html",
        topic="Python linting, pylint use, style discipline",
        confidence=0.9,
    ),
    Source(
        key="loki-backlog",
        title="LOKI Online AGI / Discord Bot / Music / LLM / Knowledge System Completion Backlog",
        url="docs/upgrades/online-agi-discordbot-completion-backlog.md",
        topic="current LOKI remaining programming goals and release gates",
        confidence=1.0,
    ),
    Source(
        key="loki-agent-workflow",
        title="LOKI AI Agent Workflow",
        url="docs/AI_AGENT_WORKFLOW.md",
        topic="bounded autonomy, agent lanes, memory and safety gates",
        confidence=1.0,
    ),
)


TASKS: tuple[Task, ...] = (
    Task(
        task_id="research-library-001",
        pass_name="pass-1-research-preparation",
        sector="knowledge-library",
        title="Initialize deterministic source and summary library",
        summary=(
            "Create a repository-local SQLite library containing source metadata, "
            "summaries, task links, env metadata, cron schedules, and grading records."
        ),
        references=("mission-control", "swarmclaw", "opencode-hermes-multiagent", "loki-backlog"),
        priority="P0",
        risk="low",
    ),
    Task(
        task_id="research-frameworks-002",
        pass_name="pass-1-research-preparation",
        sector="mythos-router-and-swarm-orchestration",
        title="Document orchestration patterns for HermesP and HermesS",
        summary=(
            "Compare Mission Control, SwarmClaw, OpenCode Hermes, and Hermes watcher "
            "patterns, then map them into LOKI's advisory-only autonomy model."
        ),
        references=("mission-control", "swarmclaw", "opencode-hermes-multiagent", "hermes-watchers"),
        depends_on=("research-library-001",),
        priority="P0",
        risk="medium",
    ),
    Task(
        task_id="env-bootstrap-003",
        pass_name="pass-1-research-preparation",
        sector="database-railway-persistence",
        title="Capture redacted environment and runtime inventory",
        summary=(
            "Record Python, OS, package/tool presence, Railway variable names, and "
            "service URLs without storing secret values."
        ),
        references=("loki-backlog", "loki-agent-workflow"),
        depends_on=("research-library-001",),
        priority="P0",
        risk="low",
    ),
    Task(
        task_id="watchers-core-004",
        pass_name="pass-2-implementation-linking",
        sector="plugin-skill-expansion",
        title="Implement RSS, GitHub, and JSON watcher modules",
        summary=(
            "Build cron-safe watcher scripts with watermark deduplication, capped state, "
            "rate-limit handling, and test fixtures for external APIs."
        ),
        references=("hermes-watchers", "pep8", "google-pyguide"),
        depends_on=("research-frameworks-002", "env-bootstrap-003"),
        priority="P1",
        risk="medium",
    ),
    Task(
        task_id="crawler-policy-005",
        pass_name="pass-2-implementation-linking",
        sector="knowledge-management-and-retrieval",
        title="Add safe crawler/recommendation policy and queue",
        summary=(
            "Define allowlist/denylist controls, source confidence scoring, unsafe-content "
            "filters, audit receipts, and operator approval before posting."
        ),
        references=("loki-backlog", "loki-agent-workflow"),
        depends_on=("watchers-core-004",),
        priority="P4",
        risk="high",
    ),
    Task(
        task_id="shepherd-router-006",
        pass_name="pass-2-implementation-linking",
        sector="mythos-router-and-swarm-orchestration",
        title="Build Shepherd Router task queue and heartbeat monitor",
        summary=(
            "Create HermesS persistence for task dispatch, dependencies, heartbeats, "
            "restart/reassign decisions, role rotation, audit logs, and cron schedules."
        ),
        references=("mission-control", "swarmclaw", "opencode-hermes-multiagent", "loki-agent-workflow"),
        depends_on=("research-frameworks-002", "env-bootstrap-003"),
        priority="P5",
        risk="high",
    ),
    Task(
        task_id="camelot-profiles-007",
        pass_name="pass-2-implementation-linking",
        sector="camelot-memory-palace",
        title="Add dashboard/operator views for Camelot exports and source-aware profiles",
        summary=(
            "Finish the remaining P1 surface by displaying deterministic member profiles "
            "and Camelot exports while preserving public-memory-only redaction rules."
        ),
        references=("loki-backlog", "loki-agent-workflow"),
        depends_on=("research-library-001",),
        priority="P1",
        risk="medium",
    ),
    Task(
        task_id="activity-heartbeat-008",
        pass_name="pass-2-implementation-linking",
        sector="discord-core-bot-architecture",
        title="Add Activity Bridge room heartbeat, stale cleanup, and persistence contract",
        summary=(
            "Complete the remaining Activity Bridge slice with durable room status, stale "
            "cleanup semantics, and Discord command failure tests."
        ),
        references=("loki-backlog",),
        depends_on=("env-bootstrap-003",),
        priority="P2",
        risk="medium",
    ),
    Task(
        task_id="audio-capabilities-009",
        pass_name="pass-2-implementation-linking",
        sector="music-and-media-systems",
        title="Add optional FFmpeg/DCA capability probes and wrappers",
        summary=(
            "Implement non-blocking optional audio capability checks, ffmpeg wrappers, and "
            "DCA asset helpers that never block Railway startup when dependencies are absent."
        ),
        references=("loki-backlog", "pep8"),
        depends_on=("env-bootstrap-003",),
        priority="P3",
        risk="medium",
    ),
    Task(
        task_id="mythos-packet-010",
        pass_name="pass-2-implementation-linking",
        sector="agi-agent-reasoning-layer",
        title="Expose safe Mythos packet compilation and proposal queue",
        summary=(
            "Build a dashboard/operator endpoint for redacted status packets, proposal "
            "grading, rollback metadata, and advisory-only approval boundaries."
        ),
        references=("loki-backlog", "loki-agent-workflow", "opencode-hermes-multiagent"),
        depends_on=("shepherd-router-006",),
        priority="P5",
        risk="high",
    ),
    Task(
        task_id="evaluation-grading-011",
        pass_name="pass-3-evaluation-grading",
        sector="testing-qc-grading-mutation-github-automation",
        title="Grade every slice and retry below-threshold work safely",
        summary=(
            "Run local gates, validate source coverage, grade each task across code, tests, "
            "docs, security, rollback, memory integration, and user value."
        ),
        references=("pep8", "google-pyguide", "loki-backlog"),
        depends_on=(
            "watchers-core-004",
            "crawler-policy-005",
            "shepherd-router-006",
            "camelot-profiles-007",
            "activity-heartbeat-008",
            "audio-capabilities-009",
            "mythos-packet-010",
        ),
        priority="P0",
        risk="medium",
    ),
)


SCHEDULES = (
    {"name": "rss-watcher", "schedule": "*/15 * * * *", "task": "watchers-core-004"},
    {"name": "github-watcher", "schedule": "*/15 * * * *", "task": "watchers-core-004"},
    {"name": "json-api-watcher", "schedule": "*/15 * * * *", "task": "watchers-core-004"},
    {"name": "shepherd-heartbeat", "schedule": "*/5 * * * *", "task": "shepherd-router-006"},
    {"name": "daily-grade-report", "schedule": "0 9 * * *", "task": "evaluation-grading-011"},
)


SECRET_NAME_FRAGMENTS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "DATABASE_URL", "WEBHOOK", "DSN")


def utc_now() -> str:
    """Return a stable UTC timestamp."""

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def read_pdf_text(pdf_path: Path) -> str:
    """Extract PDF text via pdftotext when available.

    Missing PDFs or missing pdftotext are non-fatal because the normalized task
    list above is the authoritative imported representation used by CI.
    """

    if not pdf_path.exists():
        return ""
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return ""
    try:
        result = subprocess.run(
            [pdftotext, str(pdf_path), "-"],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def content_hash(text: str) -> str:
    """Return a short SHA-256 digest for artifact provenance."""

    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def redacted_environment() -> list[dict[str, object]]:
    """Return environment variable metadata without secret values."""

    rows: list[dict[str, object]] = []
    for name in sorted(os.environ):
        upper_name = name.upper()
        sensitive = any(fragment in upper_name for fragment in SECRET_NAME_FRAGMENTS)
        if sensitive or upper_name.startswith(("LOKI_", "RAILWAY_", "DISCORD_", "HERMES_")):
            rows.append(
                {
                    "name": name,
                    "present": True,
                    "sensitive": sensitive,
                    "value": "<redacted>" if sensitive else "<set>",
                }
            )
    return rows


def runtime_inventory() -> dict[str, object]:
    """Collect non-secret runtime metadata for reproducibility."""

    packages: dict[str, str] = {}
    for module_name in ("transformers", "kernels", "torch"):
        try:
            module = __import__(module_name)
            packages[module_name] = str(getattr(module, "__version__", "installed"))
        except Exception as exc:  # pragma: no cover - defensive inventory only
            packages[module_name] = f"missing: {exc.__class__.__name__}"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "packages": packages,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the imported plan library schema."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources (
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            topic TEXT NOT NULL,
            confidence REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            pass_name TEXT NOT NULL,
            sector TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            references_json TEXT NOT NULL,
            depends_on_json TEXT NOT NULL,
            gate TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            risk TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schedules (
            name TEXT PRIMARY KEY,
            schedule TEXT NOT NULL,
            task_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS env_snapshot (
            name TEXT PRIMARY KEY,
            present INTEGER NOT NULL,
            sensitive INTEGER NOT NULL,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def write_library(
    db_path: Path,
    sources: Sequence[Source],
    tasks: Sequence[Task],
    schedules: Iterable[dict[str, str]],
    env_rows: Sequence[dict[str, object]],
    metadata: dict[str, object],
) -> None:
    """Write imported plan records to SQLite."""

    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO sources (key, title, url, topic, confidence)
            VALUES (:key, :title, :url, :topic, :confidence)
            """,
            [asdict(source) for source in sources],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO tasks (
                task_id, pass_name, sector, title, summary, references_json,
                depends_on_json, gate, status, priority, risk
            ) VALUES (
                :task_id, :pass_name, :sector, :title, :summary, :references_json,
                :depends_on_json, :gate, :status, :priority, :risk
            )
            """,
            [
                {
                    **asdict(task),
                    "references_json": json.dumps(task.references, sort_keys=True),
                    "depends_on_json": json.dumps(task.depends_on, sort_keys=True),
                }
                for task in tasks
            ],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO schedules (name, schedule, task_id)
            VALUES (:name, :schedule, :task)
            """,
            schedules,
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO env_snapshot (name, present, sensitive, value)
            VALUES (:name, :present, :sensitive, :value)
            """,
            [
                {
                    "name": row["name"],
                    "present": int(bool(row["present"])),
                    "sensitive": int(bool(row["sensitive"])),
                    "value": row["value"],
                }
                for row in env_rows
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [(key, json.dumps(value, sort_keys=True)) for key, value in metadata.items()],
        )


def build_markdown(payload: dict[str, object]) -> str:
    """Render a human-readable imported plan report."""

    lines = [
        "# LOKI/Hermes Swarm Development Plan Import",
        "",
        f"Generated: {payload['generated_at']}",
        f"Source PDF present: {payload['source_pdf_present']}",
        f"Source PDF text hash: `{payload['source_pdf_text_hash']}`",
        "",
        "## Sources",
        "",
    ]
    for source in payload["sources"]:  # type: ignore[index]
        lines.append(f"- `{source['key']}`: [{source['title']}]({source['url']}) — {source['topic']}")
    lines.extend(["", "## Fixed Task List", ""])
    for task in payload["tasks"]:  # type: ignore[index]
        refs = ", ".join(f"`{ref}`" for ref in task["references"])
        deps = ", ".join(f"`{dep}`" for dep in task["depends_on"]) or "none"
        lines.extend(
            [
                f"### {task['task_id']} — {task['title']}",
                "",
                f"- Pass: `{task['pass_name']}`",
                f"- Sector: `{task['sector']}`",
                f"- Priority/risk: `{task['priority']}` / `{task['risk']}`",
                f"- Depends on: {deps}",
                f"- References: {refs}",
                f"- Gate: `{task['gate']}`",
                f"- Summary: {task['summary']}",
                "",
            ]
        )
    lines.extend(["## Cron Schedule Seeds", ""])
    for schedule in payload["schedules"]:  # type: ignore[index]
        lines.append(f"- `{schedule['name']}` → `{schedule['schedule']}` for `{schedule['task']}`")
    lines.extend(
        [
            "",
            "## Runtime Inventory",
            "",
            "```json",
            json.dumps(payload["runtime"], indent=2, sort_keys=True),
            "```",
            "",
            "## Safety Notes",
            "",
            "- Environment values are redacted; only names/presence are stored.",
            "- External posting and Discord mutation remain operator-approved only.",
            "- Watchers must print only new deduplicated items and preserve watermarks.",
            "- Quality gate target remains release-safe, not self-modifying production code.",
            "",
        ]
    )
    return "\n".join(lines)


def validate(tasks: Sequence[Task], sources: Sequence[Source]) -> list[str]:
    """Return validation errors for the normalized plan."""

    errors: list[str] = []
    source_keys = {source.key for source in sources}
    task_ids = {task.task_id for task in tasks}
    for task in tasks:
        missing_refs = sorted(set(task.references) - source_keys)
        missing_deps = sorted(set(task.depends_on) - task_ids)
        if missing_refs:
            errors.append(f"{task.task_id}: missing source references {missing_refs}")
        if missing_deps:
            errors.append(f"{task.task_id}: missing task dependencies {missing_deps}")
        if task.status != "planned":
            errors.append(f"{task.task_id}: unexpected status {task.status!r}")
    return errors


def build_payload(pdf_path: Path) -> dict[str, object]:
    """Build the complete imported plan payload."""

    pdf_text = read_pdf_text(pdf_path)
    return {
        "generated_at": utc_now(),
        "source_pdf": str(pdf_path),
        "source_pdf_present": pdf_path.exists(),
        "source_pdf_text_hash": content_hash(pdf_text) if pdf_text else "unavailable",
        "source_pdf_text_chars": len(pdf_text),
        "sources": [asdict(source) for source in SOURCES],
        "tasks": [asdict(task) for task in TASKS],
        "schedules": list(SCHEDULES),
        "environment": redacted_environment(),
        "runtime": runtime_inventory(),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_SOURCE_PDF, help="Source PDF path to hash/extract")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Artifact output directory")
    parser.add_argument("--check", action="store_true", help="Validate only after writing artifacts")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build artifacts and return a process exit code."""

    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_payload(args.pdf)
    errors = validate(TASKS, SOURCES)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    json_path = output_dir / "swarm_plan.json"
    markdown_path = output_dir / "swarm_plan.md"
    db_path = output_dir / "library.db"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(build_markdown(payload), encoding="utf-8")
    write_library(db_path, SOURCES, TASKS, SCHEDULES, payload["environment"], payload)

    result = {
        "ok": True,
        "json": str(json_path),
        "markdown": str(markdown_path),
        "db": str(db_path),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
