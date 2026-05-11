import random

import discord
from discord.ext import commands

from utils import db
from utils.helpers import level_from_xp, now, xp_for_level


class Levels(commands.Cog):
    """XP and leveling."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or len(message.content) < 2:
            return
        t = now()
        async with db.get() as c:
            cur = await c.execute(
                "SELECT xp, level, last_msg FROM levels WHERE guild_id=? AND user_id=?",
                (message.guild.id, message.author.id),
            )
            row = await cur.fetchone()
            xp, level, last_msg = row if row else (0, 0, 0)
            if t - last_msg < 60:
                return
            gained = random.randint(15, 25)
            xp += gained
            new_level = level_from_xp(xp)
            await c.execute(
                "INSERT OR REPLACE INTO levels(guild_id,user_id,xp,level,last_msg) VALUES(?,?,?,?,?)",
                (message.guild.id, message.author.id, xp, new_level, t),
            )
            await c.commit()
        if new_level > level:
            try:
                await message.channel.send(f"🎉 {message.author.mention} reached level **{new_level}**!")
            except discord.Forbidden:
                pass

    @commands.hybrid_command(aliases=["lvl"])
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        async with db.get() as c:
            cur = await c.execute(
                "SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(f"{member.display_name} has no XP yet.")
        xp, level = row
        needed = xp_for_level(level)
        consumed = sum(xp_for_level(i) for i in range(level))
        progress = xp - consumed
        e = discord.Embed(title=f"{member.display_name}", color=0x5865F2)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Level", value=level)
        e.add_field(name="XP", value=f"{progress}/{needed}")
        e.add_field(name="Total XP", value=xp)
        await ctx.send(embed=e)

    @commands.hybrid_command(aliases=["lb"])
    async def leaderboard(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("Empty.")
        lines = []
        for i, (uid, xp, lvl) in enumerate(rows, 1):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else str(uid)
            lines.append(f"**{i}.** {name} — lvl {lvl} ({xp} XP)")
        e = discord.Embed(title="XP Leaderboard", color=0x5865F2, description="\n".join(lines))
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Levels(bot))
