import discord
from discord.ext import commands

from utils import db
from utils.helpers import now


class Notes(commands.Cog):
    """Mod-only notes about users."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def setnote(self, ctx, member: discord.Member, *, content: str):
        async with db.get() as c:
            await c.execute(
                "INSERT INTO notes(guild_id,user_id,mod_id,content,created_at) VALUES(?,?,?,?,?)",
                (ctx.guild.id, member.id, ctx.author.id, content, now()),
            )
            await c.commit()
        await ctx.send(f"Note saved on {member}.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def notes(self, ctx, member: discord.Member):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, mod_id, content, created_at FROM notes WHERE guild_id=? AND user_id=? ORDER BY id DESC",
                (ctx.guild.id, member.id),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("None.")
        e = discord.Embed(title=f"Notes for {member}", color=0x5865F2)
        for nid, mid, content, ts in rows[:25]:
            mod = ctx.guild.get_member(mid)
            e.add_field(name=f"#{nid} by {mod or mid} <t:{ts}:R>", value=content[:200], inline=False)
        await ctx.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def removenote(self, ctx, nid: int):
        async with db.get() as c:
            await c.execute("DELETE FROM notes WHERE id=? AND guild_id=?", (nid, ctx.guild.id))
            await c.commit()
        await ctx.send("Removed.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clearnotes(self, ctx, member: discord.Member):
        async with db.get() as c:
            await c.execute("DELETE FROM notes WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
            await c.commit()
        await ctx.send(f"Cleared notes for {member}.")


async def setup(bot):
    await bot.add_cog(Notes(bot))
