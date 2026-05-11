from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from utils import db as shared_db

FIXTURE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = FIXTURE_ROOT / "generated"


def seed_fixture(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "loki_fixture.db"
    runtime_log_path = output_dir / "desktop_runtime.log"
    if database_path.exists():
        database_path.unlink()

    original_db_path = shared_db.DB_PATH
    shared_db.DB_PATH = database_path
    try:
        shared_db.init_sync()
    finally:
        shared_db.DB_PATH = original_db_path

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
        conn.commit()
    finally:
        conn.close()

    runtime_log_path.write_text(
        "2026-04-30 09:00:00 boot ok\n2026-04-30 09:05:00 local diagnostics ready\n",
        encoding="utf-8",
    )
    manifest = {
        "db_path": str(database_path),
        "docs_path": str(FIXTURE_ROOT / "docs"),
        "codex_settings_path": str(FIXTURE_ROOT / "codex_settings.json"),
        "env_path": str(FIXTURE_ROOT / ".env"),
        "runtime_log_path": str(runtime_log_path),
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
