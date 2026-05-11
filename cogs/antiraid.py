import time
from collections import deque

import discord
from discord.ext import commands


class AntiRaid(commands.Cog):
    """Heuristic anti-raid: spike in joins → lockdown."""

    def __init__(self, bot):
        self.bot = bot
        self.joins = {}
        self.locked = set()
        self.threshold = 8
        self.window = 10

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        g = member.guild.id
        q = self.joins.setdefault(g, deque())
        now = time.time()
        q.append(now)
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.threshold and g not in self.locked:
            self.locked.add(g)
            await self._lockdown(member.guild)

    async def _lockdown(self, guild):
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Raid detected")
            except discord.Forbidden:
                continue
        owner = guild.owner
        if owner:
            try:
                await owner.send(
                    f"⚠️ Possible raid detected on {guild.name}. Server locked down. Use `!raidoff` to restore."
                )
            except discord.Forbidden:
                pass

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def raidoff(self, ctx):
        self.locked.discard(ctx.guild.id)
        for channel in ctx.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = None
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason="Raid cleared")
            except discord.Forbidden:
                continue
        await ctx.send("Raid mode off.")


async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
