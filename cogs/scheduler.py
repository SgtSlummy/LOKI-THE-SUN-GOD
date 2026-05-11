import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import now, parse_duration, safe_send


class Scheduler(commands.Cog):
    """Schedule messages to send later."""

    def __init__(self, bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def schedule(self, ctx, channel: discord.TextChannel, duration: str, *, content: str):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration.")
        due = now() + secs
        async with db.get() as c:
            await c.execute(
                "INSERT INTO scheduled_messages(channel_id,guild_id,content,due,author_id) VALUES(?,?,?,?,?)",
                (channel.id, ctx.guild.id, content, due, ctx.author.id),
            )
            await c.commit()
        await ctx.send(f"Will post in {channel.mention} <t:{due}:R>.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def scheduled(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, channel_id, due, content FROM scheduled_messages WHERE guild_id=? ORDER BY due",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("None.")
        e = discord.Embed(title="Scheduled", color=0x5865F2)
        for sid, chid, due, content in rows[:20]:
            ch = self.bot.get_channel(chid)
            e.add_field(name=f"#{sid} in {ch.mention if ch else chid} <t:{due}:R>", value=content[:200], inline=False)
        await ctx.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def unschedule(self, ctx, sid: int):
        async with db.get() as c:
            await c.execute("DELETE FROM scheduled_messages WHERE id=? AND guild_id=?", (sid, ctx.guild.id))
            await c.commit()
        await ctx.send("Removed.")

    @tasks.loop(seconds=30)
    async def loop(self):
        async with db.get() as c:
            cur = await c.execute("SELECT id,channel_id,content FROM scheduled_messages WHERE due<=?", (now(),))
            rows = await cur.fetchall()
            for sid, chid, content in rows:
                ch = self.bot.get_channel(chid)
                if ch:
                    try:
                        await safe_send(ch, content=content, dedupe_key=f"scheduled:{sid}", dedupe_window=60)
                    except discord.Forbidden:
                        pass
                await c.execute("DELETE FROM scheduled_messages WHERE id=?", (sid,))
            await c.commit()

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Scheduler(bot))
