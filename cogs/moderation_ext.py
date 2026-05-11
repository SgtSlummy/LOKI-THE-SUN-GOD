import asyncio
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import fmt_duration, now, parse_duration


class ModerationExt(commands.Cog):
    """Extra moderation: tempban, massban, hardmute, setnick, lockdown server, report."""

    def __init__(self, bot):
        self.bot = bot
        self.tempban_loop.start()

    def cog_unload(self):
        self.tempban_loop.cancel()

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason"):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration.")
        until = now() + secs
        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=0)
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO tempbans(guild_id,user_id,until) VALUES(?,?,?)",
                (ctx.guild.id, member.id, until),
            )
            await c.commit()
        await ctx.send(f"Tempbanned {member} for {fmt_duration(secs)}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def massban(self, ctx, *user_ids: int):
        if not user_ids:
            return await ctx.send("Provide IDs.")
        n = 0
        for uid in user_ids:
            try:
                user = discord.Object(id=uid)
                await ctx.guild.ban(user, reason=f"massban by {ctx.author}", delete_message_days=1)
                n += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.3)
        await ctx.send(f"Banned {n}/{len(user_ids)}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def hardmute(self, ctx, member: discord.Member, duration: str = "1h", *, reason: str = "No reason"):
        """Timeout + remove non-essential roles."""
        secs = parse_duration(duration) or 3600
        until = discord.utils.utcnow() + timedelta(seconds=secs)
        try:
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            return await ctx.send("Missing perms.")
        await ctx.send(f"Hardmuted {member} for {fmt_duration(secs)}")

    @commands.hybrid_command()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str = "10m", *, reason: str = "No reason"):
        secs = parse_duration(duration) or 600
        until = discord.utils.utcnow() + timedelta(seconds=secs)
        await member.timeout(until, reason=f"{ctx.author}: {reason}")
        await ctx.send(f"Timeout: {member} for {fmt_duration(secs)}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def removetimeout(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"Removed timeout on {member}")

    @commands.command()
    @commands.has_permissions(manage_nicknames=True)
    async def setnick(self, ctx, member: discord.Member, *, nick: str = ""):
        try:
            await member.edit(nick=nick or None, reason=f"by {ctx.author}")
            await ctx.send(f"Nick set: {member}")
        except discord.Forbidden:
            await ctx.send("No perms.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx):
        """Server-wide lockdown."""
        n = 0
        for ch in ctx.guild.text_channels:
            try:
                ow = ch.overwrites_for(ctx.guild.default_role)
                ow.send_messages = False
                await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"lockdown by {ctx.author}")
                n += 1
            except discord.Forbidden:
                pass
        await ctx.send(f"🔒 Locked {n} channels.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def unlockdown(self, ctx):
        n = 0
        for ch in ctx.guild.text_channels:
            try:
                ow = ch.overwrites_for(ctx.guild.default_role)
                ow.send_messages = None
                await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"unlockdown by {ctx.author}")
                n += 1
            except discord.Forbidden:
                pass
        await ctx.send(f"🔓 Unlocked {n} channels.")

    @commands.command()
    async def report(self, ctx, member: discord.Member, *, reason: str):
        async with db.get() as c:
            cur = await c.execute("SELECT log_channel FROM guild_config WHERE guild_id=?", (ctx.guild.id,))
            row = await cur.fetchone()
        if not row or not row[0]:
            return await ctx.send("No log channel configured.")
        ch = self.bot.get_channel(row[0])
        if ch:
            e = discord.Embed(title="User Report", color=0xED4245)
            e.add_field(name="Reporter", value=str(ctx.author))
            e.add_field(name="Reported", value=str(member))
            e.add_field(name="Channel", value=ctx.channel.mention)
            e.add_field(name="Reason", value=reason, inline=False)
            await ch.send(embed=e)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send("Report sent.", delete_after=5)

    @tasks.loop(seconds=60)
    async def tempban_loop(self):
        async with db.get() as c:
            cur = await c.execute("SELECT guild_id, user_id FROM tempbans WHERE until<=?", (now(),))
            rows = await cur.fetchall()
            for gid, uid in rows:
                guild = self.bot.get_guild(gid)
                if guild:
                    try:
                        await guild.unban(discord.Object(id=uid), reason="Tempban expired")
                    except discord.NotFound:
                        pass
                await c.execute("DELETE FROM tempbans WHERE guild_id=? AND user_id=?", (gid, uid))
            await c.commit()

    @tempban_loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ModerationExt(bot))
