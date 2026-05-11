import json

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok


def _normalize_color(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower().removeprefix("#").removeprefix("0x")
        try:
            return int(cleaned, 16)
        except ValueError:
            return 0x5865F2
    return 0x5865F2


def normalize_embed_payload(data: dict) -> dict:
    payload = {
        "title": str(data.get("title", ""))[:256],
        "description": str(data.get("description", ""))[:4096],
        "url": data.get("url"),
        "color": _normalize_color(data.get("color", 0x5865F2)),
        "image": data.get("image"),
        "thumbnail": data.get("thumbnail"),
        "footer": str(data.get("footer", ""))[:2048] if data.get("footer") else "",
        "fields": [],
    }
    for field in (data.get("fields") or [])[:25]:
        payload["fields"].append(
            {
                "name": str(field.get("name", "-"))[:256] or "-",
                "value": str(field.get("value", "-"))[:1024] or "-",
                "inline": bool(field.get("inline", False)),
            }
        )
    return payload


def build_embed(data: dict) -> discord.Embed:
    payload = normalize_embed_payload(data)
    embed = discord.Embed(
        title=payload["title"],
        description=payload["description"],
        url=payload.get("url"),
        color=payload["color"],
    )
    if payload.get("image"):
        embed.set_image(url=payload["image"])
    if payload.get("thumbnail"):
        embed.set_thumbnail(url=payload["thumbnail"])
    if payload.get("footer"):
        embed.set_footer(text=payload["footer"])
    for field in payload.get("fields", []):
        embed.add_field(
            name=field["name"],
            value=field["value"],
            inline=field["inline"],
        )
    return embed


class CEmbed(commands.Cog):
    """Saved custom embeds."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_payload(self, guild_id: int, name: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT payload FROM custom_embeds WHERE guild_id=? AND name=?",
                (guild_id, name.lower()),
            )
            return await cur.fetchone()

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Send or manage saved custom embed presets",
    )
    @app_commands.describe(
        name="Optional saved embed name to send right away",
        channel="Optional channel where the saved embed should be sent",
    )
    async def cembed(self, ctx, name: str | None = None, channel: discord.TextChannel | None = None):
        if not name:
            return await ctx.send(
                embed=info(
                    "Custom embeds",
                    "Use `/cembed send`, `/cembed save`, `/cembed source`, "
                    "`/cembed edit`, `/cembed delete`, or `/cembed list`.",
                )
            )
        await self._send_saved_embed(ctx, name, channel)

    async def _send_saved_embed(self, ctx, name: str, channel: discord.TextChannel | None = None):
        row = await self._get_payload(ctx.guild.id, name)
        if not row:
            return await ctx.send(embed=err(f"No saved embed named `{name}` was found."))
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return await ctx.send(embed=err("That saved embed has an invalid JSON payload."))
        target = channel or ctx.channel
        await target.send(embed=build_embed(data))
        if target != ctx.channel:
            await ctx.send(embed=ok(f"Sent `{name}` to {target.mention}."))

    @cembed.command(name="send", description="Send a saved custom embed")
    @app_commands.describe(
        name="Saved embed preset name to send",
        channel="Optional channel to post the embed in",
    )
    async def cembed_send(self, ctx, name: str, channel: discord.TextChannel | None = None):
        await self._send_saved_embed(ctx, name, channel)

    @cembed.command(name="save", description="Save a custom embed preset for later use")
    @app_commands.describe(name="Name to save the embed under", payload="Embed payload JSON to store")
    @commands.has_permissions(manage_messages=True)
    async def cembed_save(self, ctx, name: str, *, payload: str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            return await ctx.send(embed=err(f"Invalid JSON: {exc}"))
        if not isinstance(parsed, dict):
            return await ctx.send(embed=err("The payload must be a JSON object."))
        normalized = normalize_embed_payload(parsed)
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO custom_embeds(guild_id,name,payload) VALUES(?,?,?)",
                (ctx.guild.id, name.lower(), json.dumps(normalized)),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Saved custom embed `{name}`."))

    @cembed.command(name="edit", description="Update a saved custom embed preset")
    @app_commands.describe(name="Saved embed preset to overwrite", payload="Updated embed payload JSON")
    @commands.has_permissions(manage_messages=True)
    async def cembed_edit(self, ctx, name: str, *, payload: str):
        await ctx.invoke(self.cembed_save, name=name, payload=payload)

    @cembed.command(name="source", description="Show the stored JSON payload for a saved embed preset")
    @app_commands.describe(name="Saved embed preset to inspect")
    async def cembed_source(self, ctx, name: str):
        row = await self._get_payload(ctx.guild.id, name)
        if not row:
            return await ctx.send(embed=err(f"No saved embed named `{name}` was found."))
        payload = row[0][:1900]
        await ctx.send(f"```json\n{payload}\n```")

    @cembed.command(name="delete", description="Delete a saved custom embed preset")
    @app_commands.describe(name="Saved embed preset to delete")
    @commands.has_permissions(manage_messages=True)
    async def cembed_delete(self, ctx, name: str):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM custom_embeds WHERE guild_id=? AND name=?",
                (ctx.guild.id, name.lower()),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Deleted custom embed `{name}`."))
        else:
            await ctx.send(embed=err(f"No saved embed named `{name}` was found."))

    @cembed.command(name="list", description="List saved custom embed presets")
    async def cembed_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT name FROM custom_embeds WHERE guild_id=? ORDER BY name",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=info("Custom embeds", "No custom embeds are saved for this server."))
        await ctx.send(embed=info("Custom embeds", ", ".join(f"`{row[0]}`" for row in rows)))


async def setup(bot):
    await bot.add_cog(CEmbed(bot))
