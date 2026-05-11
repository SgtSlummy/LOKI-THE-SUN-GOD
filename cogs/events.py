"""
Event management with embedded messages, reminders, and reposting.

Commands:
  !event create <title> | <datetime> | <description> [| <location>]
      datetime: "2025-06-15 18:00" or relative "2h30m"
  !event list
  !event info <id>
  !event cancel <id>
  !event remind <id> <offset>
  !event repost <id> <interval>
  !event unrepost <id>
  !event color <id> <hex>
  !event edit <id> title|desc|location|time <new value>
"""

from datetime import datetime, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import db
from utils.helpers import fmt_duration, now, parse_duration, safe_send


def parse_dt(value: str) -> int | None:
    """Parse an absolute datetime or relative duration into a Unix timestamp."""
    value = value.strip()
    secs = parse_duration(value)
    if secs:
        return now() + secs
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            pass
    return None


def event_embed(title, description, starts_at, host: discord.Member | None, location, color, eid):
    embed = discord.Embed(title=f"[Event] {title}", description=description, color=color)
    embed.add_field(name="When", value=f"<t:{starts_at}:F> (<t:{starts_at}:R>)", inline=False)
    if location:
        embed.add_field(name="Where", value=location, inline=False)
    if host:
        embed.add_field(name="Host", value=host.mention, inline=True)
    embed.set_footer(text=f"Event #{eid} | React with yes / no / maybe")
    return embed


async def add_rsvp_reactions(message: discord.Message):
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    await message.add_reaction("🤔")


