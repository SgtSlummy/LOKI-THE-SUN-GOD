import pytest

from bot.services.database import Database


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

