from __future__ import annotations

import os
from urllib.parse import urlparse

import discord
from discord.ext import commands

from utils import db as shared_db


def configured_dashboard_url() -> str:
    public_url = (
        os.getenv("DASHBOARD_PUBLIC_URL", "").strip()
        or os.getenv("LOKI_DASHBOARD_URL", "").strip()
        or os.getenv("DASHBOARD_URL", "").strip()
    )
    if public_url:
        return public_url.rstrip("/")

    redirect_uri = os.getenv("REDIRECT_URI", "").strip()
    if redirect_uri.endswith("/callback"):
        return redirect_uri[: -len("/callback")].rstrip("/")

    return "http://localhost:5000"


def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return bool(parsed.scheme in {"http", "https"} and host not in {"localhost", "127.0.0.1", "::1"})


class DashboardLink(commands.Cog):
    """Expose LOKI THE SUN GOD's dashboard link inside Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="dashboard", description="Open LOKI THE SUN GOD's dashboard")
    async def dashboard(self, ctx: commands.Context):
        url = configured_dashboard_url()
        relay = self.bot.get_cog("Relay")
        relay_status = "loaded" if relay else "not loaded"
        embed = discord.Embed(
            title="LOKI THE SUN GOD Dashboard",
            description="Use this link for the web dashboard that matches the desktop control center.",
            color=0x5865F2,
        )
        embed.add_field(name="Dashboard URL", value=url, inline=False)
        embed.add_field(name="Relay", value=relay_status, inline=True)
        embed.add_field(name="Database", value=shared_db.database_backend(), inline=True)
        if not _is_public_url(url):
            embed.add_field(
                name="Hosting",
                value="Local URL configured. Set DASHBOARD_PUBLIC_URL or hosted REDIRECT_URI for Railway.",
                inline=False,
            )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Open Dashboard", url=url))
        await ctx.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(DashboardLink(bot))
