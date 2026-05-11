"""
Tickets - channel-per-ticket support system.

Flow:
    /ticket panel <#channel>    Mods post a button panel; users click -> ticket opens
    /ticket open [reason]       Open a ticket directly via slash
    Inside ticket channel:
        /ticket close           Archive + delete the channel
        /ticket add @user       Grant a user channel access
        /ticket remove @user    Revoke
        /ticket setup ...       Configure category, log channel, staff role

DB: tickets(id, guild_id, channel_id, opener_id, status, opened_at, closed_at, reason)
    + guild_config.tickets_category_id, tickets_log_channel, tickets_staff_role
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok, warn
from utils.helpers import safe_send

log = logging.getLogger("loki.tickets")

REQUIRED_COLS = {
    "id",
    "guild_id",
    "channel_id",
    "opener_id",
    "status",
    "opened_at",
    "closed_at",
    "reason",
}

EXTRA_CONFIG_COLS = [
    ("tickets_category_id", "INTEGER"),
    ("tickets_log_channel", "INTEGER"),
    ("tickets_staff_role", "INTEGER"),
]

_ticket_open_locks: dict[tuple[int, int], asyncio.Lock] = {}
_ticket_close_locks: dict[int, asyncio.Lock] = {}


def _open_lock(guild_id: int, user_id: int) -> asyncio.Lock:
    return _ticket_open_locks.setdefault((guild_id, user_id), asyncio.Lock())


def _close_lock(channel_id: int) -> asyncio.Lock:
    return _ticket_close_locks.setdefault(channel_id, asyncio.Lock())


async def _ensure_schema():
    async with db.get() as c:
        # Detect old schema; if mismatch, drop + recreate (safe - 0 rows).
        cur = await c.execute("PRAGMA table_info(tickets)")
        cols = {r[1] for r in await cur.fetchall()}
        if cols and not REQUIRED_COLS.issubset(cols):
            log.warning("tickets schema mismatch - recreating (existing rows discarded)")
            await c.execute("DROP TABLE tickets")
        await c.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL UNIQUE,
                opener_id   INTEGER NOT NULL,
                status      TEXT NOT NULL DEFAULT 'open',
                opened_at   INTEGER NOT NULL,
                closed_at   INTEGER,
                reason      TEXT
            )
            """
        )
        await c.execute("CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id, status)")
        await c.execute("CREATE INDEX IF NOT EXISTS idx_tickets_opener ON tickets(opener_id)")

        cur = await c.execute("PRAGMA table_info(guild_config)")
        gc_cols = {r[1] for r in await cur.fetchall()}
        for col, typ in EXTRA_CONFIG_COLS:
            if col not in gc_cols:
                await c.execute(f"ALTER TABLE guild_config ADD COLUMN {col} {typ}")
        await c.commit()


async def _open_ticket(guild: discord.Guild, opener: discord.Member, reason: str = "") -> Optional[discord.TextChannel]:
    async with db.get() as c:
        cur = await c.execute(
            "SELECT tickets_category_id, tickets_staff_role FROM guild_config WHERE guild_id=?",
            (guild.id,),
        )
        row = await cur.fetchone()
    cat_id, staff_role_id = row or (None, None)

    category = guild.get_channel(cat_id) if cat_id else None
    if cat_id and not isinstance(category, discord.CategoryChannel):
        category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
            read_message_history=True,
        ),
    }
    if staff_role_id:
        staff = guild.get_role(staff_role_id)
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
            )

    name = f"ticket-{opener.name}".lower().replace(" ", "-")[:90]
    try:
        channel = await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=(f"Ticket opened by {opener} | reason: {reason[:200]}" if reason else f"Ticket opened by {opener}"),
            reason=f"Ticket opened by {opener}",
        )
    except discord.Forbidden:
        return None

    async with db.get() as c:
        await c.execute(
            "INSERT INTO tickets(guild_id, channel_id, opener_id, status, opened_at, reason) VALUES(?,?,?,?,?,?)",
            (guild.id, channel.id, opener.id, "open", int(time.time()), reason or None),
        )
        await c.commit()

    e = info(
        f"Ticket #{channel.name}",
        f"Hi {opener.mention} - staff will be with you shortly.\n"
        "Use `/ticket close` (or the button below) when resolved.",
    )
    if reason:
        e.add_field(name="Reason", value=reason[:1024], inline=False)
    try:
        await safe_send(
            channel,
            content=opener.mention,
            embed=e,
            view=TicketChannelView(),
            dedupe_key=f"ticket-open:{channel.id}:{opener.id}",
            dedupe_window=30,
        )
    except discord.HTTPException:
        pass
    return channel


