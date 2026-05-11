import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.helpers import now


class Tags(commands.Cog):
    """Custom text snippets."""

    def __init__(self, bot):
        self.bot = bot

    async def _tag_autocomplete(self, interaction: discord.Interaction, current: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT name, uses FROM tags WHERE guild_id=? ORDER BY uses DESC LIMIT 200", (interaction.guild_id,)
            )
            rows = await cur.fetchall()
        cur_l = (current or "").lower()
        out = []
        for name, uses in rows:
            if not cur_l or cur_l in name.lower():
                out.append(app_commands.Choice(name=f"{name} ({uses} uses)"[:100], value=name))
            if len(out) >= 25:
                break
        return out

    @commands.hybrid_group(invoke_without_command=True, description="Recall a stored snippet")
    @app_commands.describe(name="Tag name (autocompletes from stored tags)")
    async def tag(self, ctx, *, name: str):
        async with db.get() as c:
            cur = await c.execute("SELECT content FROM tags WHERE guild_id=? AND name=?", (ctx.guild.id, name.lower()))
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f"Tag `{name}` not found.")
            await c.execute("UPDATE tags SET uses=uses+1 WHERE guild_id=? AND name=?", (ctx.guild.id, name.lower()))
            await c.commit()
        await ctx.send(row[0])

    @tag.autocomplete("name")
    async def _ac_tag_root(self, interaction, current):
        return await self._tag_autocomplete(interaction, current)

    @tag.command()
    async def create(self, ctx, name: str, *, content: str):
        async with db.get() as c:
            try:
                await c.execute(
                    "INSERT INTO tags(guild_id,name,content,owner_id,created_at) VALUES(?,?,?,?,?)",
                    (ctx.guild.id, name.lower(), content, ctx.author.id, now()),
                )
                await c.commit()
            except Exception:
                return await ctx.send("Tag already exists.")
        await ctx.send(f"Created `{name}`.")

    @tag.command()
    async def edit(self, ctx, name: str, *, content: str):
        async with db.get() as c:
            cur = await c.execute("SELECT owner_id FROM tags WHERE guild_id=? AND name=?", (ctx.guild.id, name.lower()))
            row = await cur.fetchone()
            if not row:
                return await ctx.send("No such tag.")
            if row[0] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
                return await ctx.send("Not your tag.")
            await c.execute(
                "UPDATE tags SET content=? WHERE guild_id=? AND name=?", (content, ctx.guild.id, name.lower())
            )
            await c.commit()
        await ctx.send("Edited.")

    @tag.command()
    async def delete(self, ctx, name: str):
        async with db.get() as c:
            cur = await c.execute("SELECT owner_id FROM tags WHERE guild_id=? AND name=?", (ctx.guild.id, name.lower()))
            row = await cur.fetchone()
            if not row:
                return await ctx.send("No such tag.")
            if row[0] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
                return await ctx.send("Not your tag.")
            await c.execute("DELETE FROM tags WHERE guild_id=? AND name=?", (ctx.guild.id, name.lower()))
            await c.commit()
        await ctx.send("Deleted.")

    @tag.command(name="list")
    async def tag_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute("SELECT name, uses FROM tags WHERE guild_id=? ORDER BY uses DESC", (ctx.guild.id,))
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("No tags.")
        e = discord.Embed(title="Tags", color=0x5865F2)
        e.description = "\n".join(f"`{n}` ({u} uses)" for n, u in rows[:30])
        await ctx.send(embed=e)

    @tag.command()
    async def info(self, ctx, name: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT owner_id,uses,created_at FROM tags WHERE guild_id=? AND name=?",
                (ctx.guild.id, name.lower()),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send("No such tag.")
        owner = ctx.guild.get_member(row[0])
        e = discord.Embed(title=f"Tag: {name}", color=0x5865F2)
        e.add_field(name="Owner", value=str(owner or row[0]))
        e.add_field(name="Uses", value=row[1])
        e.add_field(name="Created", value=f"<t:{row[2]}:R>")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Tags(bot))
