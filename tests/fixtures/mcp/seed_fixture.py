from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from utils import db as shared_db

FIXTURE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = FIXTURE_ROOT / "generated"


def seed_fixture(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "loki_fixture.db"
    runtime_log_path = output_dir / "desktop_runtime.log"
    external_library_root = output_dir / "loki-libraries"
    external_library_path = external_library_root / "ralph-wiggum-legacy"
    external_docs_path = external_library_path / "docs"
    external_docs_path.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()

    original_db_path = shared_db.DB_PATH
    original_database_url = os.environ.pop("DATABASE_URL", None)
    shared_db.DB_PATH = database_path
    try:
        shared_db.init_sync()
    finally:
        shared_db.DB_PATH = original_db_path
        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url

    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            """
            INSERT INTO guild_config(
                guild_id, prefix, log_channel, welcome_channel, welcome_msg,
                starboard_channel, star_threshold, level_enabled
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                123456789012345678,
                "!",
                111111111111111111,
                222222222222222222,
                "Welcome to LOKI THE SUN GOD HQ!",
                333333333333333333,
                4,
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO automod_rules(
                guild_id, anti_invite, anti_spam, anti_caps, anti_mention,
                bad_words, max_mentions, spam_threshold, caps_percent
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                123456789012345678,
                1,
                1,
                0,
                1,
                "spoiler,badword",
                4,
                6,
                80,
            ),
        )
        conn.executemany(
            "INSERT INTO stickies(guild_id, channel_id, content) VALUES(?, ?, ?)",
            [
                (123456789012345678, 444444444444444444, "Read the rules before posting."),
                (123456789012345678, 555555555555555555, "Voice channels are grouped by team."),
            ],
        )
        conn.executemany(
            "INSERT INTO tags(guild_id, name, content, owner_id, uses, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            [
                (123456789012345678, "rules", "Follow the house rules.", 1, 21, 1710000000),
                (123456789012345678, "helpdesk", "Open a ticket for staff help.", 1, 14, 1710001000),
            ],
        )
        conn.executemany(
            "INSERT INTO forms(guild_id, name, title, target_channel_id) VALUES(?, ?, ?, ?)",
            [
                (123456789012345678, "appeal", "Ban Appeal", 666666666666666666),
                (123456789012345678, "recruitment", "Team Application", 777777777777777777),
            ],
        )
        conn.executemany(
            """
            INSERT INTO stream_subs(
                guild_id, platform, channel_name, target_channel_id, mention_role_id, last_status, last_event_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (123456789012345678, "twitch", "lokilive", 888888888888888888, None, 1, 1711000000),
                (123456789012345678, "youtube", "lokiclips", 999999999999999999, 121212121212121212, 0, 1711001000),
            ],
        )
        now = int(time.time())
        conn.executemany(
            """
            INSERT INTO loki_memory_entries(guild_id, channel_id, user_id, redacted_content, confidence, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    123456789012345678,
                    444444444444444444,
                    424242424242424242,
                    "Solar DJ likes queue experiments and keeps tokens [secret].",
                    0.7,
                    now,
                ),
                (
                    123456789012345678,
                    555555555555555555,
                    424242424242424242,
                    "Solar DJ prefers redacted public memory exports.",
                    0.6,
                    now - 60,
                ),
            ],
        )
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        camelot_payload = {
            "id": "user-123456789012345678-424242424242424242",
            "name": "Solar DJ",
            "entity_type": "user",
            "summary": "Deterministic public-memory profile for Solar DJ.",
            "details": "Uses redacted public memory snippets only.",
            "sources": ["loki_memory_entries:redacted_public_messages"],
            "related_entities": ["guild:123456789012345678", "discord_user:424242424242424242"],
            "tags": ["public-memory", "user"],
            "retrieval_keywords": ["solar", "dj", "memory"],
            "sector_links": ["Camelot Memory Palace", "Knowledge Management and Retrieval"],
            "upgrade_relevance": 5,
            "priority_score": 5,
            "confidence_score": 7,
            "risk_score": 2,
            "status": "active",
            "action_items": [],
            "test_links": [],
            "commit_links": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_reviewed_at": timestamp,
        }
        conn.execute(
            """
            INSERT INTO loki_camelot_records(
                id, name, entity_type, summary, details, sources_json, related_entities_json,
                tags_json, retrieval_keywords_json, sector_links_json, upgrade_relevance,
                priority_score, confidence_score, risk_score, status, action_items_json,
                test_links_json, commit_links_json, created_at, updated_at, last_reviewed_at,
                actor_id, payload_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                camelot_payload["id"],
                camelot_payload["name"],
                camelot_payload["entity_type"],
                camelot_payload["summary"],
                camelot_payload["details"],
                json.dumps(camelot_payload["sources"], sort_keys=True),
                json.dumps(camelot_payload["related_entities"], sort_keys=True),
                json.dumps(camelot_payload["tags"], sort_keys=True),
                json.dumps(camelot_payload["retrieval_keywords"], sort_keys=True),
                json.dumps(camelot_payload["sector_links"], sort_keys=True),
                camelot_payload["upgrade_relevance"],
                camelot_payload["priority_score"],
                camelot_payload["confidence_score"],
                camelot_payload["risk_score"],
                camelot_payload["status"],
                json.dumps(camelot_payload["action_items"], sort_keys=True),
                json.dumps(camelot_payload["test_links"], sort_keys=True),
                json.dumps(camelot_payload["commit_links"], sort_keys=True),
                camelot_payload["created_at"],
                camelot_payload["updated_at"],
                camelot_payload["last_reviewed_at"],
                None,
                json.dumps(camelot_payload, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    runtime_log_path.write_text(
        "2026-04-30 09:00:00 boot ok\n2026-04-30 09:05:00 local diagnostics ready\n",
        encoding="utf-8",
    )
    external_docs_path.joinpath("legacy_capabilities.md").write_text(
        "# Ralph Wiggum legacy library\nTickets and automod behavior are available as read-only references.\n",
        encoding="utf-8",
    )
    external_library_path.joinpath("ralph_wiggum_legacy_library.json").write_text(
        json.dumps(
            {
                "library": "ralph-wiggum-legacy",
                "source_root": "C:/Ralph Wiggum",
                "purpose": "External legacy reference for LOKI.",
                "generated_at": "2026-05-12T00:00:00+00:00",
                "overview": {
                    "command_count": 263,
                    "file_count": 909,
                    "components": ["discord.py bot", "Flask dashboard"],
                    "command_categories": {"Automod": 12, "Tickets": 8},
                },
                "commands": [{"command": "ticket", "description": "Create tickets"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest = {
        "db_path": str(database_path),
        "docs_path": str(FIXTURE_ROOT / "docs"),
        "codex_settings_path": str(FIXTURE_ROOT / "codex_settings.json"),
        "env_path": str(FIXTURE_ROOT / ".env"),
        "runtime_log_path": str(runtime_log_path),
        "external_library_root": str(external_library_root),
    }
    (output_dir / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed stable fixture data for the LOKI THE SUN GOD MCP smoke tests.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    manifest = seed_fixture(args.output_dir.resolve())
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
