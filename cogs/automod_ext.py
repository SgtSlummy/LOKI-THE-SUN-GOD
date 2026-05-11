import re
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok

URL_RE = re.compile(r"https?://([^/\s]+)")


def _normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    return value.lstrip("www.").strip("/")


class AutoModExt(commands.Cog):
    """Extended delete-only filters for words and domains."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage the server word-censor list",
    )
    @commands.has_permissions(manage_guild=True)
    async def censor(self, ctx):
        await ctx.send(
            embed=info(
                "Censor",
                "Use `/censor add`, `/censor remove`, `/censor list`, and `/censor clear`.",
            )
        )

    @censor.command(name="add", description="Add a blocked word or phrase to the censor list")
    @app_commands.describe(word="Word or phrase to remove when members post it")
    @commands.has_permissions(manage_guild=True)
    async def censor_add(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        if not cleaned:
            return await ctx.send(embed=err("Provide a word or phrase to block."))
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO censor_words(guild_id,word) VALUES(?,?)",
                (ctx.guild.id, cleaned),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Added `{cleaned}` to the censor list."))

    @censor.command(name="remove", description="Remove a word or phrase from the censor list")
    @app_commands.describe(word="Saved word or phrase to remove from the list")
    @commands.has_permissions(manage_guild=True)
    async def censor_remove(self, ctx, *, word: str):
        cleaned = word.strip().lower()
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM censor_words WHERE guild_id=? AND word=?",
                (ctx.guild.id, cleaned),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed `{cleaned}` from the censor list."))
        else:
            await ctx.send(embed=err(f"`{cleaned}` was not in the censor list."))

    @censor.command(name="list", description="Show the current censor list")
    @commands.has_permissions(manage_guild=True)
    async def censor_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT word FROM censor_words WHERE guild_id=? ORDER BY word",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        await ctx.send(
            embed=info(
                "Censored words",
                ", ".join(row[0] for row in rows) if rows else "No censored words are configured.",
            )
        )

    @censor.command(name="clear", description="Clear the full censor list")
    @commands.has_permissions(manage_guild=True)
    async def censor_clear(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM censor_words WHERE guild_id=?",
                (ctx.guild.id,),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Cleared {cur.rowcount} censored word(s)."))

    @commands.hybrid_group(
        invoke_without_command=True,
        description="Manage link blocklists and allowlists for this server",
    )
    @commands.has_permissions(manage_guild=True)
    async def linkspam(self, ctx):
        await ctx.send(
            embed=info(
                "Link filter",
                "Use `/linkspam block`, `/linkspam allow`, `/linkspam unblock`, "
                "`/linkspam unallow`, and `/linkspam list`.",
            )
        )

    @linkspam.command(name="block", aliases=["bl"], description="Block links from a domain")
    @app_commands.describe(domain="Domain or URL to block")
    @commands.has_permissions(manage_guild=True)
    async def link_block(self, ctx, domain: str):
        cleaned = _normalize_domain(domain)
        if not cleaned:
            return await ctx.send(embed=err("Provide a valid domain or URL to block."))
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO link_filter(guild_id,domain,mode) VALUES(?,?,?)",
                (ctx.guild.id, cleaned, "bl"),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Blocked links from `{cleaned}`."))

    @linkspam.command(name="allow", aliases=["wl"], description="Allow a domain when using an allowlist")
    @app_commands.describe(domain="Domain or URL to allow")
    @commands.has_permissions(manage_guild=True)
    async def link_allow(self, ctx, domain: str):
        cleaned = _normalize_domain(domain)
        if not cleaned:
            return await ctx.send(embed=err("Provide a valid domain or URL to allow."))
        async with db.get() as c:
            await c.execute(
                "INSERT OR REPLACE INTO link_filter(guild_id,domain,mode) VALUES(?,?,?)",
                (ctx.guild.id, cleaned, "wl"),
            )
            await c.commit()
        await ctx.send(embed=ok(f"Allowed `{cleaned}`. When any allowlist entries exist, other domains are blocked."))

    @linkspam.command(name="unblock", aliases=["unbl"], description="Remove a domain from the blocklist")
    @app_commands.describe(domain="Blocked domain or URL to remove")
    @commands.has_permissions(manage_guild=True)
    async def link_unblock(self, ctx, domain: str):
        cleaned = _normalize_domain(domain)
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM link_filter WHERE guild_id=? AND domain=? AND mode='bl'",
                (ctx.guild.id, cleaned),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed `{cleaned}` from the blocked-domain list."))
        else:
            await ctx.send(embed=err(f"`{cleaned}` was not in the blocked-domain list."))

    @linkspam.command(name="unallow", aliases=["unwl"], description="Remove a domain from the allowlist")
    @app_commands.describe(domain="Allowed domain or URL to remove")
    @commands.has_permissions(manage_guild=True)
    async def link_unallow(self, ctx, domain: str):
        cleaned = _normalize_domain(domain)
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM link_filter WHERE guild_id=? AND domain=? AND mode='wl'",
                (ctx.guild.id, cleaned),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed `{cleaned}` from the allowed-domain list."))
        else:
            await ctx.send(embed=err(f"`{cleaned}` was not in the allowed-domain list."))

    @linkspam.command(name="list", description="Show the current link blocklist and allowlist")
    @commands.has_permissions(manage_guild=True)
    async def link_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT domain, mode FROM link_filter WHERE guild_id=? ORDER BY mode, domain",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        blocked = ", ".join(domain for domain, mode in rows if mode == "bl") or "None configured"
        allowed = ", ".join(domain for domain, mode in rows if mode == "wl") or "None configured"
        embed = info("Link filter")
        embed.add_field(name="Blocked domains", value=blocked, inline=False)
        embed.add_field(name="Allowed domains", value=allowed, inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            return
        content = message.content or ""
        async with db.get() as c:
            cur = await c.execute(
                "SELECT word FROM censor_words WHERE guild_id=?",
                (message.guild.id,),
            )
            words = [row[0] for row in await cur.fetchall()]
            cur = await c.execute(
                "SELECT domain, mode FROM link_filter WHERE guild_id=?",
                (message.guild.id,),
            )
            filters = await cur.fetchall()
        lower = content.lower()
        for word in words:
            if re.search(r"\b" + re.escape(word) + r"\b", lower):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} your message was removed because it matched a blocked word.",
                        delete_after=5,
                    )
                except discord.Forbidden:
                    pass
                return
        if filters:
            domains = URL_RE.findall(content)
            if domains:
                blocked = {domain for domain, mode in filters if mode == "bl"}
                allowed = {domain for domain, mode in filters if mode == "wl"}
                for domain in domains:
                    cleaned = domain.lower().lstrip("www.")
                    if cleaned in blocked or (allowed and cleaned not in allowed):
                        try:
                            await message.delete()
                            await message.channel.send(
                                f"{message.author.mention} links from that domain are not allowed here.",
                                delete_after=5,
                            )
                        except discord.Forbidden:
                            pass
                        return


async def setup(bot):
    await bot.add_cog(AutoModExt(bot))
