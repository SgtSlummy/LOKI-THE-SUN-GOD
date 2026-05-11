import discord
from discord.ext import commands

from utils import db


class Logging(commands.Cog):
    """Server event logging."""

    def __init__(self, bot):
        self.bot = bot

    async def _log_channel(self, guild_id):
        async with db.get() as c:
            cur = await c.execute("SELECT log_channel FROM guild_config WHERE guild_id=?", (guild_id,))
            row = await cur.fetchone()
        if not row or not row[0]:
            return None
        return self.bot.get_channel(row[0])

    async def _send(self, guild_id, embed):
        ch = await self._log_channel(guild_id)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        e = discord.Embed(title="Message Deleted", color=0xED4245, description=message.content or "*embed/attachment*")
        e.add_field(name="Author", value=f"{message.author} ({message.author.id})")
        e.add_field(name="Channel", value=message.channel.mention)
        await self._send(message.guild.id, e)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        e = discord.Embed(title="Message Edited", color=0xFEE75C)
        e.add_field(name="Before", value=(before.content or "*none*")[:1024], inline=False)
        e.add_field(name="After", value=(after.content or "*none*")[:1024], inline=False)
        e.add_field(name="Author", value=f"{before.author}")
        e.add_field(name="Jump", value=f"[link]({after.jump_url})")
        await self._send(before.guild.id, e)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        e = discord.Embed(title="Member Joined", color=0x57F287, description=f"{member.mention} ({member})")
        e.add_field(name="Account created", value=f"<t:{int(member.created_at.timestamp())}:R>")
        await self._send(member.guild.id, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        e = discord.Embed(title="Member Left", color=0xED4245, description=f"{member} ({member.id})")
        await self._send(member.guild.id, e)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        e = discord.Embed(title="Member Banned", color=0xED4245, description=str(user))
        await self._send(guild.id, e)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added = set(after.roles) - set(before.roles)
            removed = set(before.roles) - set(after.roles)
            e = discord.Embed(title="Role Change", color=0x5865F2, description=str(after))
            if added:
                e.add_field(name="Added", value=", ".join(r.mention for r in added))
            if removed:
                e.add_field(name="Removed", value=", ".join(r.mention for r in removed))
            await self._send(after.guild.id, e)
        if before.nick != after.nick:
            e = discord.Embed(title="Nickname Change", color=0x5865F2, description=str(after))
            e.add_field(name="Before", value=before.nick or "*none*")
            e.add_field(name="After", value=after.nick or "*none*")
            await self._send(after.guild.id, e)


async def setup(bot):
    await bot.add_cog(Logging(bot))
