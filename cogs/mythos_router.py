from __future__ import annotations

import asyncio
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from loki_npc.memory import redact_discord_content
from utils import mythos_router


class MythosRouter(commands.Cog):
    """Owner-only Discord router for the local Mythos packet compiler."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(
        name="mythos",
        description="Owner-only Mythos packet compiler router",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def mythos(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_snapshot(ctx, run="")

    @mythos.command(name="status", description="Show Mythos run and packet status")
    @app_commands.describe(run="Optional safe run slug under .mythos")
    @commands.is_owner()
    async def status(self, ctx: commands.Context, run: str = ""):
        await self._send_snapshot(ctx, run=run)

    @mythos.command(name="ready", description="Run mythos-skill ready")
    @commands.is_owner()
    async def ready(self, ctx: commands.Context):
        await self._run_action(ctx, "ready")

    @mythos.command(name="add", description="Add an HTTPS GitHub source to a Mythos run")
    @app_commands.describe(
        url="HTTPS GitHub repository URL to add as Mythos source material",
        run="Optional safe run slug under .mythos",
        note="Optional short note about why this source is being added",
    )
    @commands.is_owner()
    async def add(self, ctx: commands.Context, url: str, run: str = "", note: str = ""):
        try:
            record = mythos_router.add_mythos_source(
                url,
                run_slug=run or None,
                note=note,
                added_by=str(getattr(ctx.author, "id", "discord-owner")),
            )
        except mythos_router.MythosRouterError as exc:
            await self._send(ctx, str(exc))
            return

        embed = discord.Embed(title="Mythos source added", color=0x2ECC71)
        embed.add_field(name="Source", value=self._mono(record["url"], 900), inline=False)
        embed.add_field(name="Repo", value=f"`{record['owner']}/{record['repo']}`", inline=True)
        embed.add_field(name="Run", value=f"`{mythos_router.mythos_run_dir(run or None).name}`", inline=True)
        if record.get("note"):
            embed.add_field(name="Note", value=self._mono(record["note"], 900), inline=False)
        await self._send(ctx, embed=embed)

    @mythos.command(name="init", description="Initialize a Mythos run directory")
    @app_commands.describe(run="Optional safe run slug under .mythos")
    @commands.is_owner()
    async def init(self, ctx: commands.Context, run: str = ""):
        await self._run_action(ctx, "init", run=run)

    @mythos.command(name="compile", description="Compile a Mythos run packet")
    @app_commands.describe(run="Optional safe run slug under .mythos")
    @commands.is_owner()
    async def compile(self, ctx: commands.Context, run: str = ""):
        await self._run_action(ctx, "compile", run=run)

    @mythos.command(name="gate", description="Run the strict Mythos gate")
    @app_commands.describe(run="Optional safe run slug under .mythos")
    @commands.is_owner()
    async def gate(self, ctx: commands.Context, run: str = ""):
        await self._run_action(ctx, "gate", run=run)

    async def _send_snapshot(self, ctx: commands.Context, *, run: str):
        try:
            snapshot = mythos_router.mythos_snapshot(run or None)
        except mythos_router.MythosRouterError as exc:
            await self._send(ctx, str(exc))
            return

        summary = snapshot.get("packet_summary") or {}
        embed = discord.Embed(title="Mythos Router", color=0xF6C244)
        embed.add_field(name="Run", value=f"`{snapshot['run_slug']}`", inline=True)
        embed.add_field(name="Exists", value=str(snapshot["exists"]), inline=True)
        embed.add_field(name="Packet", value=str(snapshot["packet_exists"]), inline=True)
        embed.add_field(name="Sources", value=str(snapshot["source_count"]), inline=True)
        embed.add_field(name="Files", value=str(snapshot["file_count"]), inline=True)
        embed.add_field(name="Run dir", value=self._mono(snapshot["run_dir"], 900), inline=False)
        if summary:
            embed.add_field(name="Packet summary", value=self._mono(self._summary_text(summary), 900), inline=False)
        if snapshot.get("sources"):
            sources = "\n".join(source.get("url", "") for source in snapshot["sources"][:5])
            embed.add_field(name="Sources", value=self._mono(sources, 900), inline=False)
        if snapshot.get("packet_error"):
            embed.add_field(name="Packet error", value=self._mono(snapshot["packet_error"], 900), inline=False)
        if snapshot.get("source_error"):
            embed.add_field(name="Source error", value=self._mono(snapshot["source_error"], 900), inline=False)
        await self._send(ctx, embed=embed)

    async def _run_action(self, ctx: commands.Context, action: str, *, run: str = ""):
        await self._defer(ctx)
        try:
            result = await asyncio.to_thread(mythos_router.run_mythos_action, action, run_slug=run or None)
        except mythos_router.MythosRouterError as exc:
            await self._send(ctx, str(exc))
            return

        color = 0x2ECC71 if result.ok else 0xE74C3C
        title = f"Mythos {result.action}: {'passed' if result.ok else 'failed'}"
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Exit", value=str(result.returncode), inline=True)
        if result.run_dir is not None:
            embed.add_field(name="Run", value=f"`{result.run_dir.name}`", inline=True)
        embed.add_field(name="Command", value=self._mono(" ".join(result.command), 900), inline=False)
        embed.add_field(name="Output", value=self._mono(redact_discord_content(result.output), 1_000), inline=False)
        await self._send(ctx, embed=embed)

    async def _defer(self, ctx: commands.Context) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)

    async def _send(self, ctx: commands.Context, *args: Any, **kwargs: Any) -> None:
        if ctx.interaction:
            kwargs["ephemeral"] = True
        await ctx.send(*args, **kwargs)

    @staticmethod
    def _summary_text(summary: dict[str, Any]) -> str:
        lines = []
        for key in ("pass_id", "evidence_count", "verifier_count", "blocker_count"):
            if summary.get(key) is not None:
                lines.append(f"{key}: {summary[key]}")
        keys = summary.get("keys") or []
        if keys:
            lines.append("keys: " + ", ".join(str(key) for key in keys))
        return "\n".join(lines) or "Packet loaded."

    @staticmethod
    def _mono(value: str, max_chars: int) -> str:
        text = value.strip() or "None"
        if len(text) > max_chars:
            text = f"{text[: max_chars - 3]}..."
        return f"```text\n{text}\n```"


async def setup(bot):
    await bot.add_cog(MythosRouter(bot))
