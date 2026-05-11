import unicodedata

import discord
from discord.ext import commands


class Misc(commands.Cog):
    """Charinfo, botpermissions, invite."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def charinfo(self, ctx, *, chars: str):
        out = []
        for c in chars[:25]:
            try:
                name = unicodedata.name(c)
            except ValueError:
                name = "?"
            out.append(f"`U+{ord(c):04X}` {c} — {name}")
        await ctx.send("\n".join(out))

    @commands.command(aliases=["botperms"])
    async def botpermissions(self, ctx):
        perms = ctx.guild.me.guild_permissions
        granted = [p for p, v in perms if v]
        missing = [p for p, v in perms if not v]
        e = discord.Embed(title="Bot permissions", color=0x5865F2)
        e.add_field(name="Granted", value=", ".join(granted)[:1024] or "none", inline=False)
        e.add_field(name="Missing", value=", ".join(missing)[:1024] or "none", inline=False)
        await ctx.send(embed=e)

    @commands.command()
    async def invite(self, ctx):
        url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(administrator=True),
            scopes=["bot", "applications.commands"],
        )
        await ctx.send(f"Invite: {url}")

    @commands.command()
    async def vote(self, ctx):
        await ctx.send("Self-hosted; no vote site.")


async def setup(bot):
    await bot.add_cog(Misc(bot))
