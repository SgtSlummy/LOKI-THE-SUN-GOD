from __future__ import annotations

import asyncio
from typing import Any

import discord
from discord.ext import commands

from loki_activity_bridge import ActivityBridgeClient, room_id_for
from loki_engine.permissions import PermissionContext, can_create_activity_event, can_manage_activity


class LokiActivities(commands.Cog):
    """Discord Activities and scheduled-event control surface."""

    def __init__(self, bot: commands.Bot, bridge_client: ActivityBridgeClient | None = None):
        self.bot = bot
        self.bridge_client = bridge_client or ActivityBridgeClient()

    def _permission_context(self, ctx: commands.Context) -> PermissionContext:
        return PermissionContext(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            permissions=getattr(ctx.author.guild_permissions, "value", 0),
        )

    def _room_id_for_context(self, ctx: commands.Context) -> str | None:
        if not ctx.guild:
            return None
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        return room_id_for(ctx.guild.id, channel_id)

    async def _safe_reply(self, ctx: commands.Context, content: str) -> None:
        await ctx.send(content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def _bridge_call(self, method_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        method = getattr(self.bridge_client, method_name)
        result = await asyncio.to_thread(method, *args, **kwargs)
        return result if isinstance(result, dict) else {"ok": False}

    async def _defer_if_possible(self, ctx: commands.Context) -> None:
        defer = getattr(ctx, "defer", None)
        if not callable(defer):
            return
        try:
            await defer(ephemeral=True)
        except TypeError:
            await defer()
        except Exception:
            return

    def _room_count_summary(self, rooms: list[dict[str, Any]]) -> tuple[int, int]:
        participants = 0
        for room in rooms:
            participants += len(room.get("participants") or [])
        return len(rooms), participants

    async def _send_bridge_status(self, ctx: commands.Context) -> None:
        health = await self._bridge_call("health")
        rooms_payload = await self._bridge_call("list_rooms")
        rooms = rooms_payload.get("rooms") or []
        room_count, participants = self._room_count_summary(rooms)
        state = "online" if health.get("ok") else "offline"
        status = "health check passed" if health.get("ok") else "health check failed"
        await self._safe_reply(
            ctx,
            "\n".join(
                [
                    f"Activity Bridge: {state}",
                    f"Rooms: {room_count}",
                    f"Participants: {participants}",
                    f"Status: {status}",
                ]
            ),
        )

    async def _send_room_status(self, ctx: commands.Context, room_id: str | None = None) -> None:
        explicit_room_id = bool(room_id)
        if explicit_room_id:
            decision = can_manage_activity(self._permission_context(ctx))
            if not decision.allowed:
                return await self._safe_reply(ctx, decision.reason)
        selected_room_id = room_id or self._room_id_for_context(ctx)
        if not selected_room_id:
            return await self._safe_reply(ctx, "Activity rooms require a server context.")
        payload = await self._bridge_call("get_room", selected_room_id)
        room = payload.get("room") or {}
        participants = len(room.get("participants") or [])
        playing = bool((room.get("state") or {}).get("playing"))
        state = "playing" if playing else "idle"
        await self._safe_reply(ctx, f"Room `{selected_room_id}`: {state}. Participants: {participants}.")

    async def _send_room_control(
        self,
        ctx: commands.Context,
        *,
        action: str,
        media_url: str | None = None,
        title: str | None = None,
        room_id: str | None = None,
    ) -> None:
        decision = can_manage_activity(self._permission_context(ctx))
        if not decision.allowed:
            return await self._safe_reply(ctx, decision.reason)
        selected_room_id = room_id or self._room_id_for_context(ctx)
        if not selected_room_id:
            return await self._safe_reply(ctx, "Activity controls require a server context.")
        payload = await self._bridge_call("control", selected_room_id, action, url=media_url, title=title)
        status = "accepted" if payload.get("ok") else "failed"
        detail = (
            "Bridge accepted the control request."
            if payload.get("ok")
            else "Bridge rejected or failed the control request."
        )
        await self._safe_reply(ctx, f"Activity control {status} for `{selected_room_id}`: {detail}")

    @commands.hybrid_group(name="activity", description="Manage LOKI activities and scheduled events")
    async def activity(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use a subcommand: status, room, set-media, pause, play, next, create-event, or end-event.")

    @activity.command(name="status", description="Show LOKI activity control status")
    async def activity_status(self, ctx: commands.Context):
        await self._defer_if_possible(ctx)
        await self._send_bridge_status(ctx)

    @activity.command(name="room", description="Show the current Activity Bridge room")
    async def activity_room(self, ctx: commands.Context, room_id: str | None = None):
        await self._defer_if_possible(ctx)
        await self._send_room_status(ctx, room_id=room_id)

    @activity.command(name="set-media", description="Set Activity Bridge room media")
    async def activity_set_media(self, ctx: commands.Context, media_url: str, *, title: str | None = None):
        await self._defer_if_possible(ctx)
        await self._send_room_control(ctx, action="set", media_url=media_url, title=title)

    @activity.command(name="pause", description="Pause the Activity Bridge room")
    async def activity_pause(self, ctx: commands.Context):
        await self._defer_if_possible(ctx)
        await self._send_room_control(ctx, action="pause")

    @activity.command(name="play", description="Resume the Activity Bridge room")
    async def activity_play(self, ctx: commands.Context):
        await self._defer_if_possible(ctx)
        await self._send_room_control(ctx, action="play")

    @activity.command(name="next", description="Skip to the next Activity Bridge room item")
    async def activity_next(self, ctx: commands.Context):
        await self._defer_if_possible(ctx)
        await self._send_room_control(ctx, action="next")

    @activity.command(name="create-event", description="Create a tracked activity event")
    @commands.has_permissions(create_events=True)
    async def activity_create_event(self, ctx: commands.Context, *, title: str):
        permissions = getattr(ctx.author.guild_permissions, "value", 0)
        decision = can_create_activity_event(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            )
        )
        if not decision.allowed:
            return await ctx.send(decision.reason)
        await ctx.send(
            f"Activity event creation accepted for **{title}**. Configure full schedule details in the portal."
        )

    @activity.command(name="end-event", description="End or archive a tracked activity event")
    @commands.has_permissions(manage_events=True)
    async def activity_end_event(self, ctx: commands.Context, event_id: str):
        permissions = getattr(ctx.author.guild_permissions, "value", 0)
        decision = can_manage_activity(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            )
        )
        if not decision.allowed:
            return await ctx.send(decision.reason)
        await ctx.send(f"Activity event **{event_id}** marked for shutdown/audit.")


async def setup(bot):
    await bot.add_cog(LokiActivities(bot))
