import discord
from discord.ext import commands

NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class Polls(commands.Cog):
    """Simple and ranked-choice polls."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def poll(self, ctx, question: str, *options):
        if len(options) < 2 or len(options) > 10:
            return await ctx.send("Need 2-10 options.")
        e = discord.Embed(title=question, color=0x5865F2)
        e.description = "\n".join(f"{NUMS[i]} {o}" for i, o in enumerate(options))
        e.set_footer(text=f"Poll by {ctx.author}")
        msg = await ctx.send(embed=e)
        for i in range(len(options)):
            await msg.add_reaction(NUMS[i])

    @commands.command()
    async def yesno(self, ctx, *, question: str):
        e = discord.Embed(title=question, color=0x5865F2)
        e.set_footer(text=f"Poll by {ctx.author}")
        msg = await ctx.send(embed=e)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

    @commands.command()
    async def rankedpoll(self, ctx, question: str, *options):
        """Ranked-choice — users react in preference order."""
        if len(options) < 2 or len(options) > 10:
            return await ctx.send("Need 2-10 options.")
        e = discord.Embed(title=f"[Ranked] {question}", color=0xEB459E)
        e.description = "\n".join(f"{NUMS[i]} {o}" for i, o in enumerate(options))
        e.set_footer(text="React in preference order. Close with !tally <message_id>")
        msg = await ctx.send(embed=e)
        for i in range(len(options)):
            await msg.add_reaction(NUMS[i])

    @commands.command()
    async def tally(self, ctx, message_id: int):
        try:
            msg = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send("Not found.")
        counts = {}
        for r in msg.reactions:
            if str(r.emoji) in NUMS:
                counts[str(r.emoji)] = r.count - 1
        if not counts:
            return await ctx.send("No votes.")
        winner = max(counts, key=counts.get)
        lines = [f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        await ctx.send("Tally:\n" + "\n".join(lines) + f"\n\n**Winner: {winner}**")


async def setup(bot):
    await bot.add_cog(Polls(bot))
