import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok
from utils.helpers import now

DECISION_COLORS = {
    "approved": 0x57F287,
    "denied": 0xED4245,
    "considered": 0xFEE75C,
    "implemented": 0x5865F2,
}


class Suggestions(commands.Cog):
    """Suggestion system with vote reactions and staff decisions."""

    def __init__(self, bot):
        self.bot = bot

    async def _cfg(self, guild_id: int):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO suggestion_config(guild_id) VALUES(?)", (guild_id,))
            await c.commit()
            cur = await c.execute("SELECT * FROM suggestion_config WHERE guild_id=?", (guild_id,))
            return await cur.fetchone()

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage suggestion system settings for this server",
    )
    async def suggestion(self, ctx):
        await ctx.send(
            embed=info(
                "Suggestions",
                "Use `/suggestion channel`, `/suggestion anon`, `/suggestion server`, "
                "`/suggestion who`, or `/suggestion submit`.",
            )
        )

    @suggestion.command(name="channel", description="Set the channel where suggestions are posted")
    @app_commands.describe(ch="Channel where new suggestions should be sent")
    @commands.has_permissions(manage_guild=True)
    async def channel(self, ctx, ch: discord.TextChannel):
        await self._cfg(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                "UPDATE suggestion_config SET channel_id=? WHERE guild_id=?",
                (ch.id, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Suggestions will now post in {ch.mention}."))

    @suggestion.command(name="anon", description="Toggle anonymous suggestions on or off")
    @commands.has_permissions(manage_guild=True)
    async def anon(self, ctx):
        cfg = await self._cfg(ctx.guild.id)
        new_value = 1 - (cfg[2] or 0)
        async with db.get() as c:
            await c.execute(
                "UPDATE suggestion_config SET anonymous=? WHERE guild_id=?",
                (new_value, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Anonymous suggestions are now {'enabled' if new_value else 'disabled'}."))

    @suggestion.command(name="server", description="Show the current suggestion configuration for this server")
    @commands.has_permissions(manage_guild=True)
    async def server(self, ctx):
        cfg = await self._cfg(ctx.guild.id)
        async with db.get() as c:
            cur = await c.execute(
                "SELECT COUNT(*), SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) FROM suggestions WHERE guild_id=?",
                (ctx.guild.id,),
            )
            total, pending = await cur.fetchone()
        channel = ctx.guild.get_channel(cfg[1]) if cfg and cfg[1] else None
        embed = info("Suggestion system")
        embed.add_field(name="Channel", value=channel.mention if channel else "Not configured", inline=False)
        embed.add_field(name="Anonymous", value="On" if cfg and cfg[2] else "Off")
        embed.add_field(name="Total suggestions", value=str(total or 0))
        embed.add_field(name="Pending", value=str(pending or 0))
        await ctx.send(embed=embed)

    @suggestion.command(name="who", description="Reveal the author of a saved suggestion")
    @app_commands.describe(sid="Suggestion ID to inspect")
    @commands.has_permissions(manage_messages=True)
    async def who(self, ctx, sid: int):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, status, content FROM suggestions WHERE id=? AND guild_id=?",
                (sid, ctx.guild.id),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(embed=err("That suggestion ID was not found."))
        user_id, status, content = row
        member = ctx.guild.get_member(user_id)
        embed = info(f"Suggestion #{sid}")
        embed.add_field(name="Author", value=member.mention if member else f"<@{user_id}>")
        embed.add_field(name="Status", value=status)
        embed.add_field(name="Preview", value=content[:1024], inline=False)
        await ctx.send(embed=embed)

    @suggestion.command(name="submit", description="Submit a suggestion through the group command")
    @app_commands.describe(content="Suggestion text to post")
    async def suggestion_submit(self, ctx, *, content: str):
        await self._submit_suggestion(ctx, content)

    async def _submit_suggestion(self, ctx, content: str):
        cfg = await self._cfg(ctx.guild.id)
        if not cfg or not cfg[1]:
            return await ctx.send(embed=err("Suggestion channel is not configured yet."))
        channel = self.bot.get_channel(cfg[1])
        if not channel:
            return await ctx.send(embed=err("The configured suggestion channel no longer exists."))
        if not content.strip():
            return await ctx.send(embed=err("Suggestion text cannot be empty."))
        anonymous = bool(cfg[2])
        embed = discord.Embed(
            description=content,
            color=0x5865F2,
            timestamp=getattr(getattr(ctx, "message", None), "created_at", None) or discord.utils.utcnow(),
        )
        if anonymous:
            embed.set_author(name="Anonymous")
        else:
            embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        async with db.get() as c:
            cur = await c.execute(
                "INSERT INTO suggestions(guild_id,user_id,channel_id,content,status,created_at) VALUES(?,?,?,?,?,?)",
                (ctx.guild.id, ctx.author.id, channel.id, content, "pending", now()),
            )
            sid = cur.lastrowid
            await c.commit()
        embed.set_footer(text=f"Suggestion #{sid}")
        message = await channel.send(embed=embed)
        await message.add_reaction("\N{THUMBS UP SIGN}")
        await message.add_reaction("\N{THUMBS DOWN SIGN}")
        async with db.get() as c:
            await c.execute("UPDATE suggestions SET message_id=? WHERE id=?", (message.id, sid))
            await c.commit()
        if getattr(ctx, "message", None):
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=ok(f"Submitted suggestion #{sid}."), delete_after=5)

    @commands.hybrid_command(name="suggest", description="Create a suggestion in the configured suggestion channel")
    @app_commands.describe(content="Suggestion text to post")
    async def suggest(self, ctx, *, content: str):
        await self._submit_suggestion(ctx, content)

    async def _decide(self, ctx, sid: int, status: str, reason: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, channel_id, message_id, content FROM suggestions WHERE id=? AND guild_id=?",
                (sid, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(embed=err("That suggestion ID was not found."))
            await c.execute("UPDATE suggestions SET status=? WHERE id=?", (status, sid))
            await c.commit()
        user_id, channel_id, message_id, content = row
        channel = self.bot.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                embed = message.embeds[0] if message.embeds else discord.Embed(description=content)
                embed.color = DECISION_COLORS.get(status, 0x5865F2)
                embed.add_field(
                    name=status.title(),
                    value=f"by {ctx.author.mention}: {reason or 'no reason provided'}",
                    inline=False,
                )
                await message.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(f"Your suggestion #{sid} was **{status}**: {reason or '(no reason provided)'}")
        except discord.Forbidden:
            pass
        await ctx.send(embed=ok(f"Suggestion #{sid} marked as {status}."))

    @commands.hybrid_command(name="approve", description="Mark a suggestion as approved")
    @app_commands.describe(sid="Suggestion ID to approve", reason="Optional staff note for the decision")
    @commands.has_permissions(manage_messages=True)
    async def approve(self, ctx, sid: int, *, reason: str = ""):
        await self._decide(ctx, sid, "approved", reason)

    @commands.hybrid_command(name="deny", description="Mark a suggestion as denied")
    @app_commands.describe(sid="Suggestion ID to deny", reason="Optional staff note for the decision")
    @commands.has_permissions(manage_messages=True)
    async def deny(self, ctx, sid: int, *, reason: str = ""):
        await self._decide(ctx, sid, "denied", reason)

    @commands.hybrid_command(name="consider", description="Mark a suggestion as under consideration")
    @app_commands.describe(sid="Suggestion ID to update", reason="Optional staff note for the decision")
    @commands.has_permissions(manage_messages=True)
    async def consider(self, ctx, sid: int, *, reason: str = ""):
        await self._decide(ctx, sid, "considered", reason)

    @commands.hybrid_command(name="implemented", description="Mark a suggestion as implemented")
    @app_commands.describe(sid="Suggestion ID to update", reason="Optional staff note for the decision")
    @commands.has_permissions(manage_messages=True)
    async def implemented(self, ctx, sid: int, *, reason: str = ""):
        await self._decide(ctx, sid, "implemented", reason)


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
