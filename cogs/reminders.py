import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import fmt_duration, now, parse_duration, safe_send


class Reminders(commands.Cog):
    """Personal reminders."""

    def __init__(self, bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @commands.hybrid_command(aliases=["remind", "remindme"])
    async def reminder(self, ctx, duration: str, *, message: str):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration.")
        due = now() + secs
        async with db.get() as c:
            await c.execute(
                "INSERT INTO reminders(user_id,channel_id,guild_id,due,message) VALUES(?,?,?,?,?)",
                (ctx.author.id, ctx.channel.id, ctx.guild.id if ctx.guild else 0, due, message),
            )
            await c.commit()
        await ctx.send(f"Reminder set in {fmt_duration(secs)}.")

    @commands.command(aliases=["mine"])
    async def reminders(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, due, message FROM reminders WHERE user_id=? ORDER BY due", (ctx.author.id,)
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("None.")
        e = discord.Embed(title="Your reminders", color=0x5865F2)
        for rid, due, msg in rows[:20]:
            e.add_field(name=f"#{rid} <t:{due}:R>", value=msg[:200], inline=False)
        await ctx.send(embed=e)

    @commands.command(aliases=["cancelreminder", "delreminder"])
    async def cancelremind(self, ctx, rid: int):
        async with db.get() as c:
            cur = await c.execute("SELECT user_id FROM reminders WHERE id=?", (rid,))
            row = await cur.fetchone()
            if not row or row[0] != ctx.author.id:
                return await ctx.send("Not yours / not found.")
            await c.execute("DELETE FROM reminders WHERE id=?", (rid,))
            await c.commit()
        await ctx.send("Cancelled.")

    @commands.command()
    async def clearreminders(self, ctx):
        async with db.get() as c:
            await c.execute("DELETE FROM reminders WHERE user_id=?", (ctx.author.id,))
            await c.commit()
        await ctx.send("Cleared.")

    @tasks.loop(seconds=15)
    async def loop(self):
        async with db.get() as c:
            cur = await c.execute("SELECT id,user_id,channel_id,message FROM reminders WHERE due<=?", (now(),))
            rows = await cur.fetchall()
            for rid, uid, chid, msg in rows:
                ch = self.bot.get_channel(chid)
                try:
                    if ch:
                        await safe_send(
                            ch, content=f"<@{uid}> reminder: {msg}", dedupe_key=f"reminder:{rid}", dedupe_window=30
                        )
                    else:
                        user = self.bot.get_user(uid)
                        if user:
                            await safe_send(
                                user, content=f"Reminder: {msg}", dedupe_key=f"reminder-dm:{rid}", dedupe_window=30
                            )
                except Exception:
                    pass
                await c.execute("DELETE FROM reminders WHERE id=?", (rid,))
            await c.commit()

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))
