from datetime import timedelta

import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import fmt_duration, now, parse_duration


class Moderation(commands.Cog):
    """Kick, ban, mute, warn, purge."""

    def __init__(self, bot):
        self.bot = bot
        self.unmute_loop.start()

    def cog_unload(self):
        self.unmute_loop.cancel()

    @commands.hybrid_command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason"):
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.send(f"Kicked {member}. Reason: {reason}")

    @commands.hybrid_command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason"):
        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=0)
        await ctx.send(f"Banned {member}. Reason: {reason}")

    @commands.hybrid_command()
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member, *, reason="Softban"):
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.guild.unban(member)
        await ctx.send(f"Softbanned {member}")

    @commands.hybrid_command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="Unban"):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"Unbanned {user}")

    @commands.hybrid_command()
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str = "1h", *, reason="No reason"):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration. Try `1h30m`.")
        until = discord.utils.utcnow() + timedelta(seconds=secs)
        try:
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            return await ctx.send("Missing perms.")
        await ctx.send(f"Muted {member} for {fmt_duration(secs)}")

    @commands.hybrid_command()
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"Unmuted {member}")

    @commands.hybrid_command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason"):
        async with db.get() as c:
            await c.execute(
                "INSERT INTO warnings(guild_id,user_id,mod_id,reason,created_at) VALUES(?,?,?,?,?)",
                (ctx.guild.id, member.id, ctx.author.id, reason, now()),
            )
            await c.commit()
            cur = await c.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            )
            count = (await cur.fetchone())[0]
        await ctx.send(f"Warned {member}. Total warnings: {count}")
        try:
            await member.send(f"You were warned in {ctx.guild.name}: {reason}")
        except discord.Forbidden:
            pass

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, reason, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC",
                (ctx.guild.id, member.id),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(f"No warnings for {member}.")
        e = discord.Embed(title=f"Warnings for {member}", color=0xED4245)
        for wid, reason, ts in rows[:25]:
            e.add_field(name=f"#{wid} — <t:{ts}:R>", value=reason, inline=False)
        await ctx.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def delwarn(self, ctx, warn_id: int):
        async with db.get() as c:
            await c.execute("DELETE FROM warnings WHERE id=? AND guild_id=?", (warn_id, ctx.guild.id))
            await c.commit()
        await ctx.send(f"Deleted warning #{warn_id}")

    @commands.hybrid_command(aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = 10, member: discord.Member = None):
        def check(m):
            return member is None or m.author == member

        deleted = await ctx.channel.purge(limit=amount + 1, check=check)
        await ctx.send(f"Purged {len(deleted) - 1} messages.", delete_after=5)

    @commands.hybrid_command()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int = 0):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"Slowmode = {seconds}s")

    @commands.hybrid_command()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Locked.")

    @commands.hybrid_command()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Unlocked.")

    @tasks.loop(seconds=30)
    async def unmute_loop(self):
        await self.bot.wait_until_ready()

    @unmute_loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Moderation(bot))
