import re

import discord
from discord.ext import commands

URL_RE = re.compile(r"https?://\S+")
EMOJI_RE = re.compile(r"<a?:\w+:\d+>|[\U0001F300-\U0001FAFF]")


class PurgeExt(commands.Cog):
    """Purge variants + cleanup."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def purgex(self, ctx, amount: int = 10):
        """Subcommands: bot, contains, embeds, files, links, mentions, human, emoji, reactions"""
        await ctx.send(
            "Subcommands: `bot`, `contains <text>`, `embeds`, `files`, `links`, "
            "`mentions`, `human`, `emoji`, `reactions`"
        )

    async def _purge(self, ctx, amount, check):
        deleted = await ctx.channel.purge(limit=amount + 1, check=check)
        await ctx.send(f"Purged {len(deleted) - 1}.", delete_after=5)

    @purgex.command(name="bot")
    @commands.has_permissions(manage_messages=True)
    async def purge_bot(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: m.author.bot)

    @purgex.command(name="contains")
    @commands.has_permissions(manage_messages=True)
    async def purge_contains(self, ctx, amount: int, *, text: str):
        await self._purge(ctx, amount, lambda m: text.lower() in (m.content or "").lower())

    @purgex.command(name="embeds")
    @commands.has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: bool(m.embeds))

    @purgex.command(name="files")
    @commands.has_permissions(manage_messages=True)
    async def purge_files(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: bool(m.attachments))

    @purgex.command(name="links")
    @commands.has_permissions(manage_messages=True)
    async def purge_links(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: bool(URL_RE.search(m.content or "")))

    @purgex.command(name="mentions")
    @commands.has_permissions(manage_messages=True)
    async def purge_mentions(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: bool(m.mentions or m.role_mentions))

    @purgex.command(name="human")
    @commands.has_permissions(manage_messages=True)
    async def purge_human(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: not m.author.bot)

    @purgex.command(name="emoji")
    @commands.has_permissions(manage_messages=True)
    async def purge_emoji(self, ctx, amount: int = 50):
        await self._purge(ctx, amount, lambda m: bool(EMOJI_RE.search(m.content or "")))

    @purgex.command(name="reactions")
    @commands.has_permissions(manage_messages=True)
    async def purge_reactions(self, ctx, amount: int = 50):
        async for m in ctx.channel.history(limit=amount):
            if m.reactions:
                try:
                    await m.clear_reactions()
                except discord.Forbidden:
                    pass
        await ctx.send("Cleared reactions.", delete_after=5)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def cleanup(self, ctx, amount: int = 25):
        """Delete bot's own recent messages."""
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author == self.bot.user)
        await ctx.send(f"Cleaned {len(deleted)}.", delete_after=5)


async def setup(bot):
    await bot.add_cog(PurgeExt(bot))
