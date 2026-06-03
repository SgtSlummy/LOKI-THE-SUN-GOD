from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg

from bot.models.relay import RelayRoute


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sqlite_timestamp(value: datetime) -> str:
    return value.isoformat()


def _postgres_timestamp(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.kind = "postgres" if database_url.startswith(("postgres://", "postgresql://")) else "sqlite"
        self._conn: aiosqlite.Connection | asyncpg.Connection | None = None

    async def connect(self) -> None:
        if self.kind == "postgres":
            self._conn = await asyncpg.connect(self.database_url)
            return

        path = self._sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def healthcheck(self) -> bool:
        if self._conn is None:
            return False
        try:
            if self.kind == "postgres":
                await self._conn.fetchval("SELECT 1")
            else:
                await self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def migrate(self) -> None:
        if self.kind == "postgres":
            await self._migrate_postgres()
        else:
            await self._migrate_sqlite()

    async def add_relay_route(
        self,
        *,
        guild_id: int,
        source_channel_id: int,
        destination_channel_id: int,
        direction: str,
        created_by: int | None,
    ) -> RelayRoute:
        self._validate_direction(direction)
        created_at = _now_utc()
        if self.kind == "postgres":
            row = await self._pg.fetchrow(
                """
                INSERT INTO relay_routes (
                    guild_id, source_channel_id, destination_channel_id,
                    direction, enabled, created_by, created_at
                )
                VALUES ($1, $2, $3, $4, TRUE, $5, $6)
                RETURNING *
                """,
                guild_id,
                source_channel_id,
                destination_channel_id,
                direction,
                created_by,
                created_at,
            )
        else:
            sqlite_created_at = _sqlite_timestamp(created_at)
            cursor = await self._sqlite.execute(
                """
                INSERT INTO relay_routes (
                    guild_id, source_channel_id, destination_channel_id,
                    direction, enabled, created_by, created_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (guild_id, source_channel_id, destination_channel_id, direction, created_by, sqlite_created_at),
            )
            await self._sqlite.commit()
            row = await self._fetch_route_by_id(cursor.lastrowid)
        return self._route_from_row(row)

    async def remove_relay_route(self, route_id: int) -> bool:
        if self.kind == "postgres":
            result = await self._pg.execute("UPDATE relay_routes SET enabled = FALSE WHERE id = $1", route_id)
            return result.endswith("1")
        cursor = await self._sqlite.execute("UPDATE relay_routes SET enabled = 0 WHERE id = ?", (route_id,))
        await self._sqlite.commit()
        return cursor.rowcount == 1

    async def get_route(self, route_id: int) -> RelayRoute | None:
        row = await self._fetch_route_by_id(route_id)
        if row is None:
            return None
        return self._route_from_row(row)

    async def list_relay_routes(self, guild_id: int | None = None) -> list[RelayRoute]:
        if self.kind == "postgres":
            if guild_id is None:
                rows = await self._pg.fetch("SELECT * FROM relay_routes WHERE enabled = TRUE ORDER BY id")
            else:
                rows = await self._pg.fetch(
                    "SELECT * FROM relay_routes WHERE enabled = TRUE AND guild_id = $1 ORDER BY id",
                    guild_id,
                )
        else:
            if guild_id is None:
                cursor = await self._sqlite.execute("SELECT * FROM relay_routes WHERE enabled = 1 ORDER BY id")
            else:
                cursor = await self._sqlite.execute(
                    "SELECT * FROM relay_routes WHERE enabled = 1 AND guild_id = ? ORDER BY id",
                    (guild_id,),
                )
            rows = await cursor.fetchall()
        return [self._route_from_row(row) for row in rows]

    async def routes_for_source(self, guild_id: int, source_channel_id: int) -> list[RelayRoute]:
        if self.kind == "postgres":
            direct = await self._pg.fetch(
                """
                SELECT * FROM relay_routes
                WHERE enabled = TRUE AND guild_id = $1 AND source_channel_id = $2
                ORDER BY id
                """,
                guild_id,
                source_channel_id,
            )
            reverse = await self._pg.fetch(
                """
                SELECT * FROM relay_routes
                WHERE enabled = TRUE AND guild_id = $1 AND direction = 'bidirectional'
                  AND destination_channel_id = $2
                ORDER BY id
                """,
                guild_id,
                source_channel_id,
            )
        else:
            cursor = await self._sqlite.execute(
                """
                SELECT * FROM relay_routes
                WHERE enabled = 1 AND guild_id = ? AND source_channel_id = ?
                ORDER BY id
                """,
                (guild_id, source_channel_id),
            )
            direct = await cursor.fetchall()
            cursor = await self._sqlite.execute(
                """
                SELECT * FROM relay_routes
                WHERE enabled = 1 AND guild_id = ? AND direction = 'bidirectional'
                  AND destination_channel_id = ?
                ORDER BY id
                """,
                (guild_id, source_channel_id),
            )
            reverse = await cursor.fetchall()

        routes = [self._route_from_row(row) for row in direct]
        routes.extend(self._reverse_route(self._route_from_row(row)) for row in reverse)
        return routes

    async def record_message_map(
        self,
        *,
        source_message_id: int,
        source_channel_id: int,
        destination_message_id: int,
        destination_channel_id: int,
        route_id: int,
    ) -> None:
        created_at = _now_utc()
        if self.kind == "postgres":
            await self._pg.execute(
                """
                INSERT INTO relay_message_map (
                    source_message_id, source_channel_id, destination_message_id,
                    destination_channel_id, route_id, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
                """,
                source_message_id,
                source_channel_id,
                destination_message_id,
                destination_channel_id,
                route_id,
                created_at,
            )
        else:
            sqlite_created_at = _sqlite_timestamp(created_at)
            await self._sqlite.execute(
                """
                INSERT OR IGNORE INTO relay_message_map (
                    source_message_id, source_channel_id, destination_message_id,
                    destination_channel_id, route_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source_message_id,
                    source_channel_id,
                    destination_message_id,
                    destination_channel_id,
                    route_id,
                    sqlite_created_at,
                ),
            )
            await self._sqlite.commit()

    async def is_relayed_message(self, message_id: int, channel_id: int) -> bool:
        if self.kind == "postgres":
            value = await self._pg.fetchval(
                """
                SELECT 1 FROM relay_message_map
                WHERE destination_message_id = $1 AND destination_channel_id = $2
                LIMIT 1
                """,
                message_id,
                channel_id,
            )
        else:
            cursor = await self._sqlite.execute(
                """
                SELECT 1 FROM relay_message_map
                WHERE destination_message_id = ? AND destination_channel_id = ?
                LIMIT 1
                """,
                (message_id, channel_id),
            )
            value = await cursor.fetchone()
        return value is not None

    async def is_source_message_mapped(self, source_message_id: int, source_channel_id: int, route_id: int) -> bool:
        if self.kind == "postgres":
            value = await self._pg.fetchval(
                """
                SELECT 1 FROM relay_message_map
                WHERE source_message_id = $1 AND source_channel_id = $2 AND route_id = $3
                LIMIT 1
                """,
                source_message_id,
                source_channel_id,
                route_id,
            )
        else:
            cursor = await self._sqlite.execute(
                """
                SELECT 1 FROM relay_message_map
                WHERE source_message_id = ? AND source_channel_id = ? AND route_id = ?
                LIMIT 1
                """,
                (source_message_id, source_channel_id, route_id),
            )
            value = await cursor.fetchone()
        return value is not None

    async def cache_media(
        self,
        *,
        original_url_hash: str,
        provider: str | None,
        title: str | None,
        thumbnail_url: str | None,
        media_type: str | None,
        resolved_payload: dict[str, Any],
        expires_at: str | None,
    ) -> None:
        payload = json.dumps(resolved_payload)
        if self.kind == "postgres":
            postgres_expires_at = _postgres_timestamp(expires_at)
            await self._pg.execute(
                """
                INSERT INTO media_cache (
                    original_url_hash, provider, title, thumbnail_url, media_type,
                    resolved_payload_json, expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (original_url_hash) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    title = EXCLUDED.title,
                    thumbnail_url = EXCLUDED.thumbnail_url,
                    media_type = EXCLUDED.media_type,
                    resolved_payload_json = EXCLUDED.resolved_payload_json,
                    expires_at = EXCLUDED.expires_at
                """,
                original_url_hash,
                provider,
                title,
                thumbnail_url,
                media_type,
                payload,
                postgres_expires_at,
            )
        else:
            await self._sqlite.execute(
                """
                INSERT INTO media_cache (
                    original_url_hash, provider, title, thumbnail_url, media_type,
                    resolved_payload_json, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(original_url_hash) DO UPDATE SET
                    provider = excluded.provider,
                    title = excluded.title,
                    thumbnail_url = excluded.thumbnail_url,
                    media_type = excluded.media_type,
                    resolved_payload_json = excluded.resolved_payload_json,
                    expires_at = excluded.expires_at
                """,
                (original_url_hash, provider, title, thumbnail_url, media_type, payload, expires_at),
            )
            await self._sqlite.commit()

    async def audit(
        self,
        *,
        event_type: str,
        actor_id: int | None = None,
        guild_id: int | None = None,
        channel_id: int | None = None,
        message_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details_json = json.dumps(details or {})
        created_at = _now_utc()
        if self.kind == "postgres":
            await self._pg.execute(
                """
                INSERT INTO audit_log (
                    event_type, actor_id, guild_id, channel_id,
                    message_id, details_json, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_type,
                actor_id,
                guild_id,
                channel_id,
                message_id,
                details_json,
                created_at,
            )
        else:
            sqlite_created_at = _sqlite_timestamp(created_at)
            await self._sqlite.execute(
                """
                INSERT INTO audit_log (
                    event_type, actor_id, guild_id, channel_id,
                    message_id, details_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, actor_id, guild_id, channel_id, message_id, details_json, sqlite_created_at),
            )
            await self._sqlite.commit()

    async def upsert_plugin_state(
        self,
        *,
        plugin_name: str,
        slot: str,
        enabled: bool,
        config: dict[str, Any] | None = None,
    ) -> None:
        updated_at = _now_utc()
        config_json = json.dumps(config or {})
        if self.kind == "postgres":
            await self._pg.execute(
                """
                INSERT INTO plugin_state (plugin_name, slot, enabled, config_json, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (plugin_name) DO UPDATE SET
                    slot = EXCLUDED.slot,
                    enabled = EXCLUDED.enabled,
                    config_json = EXCLUDED.config_json,
                    updated_at = EXCLUDED.updated_at
                """,
                plugin_name,
                slot,
                enabled,
                config_json,
                updated_at,
            )
        else:
            sqlite_updated_at = _sqlite_timestamp(updated_at)
            await self._sqlite.execute(
                """
                INSERT INTO plugin_state (plugin_name, slot, enabled, config_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(plugin_name) DO UPDATE SET
                    slot = excluded.slot,
                    enabled = excluded.enabled,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (plugin_name, slot, int(enabled), config_json, sqlite_updated_at),
            )
            await self._sqlite.commit()

    async def _fetch_route_by_id(self, route_id: int | None) -> Any:
        if route_id is None:
            return None
        if self.kind == "postgres":
            return await self._pg.fetchrow("SELECT * FROM relay_routes WHERE id = $1", route_id)
        cursor = await self._sqlite.execute("SELECT * FROM relay_routes WHERE id = ?", (route_id,))
        return await cursor.fetchone()

    async def _migrate_sqlite(self) -> None:
        await self._sqlite.executescript(
            """
            CREATE TABLE IF NOT EXISTS relay_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                destination_channel_id INTEGER NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('one_way', 'bidirectional')),
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_relay_routes_source
                ON relay_routes(guild_id, source_channel_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_relay_routes_destination
                ON relay_routes(guild_id, destination_channel_id, enabled);

            CREATE TABLE IF NOT EXISTS relay_message_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_message_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                destination_message_id INTEGER NOT NULL,
                destination_channel_id INTEGER NOT NULL,
                route_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_message_id, source_channel_id, route_id),
                UNIQUE(destination_message_id, destination_channel_id)
            );

            CREATE TABLE IF NOT EXISTS media_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url_hash TEXT NOT NULL UNIQUE,
                provider TEXT,
                title TEXT,
                thumbnail_url TEXT,
                media_type TEXT,
                resolved_payload_json TEXT NOT NULL,
                expires_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                guild_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plugin_state (
                plugin_name TEXT PRIMARY KEY,
                slot TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS indexed_messages (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER,
                sanitized_text TEXT NOT NULL,
                media_metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            );
            """
        )
        await self._sqlite.commit()

    async def _migrate_postgres(self) -> None:
        await self._pg.execute(
            """
            CREATE TABLE IF NOT EXISTS relay_routes (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                source_channel_id BIGINT NOT NULL,
                destination_channel_id BIGINT NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('one_way', 'bidirectional')),
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_relay_routes_source
                ON relay_routes(guild_id, source_channel_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_relay_routes_destination
                ON relay_routes(guild_id, destination_channel_id, enabled);

            CREATE TABLE IF NOT EXISTS relay_message_map (
                id BIGSERIAL PRIMARY KEY,
                source_message_id BIGINT NOT NULL,
                source_channel_id BIGINT NOT NULL,
                destination_message_id BIGINT NOT NULL,
                destination_channel_id BIGINT NOT NULL,
                route_id BIGINT NOT NULL REFERENCES relay_routes(id),
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(source_message_id, source_channel_id, route_id),
                UNIQUE(destination_message_id, destination_channel_id)
            );

            CREATE TABLE IF NOT EXISTS media_cache (
                id BIGSERIAL PRIMARY KEY,
                original_url_hash TEXT NOT NULL UNIQUE,
                provider TEXT,
                title TEXT,
                thumbnail_url TEXT,
                media_type TEXT,
                resolved_payload_json JSONB NOT NULL,
                expires_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                actor_id BIGINT,
                guild_id BIGINT,
                channel_id BIGINT,
                message_id BIGINT,
                details_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plugin_state (
                plugin_name TEXT PRIMARY KEY,
                slot TEXT NOT NULL,
                enabled BOOLEAN NOT NULL,
                config_json JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            );

            CREATE TABLE IF NOT EXISTS indexed_messages (
                message_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                author_id BIGINT,
                sanitized_text TEXT NOT NULL,
                media_metadata_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                indexed_at TIMESTAMPTZ NOT NULL
            );
            """
        )

    def _sqlite_path(self) -> Path:
        if self.database_url == ":memory:":
            return Path(":memory:")
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.removeprefix("sqlite:///"))
        if self.database_url.startswith("sqlite://"):
            return Path(self.database_url.removeprefix("sqlite://"))
        return Path(self.database_url)

    def _route_from_row(self, row: Any) -> RelayRoute:
        return RelayRoute(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            source_channel_id=int(row["source_channel_id"]),
            destination_channel_id=int(row["destination_channel_id"]),
            direction=str(row["direction"]),
            enabled=bool(row["enabled"]),
            created_by=int(row["created_by"]) if row["created_by"] is not None else None,
            created_at=row["created_at"],
        )

    def _reverse_route(self, route: RelayRoute) -> RelayRoute:
        return RelayRoute(
            id=route.id,
            guild_id=route.guild_id,
            source_channel_id=route.destination_channel_id,
            destination_channel_id=route.source_channel_id,
            direction=route.direction,
            enabled=route.enabled,
            created_by=route.created_by,
            created_at=route.created_at,
        )

    def _validate_direction(self, direction: str) -> None:
        if direction not in {"one_way", "bidirectional"}:
            raise ValueError("direction must be one_way or bidirectional")

    @property
    def _sqlite(self) -> aiosqlite.Connection:
        if self._conn is None or self.kind != "sqlite":
            raise RuntimeError("SQLite database is not connected.")
        return self._conn

    @property
    def _pg(self) -> asyncpg.Connection:
        if self._conn is None or self.kind != "postgres":
            raise RuntimeError("PostgreSQL database is not connected.")
        return self._conn