class Events(commands.Cog):
    """Create, remind, and repost Discord events."""

    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()
        self.repost_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()
        self.repost_loop.cancel()

    @commands.hybrid_group(
        name="event",
        invoke_without_command=True,
        description="Manage scheduled events for this server",
    )
    async def event(self, ctx):
        await ctx.send(
            "Event commands: `create`, `list`, `info`, `cancel`, `remind`, `repost`, `unrepost`, `edit`, `color`."
        )

    @event.command(name="create", description="Create a new scheduled event entry")
    @app_commands.describe(
        body="Format: Title | 2026-05-01 19:00 | Description | Optional location",
    )
    @commands.has_permissions(manage_events=True)
    async def event_create(self, ctx, *, body: str):
        parts = [part.strip() for part in body.split("|")]
        if len(parts) < 3:
            return await ctx.send("Use `!event create Title | 2025-06-15 18:00 | Description [| Location]`.")
        if not parts[0]:
            return await ctx.send("Event title is required.")
        if not parts[2]:
            return await ctx.send("Event description is required.")

        title = parts[0]
        starts_at = parse_dt(parts[1])
        if not starts_at:
            return await ctx.send("Invalid datetime. Use `2025-06-15 18:00` (UTC) or a relative offset like `2h30m`.")
        description = parts[2]
        location = parts[3] if len(parts) > 3 else ""
        color = 0x57F287

        async with db.get() as c:
            cur = await c.execute(
                "INSERT INTO events(guild_id,channel_id,message_id,title,description,starts_at,host_id,color,location) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (ctx.guild.id, ctx.channel.id, 0, title, description, starts_at, ctx.author.id, color, location),
            )
            eid = cur.lastrowid
            await c.commit()

        embed = event_embed(title, description, starts_at, ctx.author, location, color, eid)
        msg = await ctx.send(embed=embed)
        await add_rsvp_reactions(msg)

        async with db.get() as c:
            await c.execute(
                "UPDATE events SET message_id=?, channel_id=? WHERE id=?",
                (msg.id, ctx.channel.id, eid),
            )
            await c.commit()

        await ctx.send(
            f"Event **#{eid}** created. Add reminders with `!event remind {eid} 1h`. "
            f"Auto-repost with `!event repost {eid} 6h`.",
            delete_after=15,
        )

    @event.command(name="list", description="List saved events for this server")
    async def event_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, title, starts_at, location FROM events "
                "WHERE guild_id=? AND starts_at>? ORDER BY starts_at LIMIT 15",
                (ctx.guild.id, now()),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("No upcoming events are scheduled.")
        embed = discord.Embed(title="Upcoming Events", color=0x5865F2)
        for eid, title, starts_at, location in rows:
            value = f"<t:{starts_at}:F>"
            if location:
                value += f"\nWhere: {location}"
            embed.add_field(name=f"#{eid} {title}", value=value, inline=False)
        await ctx.send(embed=embed)

    @event.command(name="info", description="Show details for a specific event")
    @app_commands.describe(eid="Saved event ID to inspect")
    async def event_info(self, ctx, eid: int):
        async with db.get() as c:
            cur = await c.execute("SELECT * FROM events WHERE id=? AND guild_id=?", (eid, ctx.guild.id))
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f"No event with ID `{eid}` was found.")
            cur = await c.execute("SELECT offset_secs, fired FROM event_reminders WHERE event_id=?", (eid,))
            reminders = await cur.fetchall()
            cur = await c.execute("SELECT interval_secs, next_at FROM event_reposts WHERE event_id=?", (eid,))
            reposts = await cur.fetchall()
        eid, gid, chid, mid, title, desc, starts_at, host_id, color, loc = row
        host = ctx.guild.get_member(host_id)
        embed = discord.Embed(title=f"Event #{eid}: {title}", color=color)
        embed.add_field(name="When", value=f"<t:{starts_at}:F>")
        if loc:
            embed.add_field(name="Where", value=loc)
        embed.add_field(name="Host", value=str(host or host_id))
        if mid:
            channel = self.bot.get_channel(chid)
            if channel:
                embed.add_field(
                    name="Message",
                    value=f"[Jump](https://discord.com/channels/{gid}/{chid}/{mid})",
                    inline=False,
                )
        if reminders:
            embed.add_field(
                name="Reminders",
                value="\n".join(
                    f"{'done' if fired else 'pending'} {fmt_duration(offset)} before" for offset, fired in reminders
                ),
                inline=False,
            )
        if reposts:
            embed.add_field(
                name="Reposts",
                value="\n".join(f"every {fmt_duration(interval)}" for interval, _ in reposts),
                inline=False,
            )
        await ctx.send(embed=embed)

    @event.command(name="cancel", description="Cancel an existing event")
    @app_commands.describe(eid="Saved event ID to cancel")
    @commands.has_permissions(manage_events=True)
    async def event_cancel(self, ctx, eid: int):
        async with db.get() as c:
            cur = await c.execute("DELETE FROM events WHERE id=? AND guild_id=?", (eid, ctx.guild.id))
            await c.execute("DELETE FROM event_reminders WHERE event_id=?", (eid,))
            await c.execute("DELETE FROM event_reposts WHERE event_id=?", (eid,))
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"Event #{eid} was cancelled.")
        else:
            await ctx.send(f"No event with ID `{eid}` was found.")

    @event.command(name="remind", description="Schedule a reminder before an event")
    @app_commands.describe(
        eid="Saved event ID that should receive a reminder",
        offset="How long before the event to send the reminder, such as 30m or 1h",
    )
    @commands.has_permissions(manage_events=True)
    async def event_remind(self, ctx, eid: int, offset: str):
        secs = parse_duration(offset)
        if not secs:
            return await ctx.send("Invalid reminder offset. Use values like `30m`, `1h`, or `1d`.")
        async with db.get() as c:
            cur = await c.execute("SELECT 1 FROM events WHERE id=? AND guild_id=?", (eid, ctx.guild.id))
            if not await cur.fetchone():
                return await ctx.send(f"No event with ID `{eid}` was found.")
            await c.execute("INSERT INTO event_reminders(event_id,offset_secs) VALUES(?,?)", (eid, secs))
            await c.commit()
        await ctx.send(f"Reminder scheduled for {fmt_duration(secs)} before event #{eid}.")

    @event.command(name="repost", description="Schedule repeated reposts for an event")
    @app_commands.describe(
        eid="Saved event ID you want reposted",
        interval="Requested repost cadence, such as 6h",
    )
    @commands.has_permissions(manage_events=True)
    async def event_repost(self, ctx, eid: int, interval: str):
        secs = parse_duration(interval)
        if not secs:
            return await ctx.send("Invalid repost interval. Use values like `30m`, `1h`, or `1d`.")
        async with db.get() as c:
            cur = await c.execute(
                "SELECT starts_at FROM events WHERE id=? AND guild_id=?",
                (eid, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f"No event with ID `{eid}` was found.")
            if row[0] <= now():
                return await ctx.send(f"Event #{eid} has already started.")
            await c.execute("DELETE FROM event_reposts WHERE event_id=?", (eid,))
            await c.execute(
                "INSERT INTO event_reposts(event_id,interval_secs,next_at) VALUES(?,?,?)",
                (eid, secs, now() + secs),
            )
            await c.commit()
        await ctx.send(f"Event #{eid} will repost every {fmt_duration(secs)}.")

    @event.command(name="unrepost", description="Stop reposting an event")
    @app_commands.describe(eid="Saved event ID that should stop reposting")
    @commands.has_permissions(manage_events=True)
    async def event_unrepost(self, ctx, eid: int):
        async with db.get() as c:
            cur = await c.execute("DELETE FROM event_reposts WHERE event_id=?", (eid,))
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"Removed repost scheduling for event #{eid}.")
        else:
            await ctx.send(f"No repost schedule was found for event #{eid}.")

    @event.command(name="color", description="Change the accent color used for an event")
    @app_commands.describe(
        eid="Saved event ID to update",
        hex_color="Hex color like #57F287",
    )
    @commands.has_permissions(manage_events=True)
    async def event_color(self, ctx, eid: int, hex_color: str):
        try:
            color = int(hex_color.strip("#"), 16)
        except ValueError:
            return await ctx.send("Invalid color. Use a hex value like `#57F287`.")
        async with db.get() as c:
            cur = await c.execute("UPDATE events SET color=? WHERE id=? AND guild_id=?", (color, eid, ctx.guild.id))
            await c.commit()
        if not cur.rowcount:
            return await ctx.send(f"No event with ID `{eid}` was found.")
        await ctx.send(f"Updated the color for event #{eid}.")
        await self._refresh_embed(eid)

    @event.command(name="edit", description="Edit a saved event field")
    @app_commands.describe(
        eid="Saved event ID to edit",
        field="Event field that should change",
        value="Replacement value for the chosen field",
    )
    @commands.has_permissions(manage_events=True)
    async def event_edit(
        self,
        ctx,
        eid: int,
        field: Literal["title", "desc", "description", "location", "loc", "time"],
        *,
        value: str,
    ):
        col_map = {
            "title": "title",
            "desc": "description",
            "description": "description",
            "location": "location",
            "loc": "location",
            "time": "starts_at",
        }
        col = col_map.get(field.lower())
        if not col:
            return await ctx.send("Field must be one of: `title`, `desc`, `location`, `time`.")
        if col == "starts_at":
            value = parse_dt(value)
            if not value:
                return await ctx.send("Invalid datetime. Use `2025-06-15 18:00` or a relative offset like `2h30m`.")
        async with db.get() as c:
            cur = await c.execute(f"UPDATE events SET {col}=? WHERE id=? AND guild_id=?", (value, eid, ctx.guild.id))
            await c.commit()
        if not cur.rowcount:
            return await ctx.send(f"No event with ID `{eid}` was found.")
        await ctx.send(f"Updated `{field}` for event #{eid}.")
        await self._refresh_embed(eid)

    async def _refresh_embed(self, eid: int):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT guild_id, channel_id, message_id, title, description, starts_at, host_id, color, location "
                "FROM events WHERE id=?",
                (eid,),
            )
            row = await cur.fetchone()
        if not row:
            return
        guild_id, channel_id, message_id, title, desc, starts_at, host_id, color, loc = row
        guild = self.bot.get_guild(guild_id)
        channel = self.bot.get_channel(channel_id)
        if not channel or not message_id:
            return
        host = guild.get_member(host_id) if guild else None
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=event_embed(title, desc, starts_at, host, loc, color, eid))
        except discord.NotFound:
            pass

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT er.id, er.event_id, er.offset_secs, "
                "e.guild_id, e.channel_id, e.title, e.starts_at, e.host_id, e.description, e.location, e.color "
                "FROM event_reminders er "
                "JOIN events e ON e.id = er.event_id "
                "WHERE er.fired=0 AND (e.starts_at - er.offset_secs) <= ?",
                (now(),),
            )
            rows = await cur.fetchall()
            for rid, eid, offset, guild_id, channel_id, title, starts_at, host_id, desc, loc, color in rows:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    guild = self.bot.get_guild(guild_id)
                    host = guild.get_member(host_id) if guild else None
                    embed = discord.Embed(
                        title=f"Reminder: {title}",
                        description=f"Starting <t:{starts_at}:R>",
                        color=0xFEE75C,
                    )
                    embed.add_field(name="When", value=f"<t:{starts_at}:F>")
                    if loc:
                        embed.add_field(name="Where", value=loc)
                    if host:
                        embed.add_field(name="Host", value=host.mention)
                    try:
                        await safe_send(channel, embed=embed, dedupe_key=f"event-reminder:{rid}", dedupe_window=60)
                    except discord.Forbidden:
                        pass
                await c.execute("UPDATE event_reminders SET fired=1 WHERE id=?", (rid,))
            await c.commit()

    @tasks.loop(seconds=60)
    async def repost_loop(self):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT er.id, er.event_id, er.interval_secs, "
                "e.guild_id, e.channel_id, e.title, e.description, e.starts_at, e.host_id, e.color, e.location "
                "FROM event_reposts er "
                "JOIN events e ON e.id = er.event_id "
                "WHERE er.next_at <= ? AND e.starts_at > ?",
                (now(), now()),
            )
            rows = await cur.fetchall()
            for repost_id, eid, interval, guild_id, channel_id, title, desc, starts_at, host_id, color, loc in rows:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    guild = self.bot.get_guild(guild_id)
                    host = guild.get_member(host_id) if guild else None
                    embed = event_embed(title, desc, starts_at, host, loc, color, eid)
                    try:
                        msg = await safe_send(
                            channel,
                            embed=embed,
                            dedupe_key=f"event-repost:{repost_id}",
                            dedupe_window=120,
                        )
                        if msg is not None:
                            await add_rsvp_reactions(msg)
                            async with db.get() as c2:
                                await c2.execute(
                                    "UPDATE events SET message_id=?, channel_id=? WHERE id=?",
                                    (msg.id, channel.id, eid),
                                )
                                await c2.commit()
                    except discord.Forbidden:
                        pass
                await c.execute("UPDATE event_reposts SET next_at=? WHERE id=?", (now() + interval, repost_id))
            await c.commit()

    @reminder_loop.before_loop
    @repost_loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Events(bot))
