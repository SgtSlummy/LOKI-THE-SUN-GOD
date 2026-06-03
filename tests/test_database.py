from datetime import datetime

import pytest

from bot.services.database import Database


class FakePostgresConnection:
    def __init__(self):
        self.execute_calls = []
        self.fetchrow_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append(args)
        return "INSERT 0 1"

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append(args)
        return {
            "id": 1,
            "guild_id": args[0],
            "source_channel_id": args[1],
            "destination_channel_id": args[2],
            "direction": args[3],
            "enabled": True,
            "created_by": args[4],
            "created_at": args[5],
        }


@pytest.mark.asyncio
async def test_postgres_writes_bind_datetime_values_for_timestamptz_columns():
    db = Database("postgresql://example")
    fake_pg = FakePostgresConnection()
    db._conn = fake_pg

    await db.add_relay_route(
        guild_id=1,
        source_channel_id=10,
        destination_channel_id=20,
        direction="one_way",
        created_by=99,
    )
    await db.record_message_map(
        source_message_id=111,
        source_channel_id=10,
        destination_message_id=555,
        destination_channel_id=20,
        route_id=1,
    )
    await db.cache_media(
        original_url_hash="hash",
        provider="provider",
        title="title",
        thumbnail_url=None,
        media_type="image",
        resolved_payload={},
        expires_at="2026-06-03T14:19:13.140746+00:00",
    )
    await db.audit(event_type="startup")
    await db.upsert_plugin_state(plugin_name="relay_core", slot="relay_core", enabled=True)

    timestamp_values = [
        fake_pg.fetchrow_calls[0][-1],
        fake_pg.execute_calls[0][-1],
        fake_pg.execute_calls[1][-1],
        fake_pg.execute_calls[2][-1],
        fake_pg.execute_calls[3][-1],
    ]

    for value in timestamp_values:
        assert isinstance(value, datetime)
        assert value.tzinfo is not None


@pytest.mark.asyncio
async def test_route_lookup_supports_one_way_and_bidirectional_routes(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'relay.db'}")
    await db.connect()
    await db.migrate()

    one_way = await db.add_relay_route(
        guild_id=1,
        source_channel_id=10,
        destination_channel_id=20,
        direction="one_way",
        created_by=99,
    )
    bidirectional = await db.add_relay_route(
        guild_id=1,
        source_channel_id=30,
        destination_channel_id=40,
        direction="bidirectional",
        created_by=99,
    )

    assert [route.destination_channel_id for route in await db.routes_for_source(1, 10)] == [20]
    assert [route.destination_channel_id for route in await db.routes_for_source(1, 20)] == []
    reverse = await db.routes_for_source(1, 40)
    assert len(reverse) == 1
    assert reverse[0].id == bidirectional.id
    assert reverse[0].source_channel_id == 40
    assert reverse[0].destination_channel_id == 30
    assert one_way.id != bidirectional.id

    await db.close()


@pytest.mark.asyncio
async def test_message_mapping_prevents_relay_loops(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'relay.db'}")
    await db.connect()
    await db.migrate()
    route = await db.add_relay_route(
        guild_id=1,
        source_channel_id=10,
        destination_channel_id=20,
        direction="one_way",
        created_by=99,
    )

    assert await db.is_relayed_message(555, 20) is False

    await db.record_message_map(
        source_message_id=111,
        source_channel_id=10,
        destination_message_id=555,
        destination_channel_id=20,
        route_id=route.id,
    )

    assert await db.is_relayed_message(555, 20) is True
    assert await db.is_source_message_mapped(111, 10, route.id) is True

    await db.close()