class TicketPanelView(discord.ui.View):
    """Mod-deployed panel with an Open button - persistent (custom_id)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open ticket",
        emoji="\N{ADMISSION TICKETS}",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:open",
    )
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        async with _open_lock(interaction.guild.id, interaction.user.id):
            async with db.get() as c:
                cur = await c.execute(
                    "SELECT channel_id FROM tickets WHERE guild_id=? AND opener_id=? AND status='open'",
                    (interaction.guild.id, interaction.user.id),
                )
                row = await cur.fetchone()
            if row:
                ch = interaction.guild.get_channel(row[0])
                return await interaction.response.send_message(
                    embed=warn(f"You already have an open ticket: {ch.mention if ch else f'<#{row[0]}>'}"),
                    ephemeral=True,
                )
            ch = await _open_ticket(interaction.guild, interaction.user)
            if ch:
                await interaction.response.send_message(
                    embed=ok(f"Ticket opened: {ch.mention}"),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=err("Couldn't create channel - bot needs Manage Channels."),
                    ephemeral=True,
                )


async def _close_channel(channel: discord.TextChannel, closer: discord.Member, send_transcript: bool = True):
    """Mark ticket closed, post transcript to log + opener, then delete channel."""
    if not channel.guild:
        return
    async with db.get() as c:
        cur = await c.execute(
            "SELECT opener_id, tickets.status, tickets_log_channel FROM tickets "
            "LEFT JOIN guild_config ON guild_config.guild_id = tickets.guild_id "
            "WHERE channel_id=?",
            (channel.id,),
        )
        row = await cur.fetchone()
    if not row:
        return
    opener_id, status, log_ch_id = row
    if status != "open":
        return

    async with db.get() as c:
        await c.execute(
            "UPDATE tickets SET status='closed', closed_at=? WHERE channel_id=?",
            (int(time.time()), channel.id),
        )
        await c.commit()

    transcript = None
    if send_transcript:
        try:
            lines = []
            async for m in channel.history(limit=500, oldest_first=True):
                lines.append(f"[{m.created_at:%Y-%m-%d %H:%M}] {m.author}: {m.content}")
            transcript = io.BytesIO("\n".join(lines).encode("utf-8"))
        except discord.HTTPException:
            transcript = None

    if log_ch_id:
        log_ch = channel.guild.get_channel(log_ch_id)
        if log_ch:
            e = info(
                f"Ticket closed: #{channel.name}",
                f"Closed by {closer.mention}\nOpener: <@{opener_id}>",
            )
            try:
                if transcript:
                    transcript.seek(0)
                    await safe_send(
                        log_ch,
                        embed=e,
                        file=discord.File(transcript, filename=f"{channel.name}.txt"),
                        dedupe_key=f"ticket-close-log:{channel.id}",
                        dedupe_window=60,
                    )
                else:
                    await safe_send(
                        log_ch,
                        embed=e,
                        dedupe_key=f"ticket-close-log:{channel.id}",
                        dedupe_window=60,
                    )
            except discord.HTTPException:
                pass

    if transcript:
        try:
            opener = await channel.guild.fetch_member(opener_id)
            transcript.seek(0)
            await opener.send(
                f"Transcript of your ticket in **{channel.guild.name}**",
                file=discord.File(transcript, filename=f"{channel.name}.txt"),
            )
        except (discord.HTTPException, discord.NotFound):
            pass

    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Ticket closed by {closer}")
    except discord.HTTPException:
        pass


class TicketChannelView(discord.ui.View):
    """In-ticket close button - persistent."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close ticket",
        emoji="\N{LOCK}",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
    )
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch = interaction.channel
        async with _close_lock(ch.id):
            async with db.get() as c:
                cur = await c.execute(
                    "SELECT opener_id, status FROM tickets WHERE channel_id=?",
                    (ch.id,),
                )
                row = await cur.fetchone()
            if not row:
                return await interaction.response.send_message(
                    embed=err("Not a tracked ticket channel."),
                    ephemeral=True,
                )
            opener_id, status = row
            if status != "open":
                return await interaction.response.send_message(
                    embed=warn("Already closed."),
                    ephemeral=True,
                )
            is_staff = interaction.user.guild_permissions.manage_messages
            if interaction.user.id != opener_id and not is_staff:
                return await interaction.response.send_message(
                    embed=err("Only the opener or staff can close."),
                    ephemeral=True,
                )
            await interaction.response.send_message(embed=info("Closing in 5 seconds..."))
            await _close_channel(ch, interaction.user)


