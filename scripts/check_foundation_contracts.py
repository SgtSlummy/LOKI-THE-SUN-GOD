"""Validate LOKI autonomous foundation docs and JSON schemas.

This script is intentionally non-invasive: it reads required docs/schemas and
parses JSON schemas, but does not import bot modules or touch production state.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "docs/upgrades/10-sector-upgrade-plan.md",
    "docs/discord/command-event-ownership.md",
    "docs/architecture/mythos-swarm-architecture.md",
    "docs/memory-palace/camelot-wing-index.md",
    "docs/qc/upgrade-grading-system.md",
    "docs/testing/test-plan.md",
    "docs/deployment/container-deployment-plan.md",
    "docs/plugins-skills/skill-plugin-expansion-plan.md",
    "docs/media/media-expansion-plan.md",
    "docs/rollback/reset-and-restore-plan.md",
    "docs/schemas/database-schema-snapshot.json",
    "docs/schemas/activity-bridge-payload-snapshot.json",
    "docs/schemas/mythos-task-envelope.schema.json",
    "docs/schemas/camelot-wing.schema.json",
    "docs/schemas/upgrade-grading.schema.json",
    "tests/test_env_examples.py",
    "tests/test_deployment_config.py",
    "tests/test_activity_bridge_payload_snapshot.py",
    "docs/schemas/discord-context-menu-snapshot.json",
    "docs/schemas/discord-component-custom-id-snapshot.json",
    "docs/schemas/discord-persistent-view-registration-snapshot.json",
]
REQUIRED_TERMS = {
    "docs/upgrades/10-sector-upgrade-plan.md": ["Discord Core", "Camelot", "Mythos", "rollback"],
    "docs/discord/command-event-ownership.md": [
        "Production Discord command owner",
        "COG_MODULES",
        "privileged intents",
    ],
    "docs/schemas/database-schema-snapshot.json": ["postgres_converted_sha256", "worker_leases", "send_dedupe"],
    "docs/schemas/activity-bridge-payload-snapshot.json": [
        "server_to_client_message_types",
        "client_to_server_message_types",
        "http_control_actions",
    ],
    "docs/architecture/mythos-swarm-architecture.md": ["Task envelope", "Write-conflict", "Promotion gates"],
    "docs/memory-palace/camelot-wing-index.md": ["Privacy rules", "Never store raw tokens"],
    "docs/qc/upgrade-grading-system.md": ["functionality", "rollback readiness", "deployment"],
}


def test_required_foundation_files_exist() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    assert not missing, f"Missing foundation files: {missing}"


def test_required_foundation_terms_present() -> None:
    failures: list[str] = []
    for rel_path, terms in REQUIRED_TERMS.items():
        text = (ROOT / rel_path).read_text(encoding="utf-8")
        for term in terms:
            if term not in text:
                failures.append(f"{rel_path}: missing {term!r}")
    assert not failures, "; ".join(failures)


def test_json_schemas_parse() -> None:
    for rel_path in REQUIRED_FILES:
        if rel_path.endswith(".json"):
            data = json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
            if rel_path == "docs/schemas/database-schema-snapshot.json":
                assert data.get("source") == "utils/db.py:CORE_SCHEMA", f"{rel_path} should snapshot CORE_SCHEMA"
                assert data.get("tables"), f"{rel_path} should list database tables"
                continue
            if rel_path == "docs/schemas/activity-bridge-payload-snapshot.json":
                assert data.get("source_files"), f"{rel_path} should list source files"
                assert data.get("server_to_client_message_types"), f"{rel_path} should list outbound message types"
                assert data.get("client_to_server_message_types"), f"{rel_path} should list inbound message types"
                continue
            assert data.get("$schema"), f"{rel_path} missing $schema"
            assert data.get("type") == "object", f"{rel_path} should define an object schema"


if __name__ == "__main__":
    test_required_foundation_files_exist()
    test_required_foundation_terms_present()
    test_json_schemas_parse()
    print("foundation contracts passed")
