import json

import discord
from discord.ext import commands


class EmbedBuilder(commands.Cog):
    """Interactive embed builder via JSON."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def embed(self, ctx, channel: discord.TextChannel = None, *, payload: str = None):
        """
        Usage: !embed [#channel] {"title":"x","description":"y","color":3447003}
        Fields supported: title, description, color, url, image, thumbnail, footer, fields[{name,value,inline}]
        """
        channel = channel or ctx.channel
        if not payload:
            return await ctx.send(
                'Provide JSON. Example: `!embed {"title":"Hi","description":"Hello","color":3447003}`'
            )
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return await ctx.send(f"Bad JSON: {e}")
        e = discord.Embed(
            title=data.get("title", ""),
            description=data.get("description", ""),
            url=data.get("url"),
            color=data.get("color", 0x5865F2),
        )
        if data.get("image"):
            e.set_image(url=data["image"])
        if data.get("thumbnail"):
            e.set_thumbnail(url=data["thumbnail"])
        if data.get("footer"):
            e.set_footer(text=data["footer"])
        for f in data.get("fields", []):
            e.add_field(name=f.get("name", "—"), value=f.get("value", "—"), inline=f.get("inline", False))
        await channel.send(embed=e)
        if channel != ctx.channel:
            await ctx.send(f"Sent to {channel.mention}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def announce(self, ctx, channel: discord.TextChannel, *, text: str):
        e = discord.Embed(title="📢 Announcement", description=text, color=0xEB459E)
        e.set_footer(text=f"By {ctx.author}")
        await channel.send(embed=e)
        await ctx.message.add_reaction("✅")


async def setup(bot):
    await bot.add_cog(EmbedBuilder(bot))
