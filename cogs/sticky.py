import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok
from utils.helpers import safe_send


class Sticky(commands.Cog):
    """Sticky messages that LOKI THE SUN GOD keeps at the bottom of a channel."""

    def __init__(self, bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage sticky channel reminders for the current channel",
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(content="Text to keep sticky in this channel")
    async def sticky(self, ctx, *, content: str | None = None):
        if content is None:
            return await ctx.send(
                embed=info(
                    "Sticky",
                    "Use `/sticky <text>` to set one, `/sticky show` to preview it, and `/sticky remove` to clear it.",
                )
            )
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO stickies(channel_id,guild_id,content,last_msg_id) VALUES(?,?,?,?)",
                (ctx.channel.id, ctx.guild.id, content, 0),
            )
            await c.commit()
        msg = await ctx.send(f"Sticky saved for {ctx.channel.mention}.\n\n{content}")
        async with db.get() as c:
            await c.execute("UPDATE stickies SET last_msg_id=? WHERE channel_id=?", (msg.id, ctx.channel.id))
            await c.commit()

    @sticky.command(name="show", description="Preview the sticky message for this channel")
    @commands.has_permissions(manage_messages=True)
    async def sticky_show(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT content FROM stickies WHERE channel_id=?",
                (ctx.channel.id,),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(embed=err("This channel does not have a sticky message yet."))
        await ctx.send(embed=info(f"Sticky preview for #{ctx.channel.name}", row[0]))

    @sticky.command(name="remove", description="Remove the sticky message from this channel")
    @commands.has_permissions(manage_messages=True)
    async def sticky_remove(self, ctx):
        async with db.get() as c:
            cur = await c.execute("DELETE FROM stickies WHERE channel_id=?", (ctx.channel.id,))
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok("Sticky removed."))
        else:
            await ctx.send(embed=err("This channel does not have a sticky message to remove."))

    @sticky.command(name="list", description="List sticky messages configured for this server")
    @commands.has_permissions(manage_messages=True)
    async def sticky_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT channel_id, content FROM stickies WHERE guild_id=?",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=info("Stickies", "No sticky messages are configured."))
        embed = discord.Embed(title="Stickies", color=0x5865F2)
        for channel_id, content in rows[:25]:
            channel = self.bot.get_channel(channel_id)
            embed.add_field(
                name=channel.name if channel else str(channel_id),
                value=content[:200],
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        lock = self._locks.setdefault(message.channel.id, asyncio.Lock())
        async with lock:
            async with db.get() as c:
                cur = await c.execute(
                    "SELECT content, last_msg_id FROM stickies WHERE channel_id=?",
                    (message.channel.id,),
                )
                row = await cur.fetchone()
            if not row:
                return

            content, last_msg_id = row
            if last_msg_id:
                try:
                    old = await message.channel.fetch_message(last_msg_id)
                    await old.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    return
                except discord.HTTPException:
                    pass

            try:
                new = await safe_send(
                    message.channel,
                    content=f"**Sticky:**\n{content}",
                    dedupe_key=f"sticky:{message.channel.id}:{message.id}",
                    dedupe_window=30,
                )
            except (discord.Forbidden, discord.HTTPException):
                return

            if new is None:
                return
            async with db.get() as c:
                await c.execute(
                    "UPDATE stickies SET last_msg_id=? WHERE channel_id=?",
                    (new.id, message.channel.id),
                )
                await c.commit()


async def setup(bot):
    await bot.add_cog(Sticky(bot))
