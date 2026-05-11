import discord
from discord.ext import commands

from utils import db
from utils.helpers import fmt_duration, now


class VoiceTracker(commands.Cog):
    """Track time spent in voice channels."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        t = now()
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO voice_activity(guild_id,user_id) VALUES(?,?)",
                (member.guild.id, member.id),
            )
            if before.channel is None and after.channel is not None:
                await c.execute(
                    "UPDATE voice_activity SET joined_at=? WHERE guild_id=? AND user_id=?",
                    (t, member.guild.id, member.id),
                )
            elif before.channel is not None and after.channel is None:
                cur = await c.execute(
                    "SELECT joined_at, seconds FROM voice_activity WHERE guild_id=? AND user_id=?",
                    (member.guild.id, member.id),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    delta = t - row[0]
                    await c.execute(
                        "UPDATE voice_activity SET seconds=?, joined_at=0 WHERE guild_id=? AND user_id=?",
                        (row[1] + delta, member.guild.id, member.id),
                    )
            await c.commit()

    @commands.command()
    async def voicetime(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        async with db.get() as c:
            cur = await c.execute(
                "SELECT seconds, joined_at FROM voice_activity WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            )
            row = await cur.fetchone()
        total = row[0] if row else 0
        if row and row[1]:
            total += now() - row[1]
        await ctx.send(f"{member.display_name} voice time: {fmt_duration(total)}")

    @commands.command()
    async def voicelb(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, seconds FROM voice_activity WHERE guild_id=? ORDER BY seconds DESC LIMIT 10",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("Empty.")
        lines = []
        for i, (uid, s) in enumerate(rows, 1):
            m = ctx.guild.get_member(uid)
            name = m.display_name if m else str(uid)
            lines.append(f"**{i}.** {name} — {fmt_duration(s)}")
        e = discord.Embed(title="Voice Leaderboard", color=0x5865F2, description="\n".join(lines))
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(VoiceTracker(bot))
