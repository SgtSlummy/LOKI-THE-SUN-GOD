from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.llm_client import LLMConfigError, LLMProviderError, ask_loki_llm, discord_safe_chunks


class AI(commands.Cog):
    """Admin-gated LLM commands for LOKI THE SUN GOD."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ask", description="Ask LOKI THE SUN GOD's configured LLM")
    @app_commands.describe(prompt="Question or task for LOKI THE SUN GOD's configured OpenAI-compatible model")
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def ask(self, ctx: commands.Context, *, prompt: str):
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        try:
            answer = await ask_loki_llm(prompt)
        except LLMConfigError as exc:
            await self._send(ctx, str(exc))
            return
        except LLMProviderError as exc:
            await self._send(ctx, f"LLM request failed: {exc}")
            return

        embed = discord.Embed(title="LOKI THE SUN GOD LLM", color=0xF6C244)
        chunks = discord_safe_chunks(answer)
        embed.description = chunks[0]
        await self._send(ctx, embed=embed)
        for chunk in chunks[1:]:
            await self._send(ctx, chunk)

    async def _send(self, ctx: commands.Context, *args, **kwargs):
        if ctx.interaction:
            kwargs["ephemeral"] = True
        await ctx.send(*args, **kwargs)


async def setup(bot):
    await bot.add_cog(AI(bot))
