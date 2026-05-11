from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiosqlite

from utils import runtime_paths

DB_PATH = runtime_paths.app_path("data", "bot.db")
IntegrityError = sqlite3.IntegrityError


def current_db_path() -> Path:
    override = os.getenv("LOKI_DB_PATH")
    return Path(override) if override else DB_PATH


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres() -> bool:
    return bool(database_url())


def database_backend() -> str:
    return "postgres" if using_postgres() else "sqlite"


def current_database_label() -> str:
    if using_postgres():
        return "DATABASE_URL"
    return str(current_db_path())


CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    prefix TEXT DEFAULT '!',
    mute_role INTEGER,
    log_channel INTEGER,
    welcome_channel INTEGER,
    welcome_msg TEXT,
    goodbye_msg TEXT,
    starboard_channel INTEGER,
    star_threshold INTEGER DEFAULT 3,
    automod_enabled INTEGER DEFAULT 0,
    level_channel INTEGER,
    level_enabled INTEGER DEFAULT 1,
    tickets_category_id INTEGER,
    tickets_log_channel INTEGER,
    tickets_staff_role INTEGER
);

CREATE TABLE IF NOT EXISTS reaction_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    message_id INTEGER,
    channel_id INTEGER,
    emoji TEXT,
    role_id INTEGER,
    mode TEXT DEFAULT 'normal',
    UNIQUE(message_id, emoji)
);

CREATE TABLE IF NOT EXISTS rr_message_mode (
    message_id INTEGER PRIMARY KEY,
    mode TEXT DEFAULT 'normal'
);

