import time
from collections import defaultdict, deque
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok
from utils.helpers import INVITE_RE

RULE_LABELS = {
    "anti_invite": "Invite links",
    "anti_spam": "Burst spam",
    "anti_caps": "Excessive caps",
    "anti_mention": "Mass mentions",
}


class AutoMod(commands.Cog):
    """Anti-spam, anti-invite, anti-caps, bad words, mass mention."""

    def __init__(self, bot):
        self.bot = bot
        self.recent = defaultdict(lambda: deque(maxlen=10))

    async def _rules(self, guild_id: int):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO automod_rules(guild_id) VALUES(?)", (guild_id,))
            await c.commit()
            cur = await c.execute("SELECT * FROM automod_rules WHERE guild_id=?", (guild_id,))
            return await cur.fetchone()

    @staticmethod
    def _bad_word_list(raw: str | None) -> list[str]:
        return sorted({word.strip().lower() for word in (raw or "").split(",") if word.strip()})

    async def _save_bad_words(self, guild_id: int, words: list[str]):
        async with db.get() as c:
            await c.execute(
                "UPDATE automod_rules SET bad_words=? WHERE guild_id=?",
                (",".join(words), guild_id),
            )
            await c.commit()

    @staticmethod
    def _status_embed(row) -> discord.Embed:
        embed = info("AutoMod", "Review or tune the built-in protections for this server.")
        embed.add_field(name="Invite links", value="On" if row[1] else "Off")
        embed.add_field(name="Burst spam", value="On" if row[2] else "Off")
        embed.add_field(name="Caps filter", value="On" if row[3] else "Off")
        embed.add_field(name="Mass mentions", value="On" if row[4] else "Off")
        embed.add_field(
            name="Blocked words",
            value=", ".join(AutoMod._bad_word_list(row[5])) or "None configured",
            inline=False,
        )
        embed.add_field(name="Max mentions", value=str(row[6]))
        embed.add_field(name="Spam threshold", value=f"{row[7]} messages in 5s")
        embed.add_field(name="Caps threshold", value=f"{row[8]}% uppercase")
        return embed

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Review and tune this server's built-in AutoMod protections",
    )
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        row = await self._rules(ctx.guild.id)
        await ctx.send(embed=self._status_embed(row))

    @automod.command(name="toggle", description="Enable or disable a specific AutoMod rule")
    @app_commands.describe(rule="Rule to enable or disable")
    @commands.has_permissions(manage_guild=True)
    async def toggle(
        self,
        ctx,
        rule: Literal["anti_invite", "anti_spam", "anti_caps", "anti_mention"],
    ):
        await self._rules(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                f"UPDATE automod_rules SET {rule}=1-{rule} WHERE guild_id=?",
                (ctx.guild.id,),
            )
            await c.commit()
        updated = await self._rules(ctx.guild.id)
        state = (
            "enabled"
            if updated[{"anti_invite": 1, "anti_spam": 2, "anti_caps": 3, "anti_mention": 4}[rule]]
            else "disabled"
        )
        await ctx.send(embed=ok(f"{RULE_LABELS[rule]} is now {state}."))

    @automod.command(name="badword", description="Add a blocked word or phrase")
    @app_commands.describe(word="Word or phrase AutoMod should remove")
    @commands.has_permissions(manage_guild=True)
    async def badword(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        if not cleaned:
            return await ctx.send(embed=err("Provide a word or phrase to block."))
        row = await self._rules(ctx.guild.id)
        words = self._bad_word_list(row[5])
        if cleaned in words:
            return await ctx.send(embed=info("AutoMod", f"`{cleaned}` is already blocked."))
        words.append(cleaned)
        await self._save_bad_words(ctx.guild.id, sorted(words))
        await ctx.send(embed=ok(f"Blocked word added: `{cleaned}`"))

    @automod.command(name="unbadword", description="Remove a blocked word or phrase")
    @app_commands.describe(word="Word or phrase to remove from the block list")
    @commands.has_permissions(manage_guild=True)
    async def unbadword(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        row = await self._rules(ctx.guild.id)
        words = self._bad_word_list(row[5])
        if cleaned not in words:
            return await ctx.send(embed=err(f"`{cleaned}` is not on the blocked-word list."))
        words.remove(cleaned)
        await self._save_bad_words(ctx.guild.id, words)
        await ctx.send(embed=ok(f"Removed blocked word: `{cleaned}`"))

    @automod.command(name="badwords", description="List all blocked words and phrases")
    @commands.has_permissions(manage_guild=True)
    async def badwords(self, ctx):
        row = await self._rules(ctx.guild.id)
        words = self._bad_word_list(row[5])
        await ctx.send(
            embed=info(
                "Blocked words",
                ", ".join(words) if words else "No blocked words are configured yet.",
            )
        )

    @automod.command(name="mentions", description="Set the maximum mentions allowed per message")
    @app_commands.describe(count="Mention count that should trigger the filter")
    @commands.has_permissions(manage_guild=True)
    async def mentions(self, ctx, count: int):
        if count < 1 or count > 50:
            return await ctx.send(embed=err("Max mentions must be between 1 and 50."))
        await self._rules(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                "UPDATE automod_rules SET max_mentions=? WHERE guild_id=?",
                (count, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Mass-mention threshold set to {count}."))

    @automod.command(name="spamthreshold", description="Set how many quick messages count as spam")
    @app_commands.describe(count="Number of recent messages allowed inside the 5-second spam window")
    @commands.has_permissions(manage_guild=True)
    async def spamthreshold(self, ctx, count: int):
        if count < 3 or count > 20:
            return await ctx.send(embed=err("Spam threshold must be between 3 and 20 messages."))
        await self._rules(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                "UPDATE automod_rules SET spam_threshold=? WHERE guild_id=?",
                (count, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Spam threshold set to {count} messages in 5 seconds."))

    @automod.command(name="capspercent", description="Set the uppercase percentage that triggers caps filtering")
    @app_commands.describe(percent="Uppercase percentage allowed before a message is removed")
    @commands.has_permissions(manage_guild=True)
    async def capspercent(self, ctx, percent: int):
        if percent < 25 or percent > 100:
            return await ctx.send(embed=err("Caps percentage must be between 25 and 100."))
        await self._rules(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                "UPDATE automod_rules SET caps_percent=? WHERE guild_id=?",
                (percent, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Caps threshold set to {percent}% uppercase."))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            return
        row = await self._rules(message.guild.id)
        (
            _guild_id,
            anti_invite,
            anti_spam,
            anti_caps,
            anti_mention,
            bad_words,
            max_mentions,
            spam_threshold,
            caps_percent,
        ) = row
        content = message.content or ""

        if anti_invite and INVITE_RE.search(content):
            await self._punish(message, "Invite links are not allowed here")
            return
        if anti_mention and len(message.mentions) > max_mentions:
            await self._punish(message, f"Too many mentions (limit: {max_mentions})")
            return
        if anti_caps and len(content) > 10:
            upper = sum(1 for ch in content if ch.isupper())
            if upper / max(1, len(content)) * 100 > caps_percent:
                await self._punish(message, "Too many capital letters")
                return
        if bad_words:
            lowered = content.lower()
            for word in self._bad_word_list(bad_words):
                if word and word in lowered:
                    await self._punish(message, "That message matched a blocked word")
                    return
        if anti_spam:
            key = (message.guild.id, message.author.id)
            self.recent[key].append(time.time())
            if len(self.recent[key]) >= spam_threshold:
                span = self.recent[key][-1] - self.recent[key][0]
                if span < 5:
                    await self._punish(message, "Please slow down")
                    self.recent[key].clear()

    async def _punish(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        try:
            await message.channel.send(
                f"{message.author.mention} your message was removed: {reason}.",
                delete_after=5,
            )
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
