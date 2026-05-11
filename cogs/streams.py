"""
Stream alerts: Twitch, Kick, and TikTok.

The bot polls tracked streamers and posts an embed when they go live.

DB:
    stream_subs(guild_id, platform, channel_name, target_channel_id, mention_role_id, last_status)

Setup examples:
    /streams add platform:twitch name:xqc target:#live ping:@StreamPing
    /streams add platform:kick name:adin target:#live
    /streams add platform:tiktok name:username target:#live

Twitch requires TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in .env.
Kick is polled through a public unauthenticated endpoint.
TikTok support uses the optional TikTokLive package when installed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Literal, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import db
from utils.embeds import err, info, ok, warn
from utils.helpers import safe_send

log = logging.getLogger("loki.streams")

POLL_INTERVAL_SECONDS = 60
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
KICK_BASE = "https://kick.com/api/v2/channels"
PLATFORMS = ("twitch", "kick", "tiktok")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stream_subs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    target_channel_id INTEGER NOT NULL,
    mention_role_id INTEGER,
    last_status INTEGER DEFAULT 0,
    last_event_at INTEGER DEFAULT 0,
    UNIQUE(guild_id, platform, channel_name)
);
"""


def platform_url(platform: str, name: str) -> str:
    if platform == "twitch":
        return f"https://twitch.tv/{name}"
    if platform == "kick":
        return f"https://kick.com/{name}"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{name}/live"
    return f"https://{platform}.com/{name}"


class TwitchClient:
    def __init__(self):
        self.token: Optional[str] = None
        self.token_expiry: float = 0

    async def _ensure_token(self, session: aiohttp.ClientSession):
        if self.token and time.time() < self.token_expiry - 60:
            return
        if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
            raise RuntimeError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET are not set.")
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        ) as response:
            data = await response.json()
        self.token = data["access_token"]
        self.token_expiry = time.time() + int(data.get("expires_in", 3600))

    async def is_live(self, session: aiohttp.ClientSession, login: str) -> Optional[dict]:
        await self._ensure_token(session)
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.token}",
        }
        async with session.get(
            "https://api.twitch.tv/helix/streams",
            headers=headers,
            params={"user_login": login.lower()},
        ) as response:
            data = await response.json()
        return data["data"][0] if data.get("data") else None


async def kick_status(session: aiohttp.ClientSession, slug: str) -> Optional[dict]:
    try:
        async with session.get(f"{KICK_BASE}/{slug.lower()}", timeout=15) as response:
            if response.status != 200:
                return None
            data = await response.json()
        livestream = data.get("livestream")
        if livestream and livestream.get("is_live"):
            return {
                "title": livestream.get("session_title", "Live"),
                "viewer_count": livestream.get("viewer_count", 0),
                "thumbnail": (livestream.get("thumbnail") or {}).get("url"),
                "category": (livestream.get("categories") or [{}])[0].get("name", "-"),
                "url": platform_url("kick", slug),
                "user_login": data.get("user", {}).get("username", slug),
            }
    except Exception as exc:
        log.warning("kick poll failed for %s: %s", slug, exc)
    return None


async def tiktok_status(_session: aiohttp.ClientSession, username: str) -> Optional[dict]:
    try:
        from TikTokLive import TikTokLiveClient  # type: ignore

        client = TikTokLiveClient(unique_id=f"@{username}")
        if await client.is_live():
            return {
                "title": "Live on TikTok",
                "viewer_count": 0,
                "thumbnail": None,
                "category": "TikTok Live",
                "url": platform_url("tiktok", username),
                "user_login": username,
            }
    except ImportError:
        return None
    except Exception as exc:
        log.warning("tiktok poll failed for %s: %s", username, exc)
    return None