CREATE TABLE IF NOT EXISTS tags (
    guild_id INTEGER,
    name TEXT,
    content TEXT,
    owner_id INTEGER,
    uses INTEGER DEFAULT 0,
    created_at INTEGER,
    PRIMARY KEY(guild_id, name)
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    mod_id INTEGER,
    reason TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS mutes (
    guild_id INTEGER,
    user_id INTEGER,
    until INTEGER,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER,
    user_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    last_msg INTEGER DEFAULT 0,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS starboard (
    message_id INTEGER PRIMARY KEY,
    star_message_id INTEGER,
    guild_id INTEGER,
    stars INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS highlights (
    guild_id INTEGER,
    user_id INTEGER,
    word TEXT,
    PRIMARY KEY(guild_id, user_id, word)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    channel_id INTEGER,
    guild_id INTEGER,
    due INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS giveaways (
    message_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    guild_id INTEGER,
    prize TEXT,
    winners INTEGER,
    ends INTEGER,
    host_id INTEGER,
    ended INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS autoresponders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    trigger TEXT,
    response TEXT,
    match_type TEXT DEFAULT 'contains'
);

CREATE TABLE IF NOT EXISTS automod_rules (
    guild_id INTEGER PRIMARY KEY,
    anti_invite INTEGER DEFAULT 0,
    anti_spam INTEGER DEFAULT 0,
    anti_caps INTEGER DEFAULT 0,
    anti_mention INTEGER DEFAULT 0,
    bad_words TEXT DEFAULT '',
    max_mentions INTEGER DEFAULT 5,
    spam_threshold INTEGER DEFAULT 5,
    caps_percent INTEGER DEFAULT 70
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL UNIQUE,
    opener_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    opened_at INTEGER NOT NULL,
    closed_at INTEGER,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_opener ON tickets(opener_id);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER,
    guild_id INTEGER,
    content TEXT,
    due INTEGER,
    author_id INTEGER
);

CREATE TABLE IF NOT EXISTS voice_activity (
    guild_id INTEGER,
    user_id INTEGER,
    seconds INTEGER DEFAULT 0,
    joined_at INTEGER DEFAULT 0,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    content TEXT,
    status TEXT DEFAULT 'pending',
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS suggestion_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    anonymous INTEGER DEFAULT 0,
    dm_on_decision INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stickies (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    content TEXT,
    last_msg_id INTEGER
);

CREATE TABLE IF NOT EXISTS autoroles (
    guild_id INTEGER,
    role_id INTEGER,
    PRIMARY KEY(guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS joinable_ranks (
    guild_id INTEGER,
    role_id INTEGER,
    PRIMARY KEY(guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    mod_id INTEGER,
    content TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS tempbans (
    guild_id INTEGER,
    user_id INTEGER,
    until INTEGER,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS temproles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    role_id INTEGER,
    until INTEGER
);

CREATE TABLE IF NOT EXISTS custom_embeds (
    guild_id INTEGER,
    name TEXT,
    payload TEXT,
    PRIMARY KEY(guild_id, name)
);

CREATE TABLE IF NOT EXISTS censor_words (
    guild_id INTEGER,
    word TEXT,
    PRIMARY KEY(guild_id, word)
);

CREATE TABLE IF NOT EXISTS link_filter (
    guild_id INTEGER,
    domain TEXT,
    mode TEXT,
    PRIMARY KEY(guild_id, domain)
);

CREATE TABLE IF NOT EXISTS disabled_commands (
    guild_id INTEGER,
    command TEXT,
    PRIMARY KEY(guild_id, command)
);

CREATE TABLE IF NOT EXISTS ignored_channels (
    guild_id INTEGER,
    channel_id INTEGER,
    PRIMARY KEY(guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS mod_roles (
    guild_id INTEGER,
    role_id INTEGER,
    PRIMARY KEY(guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS forms (
    guild_id INTEGER,
    name TEXT,
    title TEXT,
    fields TEXT DEFAULT '[]',
    target_channel_id INTEGER,
    button_label TEXT DEFAULT 'Fill Form',
    PRIMARY KEY(guild_id, name)
);

CREATE TABLE IF NOT EXISTS form_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    form_name TEXT,
    user_id INTEGER,
    responses TEXT,
    submitted_at INTEGER,
    status TEXT DEFAULT 'pending',
    decided_by TEXT,
    decided_at INTEGER,
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    title TEXT,
    description TEXT,
    starts_at INTEGER,
    host_id INTEGER,
    color INTEGER DEFAULT 5765005,
    location TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS event_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    offset_secs INTEGER,
    fired INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_reposts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    interval_secs INTEGER,
    next_at INTEGER
);

CREATE TABLE IF NOT EXISTS stream_subs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    target_channel_id INTEGER NOT NULL,
    mention_role_id INTEGER,
    last_status INTEGER DEFAULT 0,
    last_event_at INTEGER DEFAULT 0,
    UNIQUE(guild_id, platform, channel_name)
);

CREATE TABLE IF NOT EXISTS send_dedupe (
    target_id TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY(target_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_send_dedupe_expires_at ON send_dedupe(expires_at);

CREATE TABLE IF NOT EXISTS worker_leases (
    lease_name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    hostname TEXT,
    pid INTEGER,
    started_at INTEGER NOT NULL,
    heartbeat_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worker_leases_expires_at ON worker_leases(expires_at);

CREATE TABLE IF NOT EXISTS guard_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    owner_id TEXT,
    target_id TEXT,
    fingerprint TEXT,
    details TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_guard_audit_created_at ON guard_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_guard_audit_event_type ON guard_audit(event_type);

CREATE TABLE IF NOT EXISTS loki_music_settings (
    guild_id INTEGER PRIMARY KEY,
    dj_role_id INTEGER,
    request_channel_id INTEGER,
    eq_preset TEXT DEFAULT 'Flat',
    mixer_locked INTEGER DEFAULT 0,
    volume INTEGER DEFAULT 80,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS loki_npc_settings (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    persona_json TEXT DEFAULT '',
    channel_allowlist TEXT DEFAULT '',
    web_crawl_enabled INTEGER DEFAULT 0,
    auto_post_channel_id INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS loki_memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    user_id INTEGER,
    redacted_content TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_loki_memory_entries_guild ON loki_memory_entries(guild_id, created_at);

CREATE TABLE IF NOT EXISTS loki_research_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    source_url TEXT NOT NULL,
    title TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    reason_for_fit TEXT DEFAULT '',
    safety_status TEXT DEFAULT 'pending',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_loki_research_sources_guild ON loki_research_sources(guild_id, created_at);

CREATE TABLE IF NOT EXISTS loki_activity_controls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    discord_event_id TEXT DEFAULT '',
    title TEXT NOT NULL,
    status TEXT DEFAULT 'planned',
    activity_type TEXT DEFAULT 'portal',
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_loki_activity_controls_guild ON loki_activity_controls(guild_id, status);

CREATE TABLE IF NOT EXISTS loki_audit_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    actor_id INTEGER,
    action TEXT NOT NULL,
    allowed INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    details TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_loki_audit_receipts_guild ON loki_audit_receipts(guild_id, created_at);
"""

MIGRATION_COLUMNS = {
    "guild_config": [
        ("tickets_category_id", "INTEGER"),
        ("tickets_log_channel", "INTEGER"),
        ("tickets_staff_role", "INTEGER"),
    ],
    "form_responses": [
        ("status", "TEXT DEFAULT 'pending'"),
        ("decided_by", "TEXT"),
        ("decided_at", "INTEGER"),
        ("decision_note", "TEXT"),
    ],
}

TICKET_REQUIRED_COLUMNS = {
    "id",
    "guild_id",
    "channel_id",
    "opener_id",
    "status",
    "opened_at",
    "closed_at",
    "reason",
}

GUILD_CONFIG_WRITE_COLUMNS = {
    "prefix",
    "mute_role",
    "log_channel",
    "welcome_channel",
    "welcome_msg",
    "goodbye_msg",
    "starboard_channel",
    "star_threshold",
    "automod_enabled",
    "level_channel",
    "level_enabled",
    "tickets_category_id",
    "tickets_log_channel",
    "tickets_staff_role",
}

AUTOMOD_RULE_WRITE_COLUMNS = {
    "anti_invite",
    "anti_spam",
    "anti_caps",
    "anti_mention",
    "bad_words",
    "max_mentions",
    "spam_threshold",
    "caps_percent",
}

PG_CONFLICT_TARGETS = {
    "guild_config": ("guild_id",),
    "reaction_roles": ("message_id", "emoji"),
    "rr_message_mode": ("message_id",),
    "tags": ("guild_id", "name"),
    "mutes": ("guild_id", "user_id"),
    "levels": ("guild_id", "user_id"),
    "starboard": ("message_id",),
    "highlights": ("guild_id", "user_id", "word"),
    "giveaways": ("message_id",),
    "automod_rules": ("guild_id",),
    "suggestion_config": ("guild_id",),
    "stickies": ("channel_id",),
    "autoroles": ("guild_id", "role_id"),
    "joinable_ranks": ("guild_id", "role_id"),
    "tempbans": ("guild_id", "user_id"),
    "custom_embeds": ("guild_id", "name"),
    "censor_words": ("guild_id", "word"),
    "link_filter": ("guild_id", "domain"),
    "disabled_commands": ("guild_id", "command"),
    "ignored_channels": ("guild_id", "channel_id"),
    "mod_roles": ("guild_id", "role_id"),
    "forms": ("guild_id", "name"),
    "stream_subs": ("guild_id", "platform", "channel_name"),
    "send_dedupe": ("target_id", "dedupe_key"),
    "worker_leases": ("lease_name",),
    "loki_music_settings": ("guild_id",),
    "loki_npc_settings": ("guild_id",),
}

PG_SERIAL_TABLES = {
    "reaction_roles",
    "warnings",
    "reminders",
    "autoresponders",
    "tickets",
    "scheduled_messages",
    "suggestions",
    "notes",
    "temproles",
    "form_responses",
    "events",
    "event_reminders",
    "event_reposts",
    "stream_subs",
    "guard_audit",
    "loki_memory_entries",
    "loki_research_sources",
    "loki_activity_controls",
    "loki_audit_receipts",
}


class DbRow(Mapping):
    def __init__(self, keys: list[str], values: tuple[Any, ...]):
        self._keys = keys
        self._values = values
        self._mapping = dict(zip(keys, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key, default=None):
        return self._mapping.get(key, default)


def _sqlite_row_to_mapping(row: sqlite3.Row) -> DbRow:
    keys = list(row.keys())
    return DbRow(keys, tuple(row[key] for key in keys))


def _split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


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
    column_type = re.sub(r"\bINTEGER\b", "BIGINT", column_type, flags=re.IGNORECASE)
    return column_type


def _postgres_schema() -> str:
    return _postgres_column_type(CORE_SCHEMA)


def _replace_qmarks(sql: str) -> str:
    return sql.replace("?", "%s")


def _parse_insert_columns(columns: str) -> list[str]:
    return [column.strip().strip('"') for column in columns.split(",") if column.strip()]


def _translate_insert_or_ignore(sql: str) -> str | None:
    match = re.match(
        r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"\((.*?)\)\s*VALUES\s*\((.*?)\)\s*$",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    table_name, columns, values = match.groups()
    return f"INSERT INTO {table_name}({columns}) VALUES({values}) ON CONFLICT DO NOTHING"


def _translate_insert_or_replace(sql: str) -> str | None:
    match = re.match(
        r"\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"\((.*?)\)\s*VALUES\s*\((.*?)\)\s*$",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    table_name, columns, values = match.groups()
    conflict_columns = PG_CONFLICT_TARGETS.get(table_name)
    if not conflict_columns:
        return f"INSERT INTO {table_name}({columns}) VALUES({values}) ON CONFLICT DO NOTHING"
    insert_columns = _parse_insert_columns(columns)
    updates = [f"{column}=EXCLUDED.{column}" for column in insert_columns if column not in conflict_columns]
    if not updates:
        action = "DO NOTHING"
    else:
        action = "DO UPDATE SET " + ", ".join(updates)
    target = ", ".join(conflict_columns)
    return f"INSERT INTO {table_name}({columns}) VALUES({values}) ON CONFLICT ({target}) {action}"


def _to_postgres_sql(sql: str) -> str:
    translated = _translate_insert_or_ignore(sql) or _translate_insert_or_replace(sql) or sql
    translated = _postgres_column_type(translated)
    return _replace_qmarks(translated)


def _insert_table_name(sql: str) -> str | None:
    match = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _pg_connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("DATABASE_URL is set, but psycopg is not installed. Install requirements.txt.") from exc
    return psycopg.connect(database_url())


def _pg_integrity_error_classes() -> tuple[type[BaseException], ...]:
    try:
        import psycopg
    except ImportError:
        return ()
    return (psycopg.IntegrityError,)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {row[1] for row in rows}


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: list[tuple[str, str]]) -> None:
    existing = _table_columns(conn, table_name)
    for column_name, column_type in columns:
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _ensure_columns_pg(conn, table_name: str, columns: list[tuple[str, str]]) -> None:
    for column_name, column_type in columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {_postgres_column_type(column_type)}"
        )


def _migrate_legacy_tickets(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "tickets")
    if not columns or TICKET_REQUIRED_COLUMNS.issubset(columns):
        return

    legacy_rows = []
    legacy_columns = {"channel_id", "guild_id", "user_id", "opened_at", "topic"}
    if legacy_columns.issubset(columns):
        legacy_rows = conn.execute("SELECT channel_id, guild_id, user_id, opened_at, topic FROM tickets").fetchall()

    conn.execute("DROP TABLE tickets")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL UNIQUE,
            opener_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            opened_at INTEGER NOT NULL,
            closed_at INTEGER,
            reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id, status);
        CREATE INDEX IF NOT EXISTS idx_tickets_opener ON tickets(opener_id);
        """
    )

    if legacy_rows:
        conn.executemany(
            "INSERT INTO tickets(guild_id, channel_id, opener_id, status, opened_at, reason) VALUES(?,?,?,?,?,?)",
            [(row[1], row[0], row[2], "open", row[3], row[4]) for row in legacy_rows],
        )


def sync_all(sql: str, params: tuple = ()) -> list[DbRow]:
    if using_postgres():
        conn = _pg_connect()
        try:
            cur = conn.execute(_to_postgres_sql(sql), params)
            rows = cur.fetchall() if cur.description else []
            keys = [column.name for column in cur.description] if cur.description else []
            return [DbRow(keys, tuple(row)) for row in rows]
        finally:
            conn.close()

    init_sync()
    conn = sqlite3.connect(current_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [_sqlite_row_to_mapping(row) for row in rows]
    finally:
        conn.close()


def sync_one(sql: str, params: tuple = ()) -> DbRow | None:
    rows = sync_all(sql, params)
    return rows[0] if rows else None


def sync_exec(sql: str, params: tuple = ()) -> int:
    if using_postgres():
        conn = _pg_connect()
        try:
            try:
                cur = conn.execute(_to_postgres_sql(sql), params)
                conn.commit()
                return cur.rowcount
            except _pg_integrity_error_classes() as exc:
                conn.rollback()
                raise IntegrityError(str(exc)) from exc
        finally:
            conn.close()

    init_sync()
    conn = sqlite3.connect(current_db_path())
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


class PostgresAsyncCursor:
    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        rowcount: int = -1,
        lastrowid: int | None = None,
    ):
        self._rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    async def fetchall(self):
        return list(self._rows)


class PostgresAsyncConnection:
    def __init__(self):
        self._conn = None

    async def __aenter__(self):
        self._conn = _pg_connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._conn is None:
            return False
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self._conn.close()
            self._conn = None
        return False

    async def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    async def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    async def executescript(self, script: str) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresAsyncConnection must be used as an async context manager.")
        for statement in _split_sql_script(script):
            await self.execute(statement)

    async def execute(self, sql: str, params: tuple = ()) -> PostgresAsyncCursor:
        if self._conn is None:
            raise RuntimeError("PostgresAsyncConnection must be used as an async context manager.")
        pragma_rows = self._pragma_table_info_rows(sql)
        if pragma_rows is not None:
            return PostgresAsyncCursor(pragma_rows, len(pragma_rows))

        pg_sql = _to_postgres_sql(sql)
        returning_id = False
        table_name = _insert_table_name(pg_sql)
        lowered = pg_sql.lower()
        if table_name in PG_SERIAL_TABLES and " returning " not in lowered and " on conflict do nothing" not in lowered:
            pg_sql = f"{pg_sql} RETURNING id"
            returning_id = True

        try:
            cur = self._conn.execute(pg_sql, params)
        except _pg_integrity_error_classes() as exc:
            raise IntegrityError(str(exc)) from exc

        rows: list[tuple[Any, ...]] = []
        lastrowid = None
        if cur.description:
            rows = [tuple(row) for row in cur.fetchall()]
            if returning_id and rows:
                lastrowid = int(rows[0][0])
                rows = []
        return PostgresAsyncCursor(rows, cur.rowcount, lastrowid)

    def _pragma_table_info_rows(self, sql: str) -> list[tuple[Any, ...]] | None:
        match = re.match(r"\s*PRAGMA\s+table_info\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$", sql, re.IGNORECASE)
        if not match:
            return None
        table_name = match.group(1)
        cur = self._conn.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        rows = []
        for index, (name, data_type, nullable, default) in enumerate(cur.fetchall()):
            rows.append((index, name, data_type, 1 if nullable == "NO" else 0, default, 0))
        return rows


def init_sync() -> None:
    if using_postgres():
        conn = _pg_connect()
        try:
            for statement in _split_sql_script(_postgres_schema()):
                conn.execute(_to_postgres_sql(statement))
            for table_name, columns in MIGRATION_COLUMNS.items():
                _ensure_columns_pg(conn, table_name, columns)
            conn.commit()
        finally:
            conn.close()
        return

    db_path = current_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(CORE_SCHEMA)
        _migrate_legacy_tickets(conn)
        conn.executescript(CORE_SCHEMA)
        for table_name, columns in MIGRATION_COLUMNS.items():
            _ensure_columns(conn, table_name, columns)
        conn.commit()
    finally:
        conn.close()


async def init() -> None:
    init_sync()


def get():
    if using_postgres():
        return PostgresAsyncConnection()
    return aiosqlite.connect(current_db_path())


def _upsert_row_sync(
    table_name: str,
    key_column: str,
    key_value: int,
    values: dict[str, object],
) -> None:
    sync_exec(f"INSERT OR IGNORE INTO {table_name}({key_column}) VALUES(?)", (key_value,))
    if not values:
        return
    assignments = ", ".join(f"{column}=?" for column in values)
    sync_exec(
        f"UPDATE {table_name} SET {assignments} WHERE {key_column}=?",
        (*values.values(), key_value),
    )


def save_guild_config_sync(guild_id: int, values: dict[str, object]) -> None:
    filtered = {key: value for key, value in values.items() if key in GUILD_CONFIG_WRITE_COLUMNS}
    init_sync()
    _upsert_row_sync("guild_config", "guild_id", guild_id, filtered)


def save_automod_rules_sync(guild_id: int, values: dict[str, object]) -> None:
    filtered = {key: value for key, value in values.items() if key in AUTOMOD_RULE_WRITE_COLUMNS}
    init_sync()
    _upsert_row_sync("automod_rules", "guild_id", guild_id, filtered)
