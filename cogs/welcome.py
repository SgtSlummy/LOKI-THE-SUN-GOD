from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok


def render(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    """Welcome and goodbye messages."""

    def __init__(self, bot):
        self.bot = bot

    async def _config(self, guild_id: int):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (guild_id,))
            await c.commit()
            cur = await c.execute(
                "SELECT welcome_channel, welcome_msg, goodbye_msg FROM guild_config WHERE guild_id=?",
                (guild_id,),
            )
            return await cur.fetchone()

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage welcome and goodbye messaging",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx):
        await ctx.send(
            embed=info(
                "Welcome",
                "Use `/welcome channel`, `/welcome message`, `/welcome bye`, "
                "`/welcome status`, or `/welcome preview`.\n"
                "Placeholders: `{user}`, `{username}`, `{server}`, `{count}`.",
            )
        )

    @welcome.command(name="channel", description="Set the welcome and goodbye message channel")
    @app_commands.describe(channel="Channel where welcome and goodbye messages should be posted")
    @commands.has_permissions(manage_guild=True)
    async def channel(self, ctx, channel: discord.TextChannel):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (ctx.guild.id,))
            await c.execute(
                "UPDATE guild_config SET welcome_channel=? WHERE guild_id=?",
                (channel.id, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Welcome channel set to {channel.mention}."))

    @welcome.command(name="message", description="Set the join message template")
    @app_commands.describe(text="Welcome text to send when a member joins")
    @commands.has_permissions(manage_guild=True)
    async def message(self, ctx, *, text: str):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (ctx.guild.id,))
            await c.execute(
                "UPDATE guild_config SET welcome_msg=? WHERE guild_id=?",
                (text, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok("Welcome message updated."))

    @welcome.command(name="bye", description="Set the leave message template")
    @app_commands.describe(text="Goodbye text to send when a member leaves")
    @commands.has_permissions(manage_guild=True)
    async def bye(self, ctx, *, text: str):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (ctx.guild.id,))
            await c.execute(
                "UPDATE guild_config SET goodbye_msg=? WHERE guild_id=?",
                (text, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok("Goodbye message updated."))

    @welcome.command(name="status", description="Show the current welcome configuration")
    @commands.has_permissions(manage_guild=True)
    async def welcome_status(self, ctx):
        channel_id, welcome_msg, goodbye_msg = await self._config(ctx.guild.id)
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed = info("Welcome configuration")
        embed.add_field(name="Channel", value=channel.mention if channel else "Not configured", inline=False)
        embed.add_field(name="Welcome", value=welcome_msg or "Not configured", inline=False)
        embed.add_field(name="Goodbye", value=goodbye_msg or "Not configured", inline=False)
        await ctx.send(embed=embed)

    @welcome.command(name="preview", description="Preview the current welcome or goodbye template")
    @app_commands.describe(
        kind="Choose whether to preview the welcome or goodbye message",
        member="Optional member to render the placeholders against",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_preview(
        self,
        ctx,
        kind: Literal["welcome", "goodbye"],
        member: discord.Member | None = None,
    ):
        channel_id, welcome_msg, goodbye_msg = await self._config(ctx.guild.id)
        template = welcome_msg if kind == "welcome" else goodbye_msg
        if not template:
            return await ctx.send(embed=err(f"No {kind} message has been configured yet."))
        sample_member = member or ctx.author
        preview = render(template, sample_member)
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed = info(f"{kind.title()} preview", preview)
        embed.add_field(name="Channel", value=channel.mention if channel else "Not configured", inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT welcome_channel, welcome_msg FROM guild_config WHERE guild_id=?",
                (member.guild.id,),
            )
            row = await cur.fetchone()
        if row and row[0] and row[1]:
            channel = self.bot.get_channel(row[0])
            if channel:
                try:
                    await channel.send(render(row[1], member))
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT welcome_channel, goodbye_msg FROM guild_config WHERE guild_id=?",
                (member.guild.id,),
            )
            row = await cur.fetchone()
        if row and row[0] and row[1]:
            channel = self.bot.get_channel(row[0])
            if channel:
                try:
                    await channel.send(render(row[1], member))
                except discord.Forbidden:
                    pass


async def setup(bot):
    await bot.add_cog(Welcome(bot))
