from __future__ import annotations

import asyncio
import logging
import os
import re

import discord
from discord.ext import commands

from utils.llm_client import discord_safe_chunks
from utils.unified_discord_router import (
    AutoDMGatewayClient,
    AutoDMGatewayError,
    IntegrationConfigError,
    autodm_channel_ids,
    autodm_enabled,
)

log = logging.getLogger("loki.autodm")


class AutoDMRouter(commands.Cog):
    """Route one configured Discord campaign surface through AutoDM and Mythos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._client: AutoDMGatewayClient | None = None
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}
        self._reported_config_error: str | None = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not autodm_enabled() or message.author.bot or not message.guild:
            return
        if self._addressed_to_loki(message) or self._looks_like_command(message):
            return
        try:
            if not self._channel_allowed(message.channel):
                return
            client = self._client_for_runtime()
        except IntegrationConfigError as exc:
            self._report_config_error_once(exc)
            return

        content = (message.clean_content or "").strip()
        if not content:
            return
        key = (message.channel.id, message.author.id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            try:
                result = await client.process_message(
                    channel_id=message.channel.id,
                    user_id=message.author.id,
                    display_name=message.author.display_name,
                    message_id=message.id,
                    content=content,
                )
            except (AutoDMGatewayError, IntegrationConfigError):
                log.exception(
                    "AutoDM route failed for channel=%s user=%s message=%s",
                    message.channel.id,
                    message.author.id,
                    message.id,
                )
                await message.reply(
                    "AutoDM is not ready right now. An operator can check the local campaign service.",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

        chunks = discord_safe_chunks(result.narrative)
        embed = discord.Embed(
            title=f"AutoDM · Mythos {result.route}",
            description=chunks[0],
            color=0xF6C244,
        )
        embed.set_footer(text="Campaign state is owned by AutoDM")
        await message.reply(
            embed=embed,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        for chunk in chunks[1:]:
            await message.reply(
                chunk,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    def _client_for_runtime(self) -> AutoDMGatewayClient:
        if self._client is None:
            self._client = AutoDMGatewayClient.from_env()
        return self._client

    def _channel_allowed(self, channel: discord.abc.Messageable) -> bool:
        configured = autodm_channel_ids()
        channel_ids = {getattr(channel, "id", None)}
        parent = getattr(channel, "parent", None)
        channel_ids.add(getattr(parent, "id", None))
        return bool(configured & {value for value in channel_ids if isinstance(value, int)})

    def _addressed_to_loki(self, message: discord.Message) -> bool:
        bot_user = self.bot.user
        if bot_user is not None and bot_user in getattr(message, "mentions", []):
            return True
        content = (message.clean_content or "").strip().casefold()
        return bool(re.match(r"^(hey|hi|yo|ok|okay)?\s*loki\b", content))

    @staticmethod
    def _looks_like_command(message: discord.Message) -> bool:
        prefix = os.getenv("PREFIX", "!")
        content = (message.content or "").lstrip()
        return bool(prefix and content.startswith(prefix))

    def _report_config_error_once(self, exc: IntegrationConfigError) -> None:
        detail = str(exc)
        if detail == self._reported_config_error:
            return
        self._reported_config_error = detail
        log.error("AutoDM routing disabled: %s", detail)


async def setup(bot):
    await bot.add_cog(AutoDMRouter(bot))
