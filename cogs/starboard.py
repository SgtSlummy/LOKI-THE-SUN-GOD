import asyncio

import discord
from discord.ext import commands

from utils import db
from utils.helpers import safe_send

STAR = "⭐"


class Starboard(commands.Cog):
    """Pin popular messages to a starboard channel."""

    def __init__(self, bot):
        self.bot = bot
        self._message_locks: dict[int, asyncio.Lock] = {}

    async def _cfg(self, gid):
        async with db.get() as c:
            cur = await c.execute("SELECT starboard_channel, star_threshold FROM guild_config WHERE guild_id=?", (gid,))
            return await cur.fetchone()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) != STAR or not payload.guild_id:
            return
        cfg = await self._cfg(payload.guild_id)
        if not cfg or not cfg[0]:
            return
        sb_channel_id, threshold = cfg
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        if message.author.bot:
            return
        lock = self._message_locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            star_reaction = next((r for r in message.reactions if str(r.emoji) == STAR), None)
            count = star_reaction.count if star_reaction else 0
            if count < threshold:
                return

            async with db.get() as c:
                cur = await c.execute("SELECT star_message_id FROM starboard WHERE message_id=?", (message.id,))
                row = await cur.fetchone()

            sb_channel = self.bot.get_channel(sb_channel_id)
            if not sb_channel:
                return

            embed = discord.Embed(description=message.content, color=0xFEE75C, timestamp=message.created_at)
            embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            embed.add_field(name="Source", value=f"[Jump]({message.jump_url})")
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            content = f"{STAR} **{count}** {message.channel.mention}"

            star_message_id = row[0] if row else None
            if star_message_id:
                try:
                    sm = await sb_channel.fetch_message(star_message_id)
                    await sm.edit(content=content, embed=embed)
                except discord.NotFound:
                    star_message_id = None

            if not star_message_id:
                sm = await safe_send(
                    sb_channel,
                    content=content,
                    embed=embed,
                    dedupe_key=f"starboard:{message.id}",
                    dedupe_window=30,
                )
                if sm is None:
                    return
                async with db.get() as c:
                    await c.execute(
                        "INSERT OR REPLACE INTO starboard(message_id,star_message_id,guild_id,stars) VALUES(?,?,?,?)",
                        (message.id, sm.id, payload.guild_id, count),
                    )
                    await c.commit()


async def setup(bot):
    await bot.add_cog(Starboard(bot))
