import re

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok

MATCH_TYPES = ("contains", "strict", "exact", "startswith", "endswith", "regex")


class Autoresponders(commands.Cog):
    """Trigger-response automation with several match styles."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(
        invoke_without_command=True,
        aliases=["triggers", "autoresponse"],
        description="Manage autoresponder triggers and replies",
    )
    @commands.has_permissions(manage_guild=True)
    async def ar(self, ctx):
        await ctx.send(
            embed=info(
                "Autoresponders",
                "Use `/ar add`, `/ar strict`, `/ar exact`, `/ar startswith`, "
                "`/ar endswith`, `/ar regex`, `/ar test`, `/ar list`, and `/ar remove`.",
            )
        )

    async def _add(self, ctx, body: str, match_type: str):
        if "|" not in body:
            return await ctx.send(
                embed=err("Use `trigger|response`. Example: `!ar add hello|Hi there`."),
            )
        trigger, response = body.split("|", 1)
        trigger = trigger.strip()
        response = response.strip()
        if not trigger or not response:
            return await ctx.send(embed=err("Both the trigger and the response are required."))
        async with db.get() as c:
            cur = await c.execute(
                "INSERT INTO autoresponders(guild_id,trigger,response,match_type) VALUES(?,?,?,?)",
                (ctx.guild.id, trigger, response, match_type),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Saved autoresponder #{cur.lastrowid} with `{match_type}` matching for `{trigger}`."))

    async def _matching_autoresponder(self, guild_id: int, content: str):
        lower = content.lower()
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, trigger, response, match_type FROM autoresponders WHERE guild_id=? ORDER BY id",
                (guild_id,),
            )
            rows = await cur.fetchall()
        for row in rows:
            ar_id, trigger, response, match_type = row
            trigger_lower = trigger.lower()
            matched = False
            if match_type == "contains":
                matched = re.search(r"\b" + re.escape(trigger_lower) + r"\b", lower) is not None
            elif match_type == "strict":
                matched = trigger_lower in lower
            elif match_type == "exact":
                matched = lower.strip() == trigger_lower
            elif match_type == "startswith":
                matched = lower.startswith(trigger_lower)
            elif match_type == "endswith":
                matched = lower.endswith(trigger_lower)
            elif match_type == "regex":
                try:
                    matched = re.search(trigger, content) is not None
                except re.error:
                    matched = False
            if matched:
                return row
        return None

    async def _autoresponder_autocomplete(self, interaction: discord.Interaction, current: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, trigger, match_type FROM autoresponders WHERE guild_id=? ORDER BY id DESC LIMIT 50",
                (interaction.guild_id,),
            )
            rows = await cur.fetchall()
        choices = []
        needle = current.lower()
        for ar_id, trigger, match_type in rows:
            label = f"#{ar_id} [{match_type}] {trigger}"
            if not needle or needle in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=ar_id))
            if len(choices) >= 25:
                break
        return choices

    @ar.command(name="add", aliases=["create"], description="Create a contains-match autoresponder")
    @app_commands.describe(body="Use trigger|response, for example hello|Hi there")
    @commands.has_permissions(manage_guild=True)
    async def add(self, ctx, *, body: str):
        await self._add(ctx, body, "contains")

    @ar.command(name="strict", aliases=["s"], description="Create a strict substring autoresponder")
    @app_commands.describe(body="Use trigger|response for the strict match rule")
    @commands.has_permissions(manage_guild=True)
    async def ar_strict(self, ctx, *, body: str):
        await self._add(ctx, body, "strict")

    @ar.command(name="exact", aliases=["e"], description="Create an exact-match autoresponder")
    @app_commands.describe(body="Use trigger|response for the exact match rule")
    @commands.has_permissions(manage_guild=True)
    async def ar_exact(self, ctx, *, body: str):
        await self._add(ctx, body, "exact")

    @ar.command(name="startswith", aliases=["sw"], description="Create a starts-with autoresponder")
    @app_commands.describe(body="Use trigger|response for the starts-with rule")
    @commands.has_permissions(manage_guild=True)
    async def ar_sw(self, ctx, *, body: str):
        await self._add(ctx, body, "startswith")

    @ar.command(name="endswith", aliases=["ew"], description="Create an ends-with autoresponder")
    @app_commands.describe(body="Use trigger|response for the ends-with rule")
    @commands.has_permissions(manage_guild=True)
    async def ar_ew(self, ctx, *, body: str):
        await self._add(ctx, body, "endswith")

    @ar.command(name="regex", description="Create a regex-based autoresponder")
    @app_commands.describe(body="Use pattern|response for the regex rule")
    @commands.has_permissions(manage_guild=True)
    async def ar_regex(self, ctx, *, body: str):
        if "|" not in body:
            return await ctx.send(
                embed=err("Use `pattern|response`. Example: `!ar regex ^hi there$|Hello`."),
            )
        pattern, _ = body.split("|", 1)
        try:
            re.compile(pattern)
        except re.error as exc:
            return await ctx.send(embed=err(f"Invalid regex: {exc}"))
        await self._add(ctx, body, "regex")

    @ar.command(name="test", description="Check which autoresponder would fire for a message")
    @app_commands.describe(content="Message content to test against the saved autoresponders")
    @commands.has_permissions(manage_guild=True)
    async def ar_test(self, ctx, *, content: str):
        match = await self._matching_autoresponder(ctx.guild.id, content)
        if not match:
            return await ctx.send(embed=info("Autoresponders", "No saved autoresponder would match that message."))
        ar_id, trigger, response, match_type = match
        embed = info("Autoresponder match")
        embed.add_field(name="ID", value=str(ar_id))
        embed.add_field(name="Match type", value=match_type)
        embed.add_field(name="Trigger", value=trigger, inline=False)
        embed.add_field(name="Response", value=response[:1024], inline=False)
        await ctx.send(embed=embed)

    @ar.command(name="remove", aliases=["del", "delete", "-"], description="Delete an autoresponder trigger")
    @app_commands.describe(ar_id="Saved autoresponder ID to delete")
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx, ar_id: int):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM autoresponders WHERE id=? AND guild_id=?",
                (ar_id, ctx.guild.id),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed autoresponder #{ar_id}."))
        else:
            await ctx.send(embed=err(f"No autoresponder with ID `{ar_id}` was found."))

    @remove.autocomplete("ar_id")
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._autoresponder_autocomplete(interaction, current)

    @ar.command(name="clear", description="Remove all autoresponders for this server")
    @commands.has_permissions(manage_guild=True)
    async def ar_clear(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM autoresponders WHERE guild_id=?",
                (ctx.guild.id,),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Cleared {cur.rowcount} autoresponder(s)."))

    @ar.command(name="list", description="List saved autoresponder triggers")
    @commands.has_permissions(manage_guild=True)
    async def ar_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id,trigger,response,match_type FROM autoresponders WHERE guild_id=? ORDER BY id",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=info("Autoresponders", "No autoresponders are configured."))
        embed = discord.Embed(title="Autoresponders", color=0x5865F2)
        for ar_id, trigger, response, match_type in rows[:25]:
            embed.add_field(
                name=f"#{ar_id} [{match_type}] {trigger}",
                value=response[:200],
                inline=False,
            )
        if len(rows) > 25:
            embed.set_footer(text=f"Showing 25 of {len(rows)} autoresponders.")
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or not message.content:
            return
        match = await self._matching_autoresponder(message.guild.id, message.content)
        if not match:
            return
        _ar_id, _trigger, response, _match_type = match
        try:
            await message.channel.send(response)
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Autoresponders(bot))
