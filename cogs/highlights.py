import re

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok
from utils.link_previews import extract_music_artists, extract_urls, resolve_link_previews


async def music_artists_for_message_content(content: str | None) -> str:
    urls = extract_urls(content)
    if not urls:
        return ""

    artists: list[str] = []
    for preview in await resolve_link_previews(urls):
        artist = extract_music_artists(preview)
        if artist and artist.casefold() not in {existing.casefold() for existing in artists}:
            artists.append(artist)
        if len(artists) >= 5:
            break
    return "\n".join(artists)


class Highlights(commands.Cog):
    """DM user when a keyword they subscribed to is mentioned."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage highlight keywords for notification DMs",
    )
    async def highlight(self, ctx):
        await ctx.send(
            embed=info(
                "Highlights",
                "Use `/highlight add`, `/highlight remove`, `/highlight list`, and `/highlight clear`.",
            )
        )

    @highlight.command(name="add", description="Add a highlight keyword")
    @app_commands.describe(word="Keyword or phrase that should trigger a DM")
    async def add(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        if not cleaned:
            return await ctx.send(embed=err("Provide a keyword or phrase to track."))
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO highlights(guild_id,user_id,word) VALUES(?,?,?)",
                (ctx.guild.id, ctx.author.id, cleaned),
            )
            await c.commit()
        if getattr(ctx, "message", None):
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
        try:
            await ctx.author.send(f"Added highlight `{cleaned}` in {ctx.guild.name}.")
            await ctx.send(embed=ok("Highlight saved. Check your DMs for confirmation."), delete_after=5)
        except discord.Forbidden:
            await ctx.send(embed=ok("Highlight saved, but I could not DM you."), delete_after=5)

    @highlight.command(name="remove", description="Remove a highlight keyword")
    @app_commands.describe(word="Saved highlight keyword to remove")
    async def remove(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM highlights WHERE guild_id=? AND user_id=? AND word=?",
                (ctx.guild.id, ctx.author.id, cleaned),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed highlight `{cleaned}`."), delete_after=5)
        else:
            await ctx.send(embed=err(f"`{cleaned}` was not on your highlight list."), delete_after=5)

    @highlight.command(name="list", description="List your saved highlight keywords")
    async def hl_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT word FROM highlights WHERE guild_id=? AND user_id=? ORDER BY word",
                (ctx.guild.id, ctx.author.id),
            )
            rows = await cur.fetchall()
        words = ", ".join(row[0] for row in rows) or "None"
        try:
            await ctx.author.send(f"Highlights in {ctx.guild.name}: {words}")
            await ctx.send(embed=ok("Sent your highlight list in DMs."), delete_after=5)
        except discord.Forbidden:
            await ctx.send(embed=info("Highlights", words))

    @highlight.command(name="clear", description="Clear all of your highlight keywords in this server")
    async def hl_clear(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM highlights WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, ctx.author.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Cleared {cur.rowcount} highlight keyword(s)."), delete_after=5)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or not message.content:
            return
        content = message.content.lower()
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, word FROM highlights WHERE guild_id=?",
                (message.guild.id,),
            )
            rows = await cur.fetchall()
        seen = set()
        artist_text: str | None = None
        for user_id, word in rows:
            if user_id == message.author.id or user_id in seen:
                continue
            if not re.search(r"\b" + re.escape(word) + r"\b", content):
                continue
            member = message.guild.get_member(user_id)
            if not member or not message.channel.permissions_for(member).view_channel:
                continue
            seen.add(user_id)
            embed = discord.Embed(
                title=f"Highlight: {word}",
                description=f"{message.content}\n\n[Jump to message]({message.jump_url})",
                color=0xFEE75C,
            )
            embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            embed.add_field(name="Channel", value=message.channel.mention)
            if artist_text is None:
                artist_text = await music_artists_for_message_content(message.content)
            if artist_text:
                embed.add_field(name="Artists", value=artist_text[:1024], inline=False)
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(Highlights(bot))