class Tickets(commands.Cog):
    """Channel-per-ticket support system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await _ensure_schema()
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketChannelView())

    @commands.hybrid_group(
        name="ticket",
        invoke_without_command=True,
        description="Open or manage support tickets",
    )
    async def ticket(self, ctx):
        await ctx.send(
            embed=info(
                "Tickets",
                "`/ticket open [reason]` - open a ticket\n"
                "`/ticket panel #channel` - post a button panel (mod)\n"
                "`/ticket close` - close current ticket\n"
                "`/ticket add @user` / `/ticket remove @user` - manage access\n"
                "`/ticket status` - review current ticket config\n"
                "`/ticket setup` - configure category / log / staff role",
            )
        )

    @ticket.command(name="open", description="Open a new support ticket")
    @app_commands.describe(reason="Brief reason (optional)")
    async def ticket_open(self, ctx, *, reason: str = ""):
        if not ctx.guild:
            return await ctx.send(embed=err("Tickets only work in a server."))
        async with _open_lock(ctx.guild.id, ctx.author.id):
            async with db.get() as c:
                cur = await c.execute(
                    "SELECT channel_id FROM tickets WHERE guild_id=? AND opener_id=? AND status='open'",
                    (ctx.guild.id, ctx.author.id),
                )
                row = await cur.fetchone()
            if row:
                ch = ctx.guild.get_channel(row[0])
                return await ctx.send(
                    embed=warn(f"You already have an open ticket: {ch.mention if ch else f'<#{row[0]}>'}")
                )
            ch = await _open_ticket(ctx.guild, ctx.author, reason=reason)
            if ch:
                await ctx.send(embed=ok(f"Ticket opened: {ch.mention}"))
            else:
                await ctx.send(embed=err("Couldn't create channel - bot needs Manage Channels."))

    @ticket.command(name="panel", description="Post a ticket button panel in a channel")
    @app_commands.describe(channel="Where to post the panel")
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx, channel: discord.TextChannel):
        e = info("Need help?", "Click below to open a private ticket with staff.")
        try:
            await channel.send(embed=e, view=TicketPanelView())
            await ctx.send(embed=ok(f"Panel posted in {channel.mention}"))
        except discord.Forbidden:
            await ctx.send(embed=err(f"Missing perms to post in {channel.mention}"))

    @ticket.command(name="close", description="Close the current ticket channel")
    async def ticket_close(self, ctx):
        async with _close_lock(ctx.channel.id):
            async with db.get() as c:
                cur = await c.execute(
                    "SELECT opener_id, status FROM tickets WHERE channel_id=?",
                    (ctx.channel.id,),
                )
                row = await cur.fetchone()
            if not row:
                return await ctx.send(embed=err("Not a ticket channel."))
            opener_id, status = row
            if status != "open":
                return await ctx.send(embed=warn("Already closed."))
            is_staff = ctx.author.guild_permissions.manage_messages
            if ctx.author.id != opener_id and not is_staff:
                return await ctx.send(embed=err("Only the opener or staff can close."))
            await ctx.send(embed=info("Closing in 5s..."))
            await _close_channel(ctx.channel, ctx.author)

    @ticket.command(name="status", description="Show the current ticket configuration for this server")
    @commands.has_permissions(manage_guild=True)
    async def ticket_status(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT tickets_category_id, tickets_log_channel, tickets_staff_role "
                "FROM guild_config WHERE guild_id=?",
                (ctx.guild.id,),
            )
            config = await cur.fetchone()
            cur = await c.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id=? AND status='open'",
                (ctx.guild.id,),
            )
            open_count = (await cur.fetchone())[0]
        category_id, log_channel_id, staff_role_id = config or (None, None, None)
        category = ctx.guild.get_channel(category_id) if category_id else None
        log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
        staff_role = ctx.guild.get_role(staff_role_id) if staff_role_id else None
        embed = info("Ticket configuration")
        embed.add_field(name="Category", value=category.mention if category else "Not configured", inline=False)
        embed.add_field(
            name="Log channel", value=log_channel.mention if log_channel else "Not configured", inline=False
        )
        embed.add_field(name="Staff role", value=staff_role.mention if staff_role else "Not configured", inline=False)
        embed.add_field(name="Open tickets", value=str(open_count))
        await ctx.send(embed=embed)

    @ticket.command(name="add", description="Grant a user access to this ticket")
    @app_commands.describe(member="User to add")
    @commands.has_permissions(manage_messages=True)
    async def ticket_add(self, ctx, member: discord.Member):
        async with db.get() as c:
            cur = await c.execute("SELECT 1 FROM tickets WHERE channel_id=?", (ctx.channel.id,))
            if not await cur.fetchone():
                return await ctx.send(embed=err("Not a ticket channel."))
        try:
            await ctx.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
            await ctx.send(embed=ok(f"Added {member.mention} to ticket."))
        except discord.Forbidden:
            await ctx.send(embed=err("Missing perms."))

    @ticket.command(name="remove", description="Revoke a user's access to this ticket")
    @app_commands.describe(member="User to remove")
    @commands.has_permissions(manage_messages=True)
    async def ticket_remove(self, ctx, member: discord.Member):
        async with db.get() as c:
            cur = await c.execute("SELECT 1 FROM tickets WHERE channel_id=?", (ctx.channel.id,))
            if not await cur.fetchone():
                return await ctx.send(embed=err("Not a ticket channel."))
        try:
            await ctx.channel.set_permissions(member, overwrite=None)
            await ctx.send(embed=ok(f"Removed {member.mention} from ticket."))
        except discord.Forbidden:
            await ctx.send(embed=err("Missing perms."))

    @ticket.command(name="setup", description="Configure ticket category, log channel and staff role")
    @app_commands.describe(
        category="Category for new ticket channels",
        log_channel="Channel for close logs + transcripts",
        staff_role="Role granted access to all tickets",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        ctx,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel,
        staff_role: discord.Role,
    ):
        async with db.get() as c:
            await c.execute(
                "INSERT INTO guild_config(guild_id) VALUES(?) ON CONFLICT(guild_id) DO NOTHING",
                (ctx.guild.id,),
            )
            await c.execute(
                "UPDATE guild_config SET tickets_category_id=?, tickets_log_channel=?, "
                "tickets_staff_role=? WHERE guild_id=?",
                (category.id, log_channel.id, staff_role.id, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(
            embed=ok(
                f"Tickets wired:\n"
                f"- Category: {category.mention}\n"
                f"- Log: {log_channel.mention}\n"
                f"- Staff role: {staff_role.mention}"
            )
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
