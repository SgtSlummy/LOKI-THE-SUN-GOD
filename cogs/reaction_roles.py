import re

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok

MESSAGE_LINK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(?P<guild_id>\d+)/(?P<channel_id>\d+)/(?P<message_id>\d+)"
)


class ReactionRoles(commands.Cog):
    """Reaction role menus."""

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_message(self, ctx, message_ref: str) -> discord.Message | None:
        value = (message_ref or "").strip()
        if not value:
            return None
        channel = ctx.channel
        message_id = None
        match = MESSAGE_LINK_RE.fullmatch(value)
        if match:
            if int(match.group("guild_id")) != ctx.guild.id:
                return None
            channel = ctx.guild.get_channel(int(match.group("channel_id")))
            message_id = int(match.group("message_id"))
        elif value.isdigit():
            message_id = int(value)
        else:
            return None
        if not channel or not hasattr(channel, "fetch_message"):
            return None
        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _set_mode(self, ctx, message_ref: str, mode: str):
        message = await self._resolve_message(ctx, message_ref)
        if not message:
            return await ctx.send(
                embed=err("Provide a valid message link, or a message ID from the current channel."),
            )
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO rr_message_mode(message_id,mode) VALUES(?,?)",
                (message.id, mode),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Mode `{mode}` set for [message]({message.jump_url})."))

    async def _mode(self, message_id: int):
        async with db.get() as c:
            cur = await c.execute("SELECT mode FROM rr_message_mode WHERE message_id=?", (message_id,))
            row = await cur.fetchone()
        return row[0] if row else "normal"

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage reaction role messages",
    )
    @commands.has_permissions(manage_roles=True)
    async def rr(self, ctx):
        await ctx.send(
            embed=info(
                "Reaction roles",
                "Use `/rr add`, `/rr remove`, `/rr list`, `/rr unique`, "
                "`/rr binding`, `/rr reversed`, `/rr verify`, and `/rr normal`.\n"
                "Message inputs accept a full Discord message link or a message ID from the current channel.",
            )
        )

    @rr.command(name="add", description="Create a reaction role binding")
    @app_commands.describe(
        message_ref="Message link or current-channel message ID to bind",
        emoji="Emoji members should react with",
        role="Role members should receive",
    )
    @commands.has_permissions(manage_roles=True)
    async def add(self, ctx, message_ref: str, emoji: str, role: discord.Role):
        message = await self._resolve_message(ctx, message_ref)
        if not message:
            return await ctx.send(
                embed=err("Provide a valid message link, or a message ID from the current channel."),
            )
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.send(embed=err("That emoji could not be added to the target message."))
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO reaction_roles(guild_id,message_id,channel_id,emoji,role_id) VALUES(?,?,?,?,?)",
                (ctx.guild.id, message.id, message.channel.id, str(emoji), role.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Bound {emoji} to {role.mention} on [message]({message.jump_url})."))

    @rr.command(name="unique", description="Allow only one reaction role from that message at a time")
    @app_commands.describe(message_ref="Message link or current-channel message ID")
    @commands.has_permissions(manage_roles=True)
    async def rr_unique(self, ctx, message_ref: str):
        await self._set_mode(ctx, message_ref, "unique")

    @rr.command(name="binding", description="Make a reaction role stay even if the reaction is removed")
    @app_commands.describe(message_ref="Message link or current-channel message ID")
    @commands.has_permissions(manage_roles=True)
    async def rr_binding(self, ctx, message_ref: str):
        await self._set_mode(ctx, message_ref, "binding")

    @rr.command(name="reversed", description="Reverse the behavior so reactions remove the role")
    @app_commands.describe(message_ref="Message link or current-channel message ID")
    @commands.has_permissions(manage_roles=True)
    async def rr_reversed(self, ctx, message_ref: str):
        await self._set_mode(ctx, message_ref, "reversed")

    @rr.command(name="verify", description="Only add the role; never remove it when the reaction is removed")
    @app_commands.describe(message_ref="Message link or current-channel message ID")
    @commands.has_permissions(manage_roles=True)
    async def rr_verify(self, ctx, message_ref: str):
        await self._set_mode(ctx, message_ref, "verify")

    @rr.command(name="normal", description="Set a reaction role message back to normal mode")
    @app_commands.describe(message_ref="Message link or current-channel message ID")
    @commands.has_permissions(manage_roles=True)
    async def rr_normal(self, ctx, message_ref: str):
        await self._set_mode(ctx, message_ref, "normal")

    @rr.command(name="remove", description="Remove a reaction role binding")
    @app_commands.describe(
        message_ref="Message link or current-channel message ID to edit",
        emoji="Emoji binding to remove from the message",
    )
    @commands.has_permissions(manage_roles=True)
    async def remove(self, ctx, message_ref: str, emoji: str):
        message = await self._resolve_message(ctx, message_ref)
        if not message:
            return await ctx.send(
                embed=err("Provide a valid message link, or a message ID from the current channel."),
            )
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM reaction_roles WHERE message_id=? AND emoji=?",
                (message.id, emoji),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed the {emoji} binding from [message]({message.jump_url})."))
        else:
            await ctx.send(embed=err("That binding was not found on the selected message."))

    @rr.command(name="list", description="List reaction role bindings for this server")
    @commands.has_permissions(manage_roles=True)
    async def rr_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT message_id, channel_id, emoji, role_id FROM reaction_roles "
                "WHERE guild_id=? ORDER BY message_id",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=info("Reaction roles", "No reaction role bindings are configured."))
        embed = discord.Embed(title="Reaction Roles", color=0x5865F2)
        for message_id, channel_id, emoji, role_id in rows[:25]:
            role = ctx.guild.get_role(role_id)
            jump_url = f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{message_id}"
            embed.add_field(
                name=f"Message {message_id}",
                value=f"{emoji} -> {role.mention if role else role_id}\n[Jump to message]({jump_url})",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        async with db.get() as c:
            cur = await c.execute(
                "SELECT role_id FROM reaction_roles WHERE message_id=? AND emoji=?",
                (payload.message_id, str(payload.emoji)),
            )
            row = await cur.fetchone()
            cur = await c.execute(
                "SELECT role_id, emoji FROM reaction_roles WHERE message_id=?",
                (payload.message_id,),
            )
            all_rows = await cur.fetchall()
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(row[0]) if guild else None
        if not role or not payload.member:
            return
        mode = await self._mode(payload.message_id)
        try:
            if mode == "reversed":
                await payload.member.remove_roles(role, reason="Reaction role reversed mode")
            else:
                if mode == "unique":
                    other_roles = [guild.get_role(role_id) for role_id, _emoji in all_rows if role_id != role.id]
                    other_roles = [
                        other_role for other_role in other_roles if other_role and other_role in payload.member.roles
                    ]
                    if other_roles:
                        await payload.member.remove_roles(*other_roles, reason="Reaction role unique mode")
                await payload.member.add_roles(role, reason="Reaction role added")
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        async with db.get() as c:
            cur = await c.execute(
                "SELECT role_id FROM reaction_roles WHERE message_id=? AND emoji=?",
                (payload.message_id, str(payload.emoji)),
            )
            row = await cur.fetchone()
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(row[0]) if guild else None
        if not member or not role:
            return
        mode = await self._mode(payload.message_id)
        if mode in {"binding", "verify"}:
            return
        try:
            if mode == "reversed":
                await member.add_roles(role, reason="Reaction role reversed remove")
            else:
                await member.remove_roles(role, reason="Reaction role removed")
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
