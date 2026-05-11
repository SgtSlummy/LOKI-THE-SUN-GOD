import random

import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import now, parse_duration

PARTY = "🎉"


class Giveaways(commands.Cog):
    """Reaction-based giveaways."""

    def __init__(self, bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @commands.command(aliases=["gstart"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx, duration: str, winners: int, *, prize: str):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration.")
        ends = now() + secs
        e = discord.Embed(title=f"{PARTY} GIVEAWAY {PARTY}", description=f"**{prize}**", color=0xFEE75C)
        e.add_field(name="Winners", value=winners)
        e.add_field(name="Ends", value=f"<t:{ends}:R>")
        e.set_footer(text=f"React with {PARTY} to enter")
        msg = await ctx.send(embed=e)
        await msg.add_reaction(PARTY)
        async with db.get() as c:
            await c.execute(
                "INSERT INTO giveaways"
                "(message_id,channel_id,guild_id,prize,winners,ends,host_id) VALUES(?,?,?,?,?,?,?)",
                (msg.id, ctx.channel.id, ctx.guild.id, prize, winners, ends, ctx.author.id),
            )
            await c.commit()

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: int):
        async with db.get() as c:
            cur = await c.execute("SELECT channel_id,prize,winners FROM giveaways WHERE message_id=?", (message_id,))
            row = await cur.fetchone()
        if not row:
            return await ctx.send("Not found.")
        ch = self.bot.get_channel(row[0])
        msg = await ch.fetch_message(message_id)
        await self._pick(msg, row[1], row[2])

    async def _pick(self, msg, prize, winners):
        reaction = next((r for r in msg.reactions if str(r.emoji) == PARTY), None)
        users = []
        if reaction:
            async for u in reaction.users():
                if not u.bot:
                    users.append(u)
        if not users:
            return await msg.channel.send(f"No entries for **{prize}**.")
        picks = random.sample(users, min(winners, len(users)))
        mentions = ", ".join(u.mention for u in picks)
        await msg.channel.send(f"{PARTY} Winners of **{prize}**: {mentions}")

    @tasks.loop(seconds=30)
    async def loop(self):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT message_id,channel_id,prize,winners FROM giveaways WHERE ended=0 AND ends<=?", (now(),)
            )
            rows = await cur.fetchall()
            for mid, chid, prize, w in rows:
                ch = self.bot.get_channel(chid)
                if ch:
                    try:
                        msg = await ch.fetch_message(mid)
                        await self._pick(msg, prize, w)
                    except discord.NotFound:
                        pass
                await c.execute("UPDATE giveaways SET ended=1 WHERE message_id=?", (mid,))
            await c.commit()

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
