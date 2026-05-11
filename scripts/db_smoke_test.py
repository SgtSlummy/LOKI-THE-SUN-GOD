from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import db as shared_db  # noqa: E402


def sqlite_smoke() -> str:
    old_path = os.environ.get("LOKI_DB_PATH")
    old_database_url = os.environ.pop("DATABASE_URL", None)
    try:
        with tempfile.TemporaryDirectory(prefix="loki-db-smoke-") as tmp:
            db_path = Path(tmp) / "bot.db"
            os.environ["LOKI_DB_PATH"] = str(db_path)
            shared_db.init_sync()
            shared_db.save_guild_config_sync(9001, {"prefix": "?"})
            row = shared_db.sync_one("SELECT prefix FROM guild_config WHERE guild_id=?", (9001,))
            if not row or row[0] != "?":
                raise AssertionError("SQLite smoke row did not round-trip.")
            first = shared_db.sync_exec(
                "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
                ("smoke-target", "smoke-key", 1, 9999999999),
            )
            second = shared_db.sync_exec(
                "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
                ("smoke-target", "smoke-key", 1, 9999999999),
            )
            if first != 1 or second != 0:
                raise AssertionError("SQLite send dedupe uniqueness did not hold.")
            lease_first = shared_db.sync_exec(
                "INSERT OR IGNORE INTO worker_leases"
                "(lease_name,owner_id,hostname,pid,started_at,heartbeat_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?)",
                ("loki-smoke-worker", "one", "smoke", 1, 1, 1, 9999999999),
            )
            lease_second = shared_db.sync_exec(
                "INSERT OR IGNORE INTO worker_leases"
                "(lease_name,owner_id,hostname,pid,started_at,heartbeat_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?)",
                ("loki-smoke-worker", "two", "smoke", 2, 1, 1, 9999999999),
            )
            if lease_first != 1 or lease_second != 0:
                raise AssertionError("SQLite worker lease uniqueness did not hold.")
            audit_row = shared_db.sync_exec(
                "INSERT INTO guard_audit(event_type,reason,owner_id,target_id,fingerprint,details,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                ("smoke", "sqlite_guard_audit", "owner", "target", "fingerprint", "{}", 1),
            )
            if audit_row != 1:
                raise AssertionError("SQLite guard audit row did not insert.")
            return f"SQLite ready at {db_path}"
    finally:
        if old_path is None:
            os.environ.pop("LOKI_DB_PATH", None)
        else:
            os.environ["LOKI_DB_PATH"] = old_path
        if old_database_url is not None:
            os.environ["DATABASE_URL"] = old_database_url


def postgres_smoke() -> str:
    if not os.getenv("DATABASE_URL"):
        return "Postgres skipped because DATABASE_URL is not set."

    sentinel = 900000000000000001
    shared_db.init_sync()
    try:
        shared_db.sync_exec("DELETE FROM guild_config WHERE guild_id=?", (sentinel,))
        shared_db.save_guild_config_sync(sentinel, {"prefix": "$"})
        row = shared_db.sync_one("SELECT prefix FROM guild_config WHERE guild_id=?", (sentinel,))
        if not row or row[0] != "$":
            raise AssertionError("Postgres smoke row did not round-trip.")
        shared_db.sync_exec(
            "DELETE FROM send_dedupe WHERE target_id=? AND dedupe_key=?",
            ("postgres-smoke-target", "postgres-smoke-key"),
        )
        first = shared_db.sync_exec(
            "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
            ("postgres-smoke-target", "postgres-smoke-key", 1, 9999999999),
        )
        second = shared_db.sync_exec(
            "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
            ("postgres-smoke-target", "postgres-smoke-key", 1, 9999999999),
        )
        if first != 1 or second != 0:
            raise AssertionError("Postgres send dedupe uniqueness did not hold.")
        shared_db.sync_exec("DELETE FROM worker_leases WHERE lease_name=?", ("loki-postgres-smoke-worker",))
        lease_first = shared_db.sync_exec(
            "INSERT OR IGNORE INTO worker_leases(lease_name,owner_id,hostname,pid,started_at,heartbeat_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?)",
            ("loki-postgres-smoke-worker", "one", "smoke", 1, 1, 1, 9999999999),
        )
        lease_second = shared_db.sync_exec(
            "INSERT OR IGNORE INTO worker_leases(lease_name,owner_id,hostname,pid,started_at,heartbeat_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?)",
            ("loki-postgres-smoke-worker", "two", "smoke", 2, 1, 1, 9999999999),
        )
        if lease_first != 1 or lease_second != 0:
            raise AssertionError("Postgres worker lease uniqueness did not hold.")
        audit_row = shared_db.sync_exec(
            "INSERT INTO guard_audit(event_type,reason,owner_id,target_id,fingerprint,details,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            ("smoke", "postgres_guard_audit", "owner", "target", "fingerprint", "{}", 1),
        )
        if audit_row != 1:
            raise AssertionError("Postgres guard audit row did not insert.")
        return "Postgres DATABASE_URL round-trip passed."
    finally:
        shared_db.sync_exec("DELETE FROM guild_config WHERE guild_id=?", (sentinel,))
        shared_db.sync_exec(
            "DELETE FROM send_dedupe WHERE target_id=? AND dedupe_key=?",
            ("postgres-smoke-target", "postgres-smoke-key"),
        )
        shared_db.sync_exec("DELETE FROM worker_leases WHERE lease_name=?", ("loki-postgres-smoke-worker",))
        shared_db.sync_exec(
            "DELETE FROM guard_audit WHERE event_type=? AND reason=?", ("smoke", "postgres_guard_audit")
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LOKI THE SUN GOD database migration smoke tests.")
    parser.add_argument("--postgres-required", action="store_true", help="Fail when DATABASE_URL is not set.")
    args = parser.parse_args()

    sqlite_detail = sqlite_smoke()
    print(f"[PASS] {sqlite_detail}")

    if args.postgres_required and not os.getenv("DATABASE_URL"):
        print("[FAIL] Postgres required but DATABASE_URL is not set.")
        return 1
    postgres_detail = postgres_smoke()
    print(f"[PASS] {postgres_detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