class Streams(commands.Cog):
    """Twitch, Kick, and TikTok live alerts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.twitch = TwitchClient()
        self.session: Optional[aiohttp.ClientSession] = None
        self.poll_loop.start()

    async def cog_load(self):
        async with db.get() as c:
            await c.executescript(SCHEMA_SQL)
            await c.commit()
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.poll_loop.cancel()
        if self.session:
            asyncio.create_task(self.session.close())

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def poll_loop(self):
        if not self.session:
            return
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, guild_id, platform, channel_name, target_channel_id, "
                "mention_role_id, last_status FROM stream_subs"
            )
            rows = await cur.fetchall()
        for sub_id, guild_id, platform, name, target_channel_id, mention_role_id, last_status in rows:
            try:
                live = await self._check(platform, name)
            except Exception as exc:
                log.warning("stream poll failed for %s/%s: %s", platform, name, exc)
                continue
            if live and not last_status:
                await self._announce(guild_id, target_channel_id, mention_role_id, platform, live)
                async with db.get() as c:
                    await c.execute(
                        "UPDATE stream_subs SET last_status=1, last_event_at=? WHERE id=?",
                        (int(time.time()), sub_id),
                    )
                    await c.commit()
            elif not live and last_status:
                async with db.get() as c:
                    await c.execute(
                        "UPDATE stream_subs SET last_status=0, last_event_at=? WHERE id=?",
                        (int(time.time()), sub_id),
                    )
                    await c.commit()

    @poll_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    async def _check(self, platform: str, name: str) -> Optional[dict]:
        if platform == "twitch":
            stream = await self.twitch.is_live(self.session, name)
            if stream:
                return {
                    "title": stream.get("title", "Live"),
                    "viewer_count": stream.get("viewer_count", 0),
                    "thumbnail": stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720"),
                    "category": stream.get("game_name", "-"),
                    "url": platform_url("twitch", stream.get("user_login", name)),
                    "user_login": stream.get("user_login", name),
                }
            return None
        if platform == "kick":
            return await kick_status(self.session, name)
        if platform == "tiktok":
            return await tiktok_status(self.session, name)
        return None

    async def _announce(self, guild_id: int, channel_id: int, role_id: Optional[int], platform: str, live: dict):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        color = {"twitch": 0x9146FF, "kick": 0x53FC18, "tiktok": 0xFF0050}.get(platform, 0x5865F2)
        embed = discord.Embed(
            title=f"{live['user_login']} is live on {platform.title()}",
            description=f"**{live.get('title', 'Live')}**",
            url=live["url"],
            color=color,
        )
        embed.add_field(name="Category", value=live.get("category") or "-", inline=True)
        embed.add_field(name="Viewers", value=str(live.get("viewer_count", 0)), inline=True)
        if live.get("thumbnail"):
            embed.set_image(url=live["thumbnail"])
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=f"Watch on {platform.title()}",
                url=live["url"],
                style=discord.ButtonStyle.link,
            )
        )
        content = f"<@&{role_id}>" if role_id else None
        try:
            await safe_send(
                channel,
                content=content,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
                dedupe_key=f"stream:{guild_id}:{channel_id}:{platform}:{live['user_login']}:{live['url']}",
                dedupe_window=POLL_INTERVAL_SECONDS * 2,
            )
        except discord.Forbidden:
            log.warning("Missing permission to post stream alert in channel %s", channel_id)

    async def _sub_autocomplete(self, interaction: discord.Interaction, current: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, platform, channel_name FROM stream_subs WHERE guild_id=? ORDER BY platform, channel_name",
                (interaction.guild_id,),
            )
            rows = await cur.fetchall()
        choices = []
        for sub_id, platform, name in rows:
            label = f"#{sub_id} {platform}/{name}"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=sub_id))
            if len(choices) >= 25:
                break
        return choices

    @commands.hybrid_group(
        name="streams",
        invoke_without_command=True,
        description="Manage live-stream alert subscriptions",
    )
    @commands.has_permissions(manage_guild=True)
    async def streams(self, ctx):
        await ctx.send(
            embed=info(
                "Streams",
                "Use `/streams add`, `/streams remove`, `/streams list`, and `/streams test`.",
            )
        )

    @streams.command(name="add", description="Track a streamer for live alerts")
    @app_commands.describe(
        platform="Streaming service to track",
        name="Channel name or username on that platform",
        target="Channel where live alerts should be posted",
        ping="Optional role to mention when the alert fires",
    )
    @commands.has_permissions(manage_guild=True)
    async def streams_add(
        self,
        ctx,
        platform: Literal["twitch", "kick", "tiktok"],
        name: str,
        target: discord.TextChannel,
        ping: Optional[discord.Role] = None,
    ):
        cleaned_name = name.strip()
        if not cleaned_name:
            return await ctx.send(embed=err("Provide the streamer channel name or username to track."))
        async with db.get() as c:
            try:
                await c.execute(
                    "INSERT INTO stream_subs"
                    "(guild_id, platform, channel_name, target_channel_id, mention_role_id) VALUES(?,?,?,?,?)",
                    (ctx.guild.id, platform, cleaned_name, target.id, ping.id if ping else None),
                )
                await c.commit()
            except Exception as exc:
                return await ctx.send(embed=err(f"That stream is already tracked, or the database rejected it: {exc}"))
        message = f"Tracking **{platform}/{cleaned_name}** -> {target.mention}"
        if ping:
            message += f" and pinging {ping.mention}"
        if platform == "twitch" and not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
            message += (
                "\nWarning: Twitch credentials are still missing, so Twitch polls will not work "
                "until they are configured."
            )
            await ctx.send(embed=warn(message))
        else:
            await ctx.send(embed=ok(message))

    @streams.command(name="remove", description="Stop tracking a stream subscription")
    @app_commands.describe(sub_id="Tracked subscription ID to remove")
    @commands.has_permissions(manage_guild=True)
    async def streams_remove(self, ctx, sub_id: int):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM stream_subs WHERE id=? AND guild_id=?",
                (sub_id, ctx.guild.id),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(embed=ok(f"Removed subscription #{sub_id}."))
        else:
            await ctx.send(embed=err(f"No subscription with ID `{sub_id}` exists in this server."))

    @streams_remove.autocomplete("sub_id")
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._sub_autocomplete(interaction, current)

    @streams.command(name="list", description="List tracked stream subscriptions")
    @commands.has_permissions(manage_guild=True)
    async def streams_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT id, platform, channel_name, target_channel_id, mention_role_id, last_status "
                "FROM stream_subs WHERE guild_id=? ORDER BY platform, channel_name",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=info("Streams", "No streams are tracked yet."))
        embed = discord.Embed(title="Tracked streams", color=0x5865F2)
        for sub_id, platform, name, target, role, status in rows[:25]:
            state = "live" if status else "idle"
            value = f"Status: `{state}`\nTarget: <#{target}>"
            if role:
                value += f"\nPing: <@&{role}>"
            embed.add_field(name=f"#{sub_id} {platform}/{name}", value=value, inline=False)
        if len(rows) > 25:
            embed.set_footer(text=f"Showing 25 of {len(rows)} tracked stream subscriptions.")
        await ctx.send(embed=embed)

    @streams.command(name="test", description="Fire a test announcement for a tracked subscription")
    @app_commands.describe(sub_id="Tracked subscription ID to use for the test alert")
    @commands.has_permissions(manage_guild=True)
    async def streams_test(self, ctx, sub_id: int):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT guild_id, platform, channel_name, target_channel_id, mention_role_id "
                "FROM stream_subs WHERE id=? AND guild_id=?",
                (sub_id, ctx.guild.id),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(embed=err(f"No subscription with ID `{sub_id}` exists in this server."))
        guild_id, platform, name, target_channel_id, mention_role_id = row
        fake = {
            "title": f"[TEST] {name} stream",
            "viewer_count": 0,
            "thumbnail": None,
            "category": "Test",
            "url": platform_url(platform, name),
            "user_login": name,
        }
        await self._announce(guild_id, target_channel_id, mention_role_id, platform, fake)
        await ctx.send(embed=ok("Test alert sent."))

    @streams_test.autocomplete("sub_id")
    async def test_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._sub_autocomplete(interaction, current)


async def setup(bot):
    await bot.add_cog(Streams(bot))
