from __future__ import annotations

import asyncio
from types import SimpleNamespace

from cogs.loki_activities import LokiActivities
from loki_engine.permissions import MANAGE_EVENTS


class FakeBridgeClient:
    def __init__(self):
        self.controls = []
        self.room_requests = []

    def health(self):
        return {"ok": True, "service": "activity-bridge", "status_code": 200}

    def list_rooms(self):
        return {
            "ok": True,
            "rooms": [
                {"id": "123:456", "participants": [{"id": "u1"}, {"id": "u2"}], "state": {"playing": True}},
                {"id": "123:dashboard", "participants": [], "state": {"playing": False}},
            ],
        }

    def get_room(self, room_id):
        self.room_requests.append(room_id)
        return {"ok": True, "room": {"id": room_id, "participants": [{"id": "u1"}], "state": {"playing": False}}}

    def control(self, room_id, action, **payload):
        self.controls.append((room_id, action, payload))
        return {"ok": True, "message": "accepted", "room": {"id": room_id}}


class FakeCtx:
    def __init__(self, *, guild_id=123, channel_id=456, permissions=0):
        self.guild = SimpleNamespace(id=guild_id) if guild_id is not None else None
        self.channel = SimpleNamespace(id=channel_id) if channel_id is not None else None
        self.author = SimpleNamespace(id=789, guild_permissions=SimpleNamespace(value=permissions))
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))


def test_activity_status_reads_bridge_health_and_room_snapshot():
    cog = LokiActivities(bot=object(), bridge_client=FakeBridgeClient())
    ctx = FakeCtx()

    asyncio.run(cog._send_bridge_status(ctx))

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert kwargs["allowed_mentions"].everyone is False
    assert "Activity Bridge: online" in content
    assert "Rooms: 2" in content
    assert "Participants: 2" in content


def test_activity_room_status_uses_guild_channel_room_id():
    cog = LokiActivities(bot=object(), bridge_client=FakeBridgeClient())
    ctx = FakeCtx()

    asyncio.run(cog._send_room_status(ctx))

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert "Room `123:456`" in content
    assert "Participants: 1" in content


def test_activity_room_status_rejects_explicit_room_id_without_manage_permission():
    bridge = FakeBridgeClient()
    cog = LokiActivities(bot=object(), bridge_client=bridge)
    ctx = FakeCtx(permissions=0)

    asyncio.run(cog._send_room_status(ctx, room_id="999:dashboard"))

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert "requires create-events, manage-events, or admin" in content
    assert bridge.room_requests == []


def test_activity_room_status_allows_explicit_room_id_for_activity_manager():
    bridge = FakeBridgeClient()
    cog = LokiActivities(bot=object(), bridge_client=bridge)
    ctx = FakeCtx(permissions=MANAGE_EVENTS)

    asyncio.run(cog._send_room_status(ctx, room_id="999:dashboard"))

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert "Room `999:dashboard`" in content
    assert bridge.room_requests == ["999:dashboard"]


def test_activity_control_requires_manage_activity_permission_before_bridge_write():
    bridge = FakeBridgeClient()
    cog = LokiActivities(bot=object(), bridge_client=bridge)
    ctx = FakeCtx(permissions=0)

    asyncio.run(cog._send_room_control(ctx, action="pause"))

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert "requires create-events, manage-events, or admin" in content
    assert bridge.controls == []


def test_activity_control_calls_bridge_for_authorized_operator():
    bridge = FakeBridgeClient()
    cog = LokiActivities(bot=object(), bridge_client=bridge)
    ctx = FakeCtx(permissions=MANAGE_EVENTS)

    asyncio.run(
        cog._send_room_control(
            ctx,
            action="set",
            media_url="https://media.example/video.mp4",
            title="Solar Room",
        )
    )

    content, kwargs = ctx.sent[-1]
    assert kwargs.get("ephemeral") is True
    assert "accepted" in content
    assert bridge.controls == [
        (
            "123:456",
            "set",
            {"url": "https://media.example/video.mp4", "title": "Solar Room"},
        )
    ]
