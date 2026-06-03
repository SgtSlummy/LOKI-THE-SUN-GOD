from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import asdict
from datetime import timezone
from typing import Any

import discord
from discord.ext import commands

from bot.models.media import MediaItem, MediaKind
from bot.models.relay import RelayMessage, RelayRoute
from bot.plugins.base import BasePlugin, PluginSlot
from bot.plugins.relay_core.formatting import (
    build_media_link_view,
    build_relay_content,
    image_links_to_embeds,
    media_cards_to_embeds,
    safe_allowed_mentions,
)
from bot.services.database import Database
from bot.services.media_resolver import MAX_DISCORD_UPLOAD_BYTES, MediaResolver
from bot.settings import Settings


class RelayCircuitBreaker:
    def __init__(self, *, threshold: int, window_seconds: int):
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.failures: deque[float] = deque()

    def record_failure(self) -> None:
        now = time.monotonic()
        self.failures.append(now)
        self._trim(now)

    def record_success(self) -> None:
        self._trim(time.monotonic())

    def is_open(self) -> bool:
        now = time.monotonic()
        self._trim(now)
        return len(self.failures) >= self.threshold

    def _trim(self, now: float) -> None:
        while self.failures and now - self.failures[0] > self.window_seconds:
            self.failures.popleft()


class RelayCoreCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        settings: Settings,
        database: Database,
        media_resolver: MediaResolver,
        logger: logging.Logger,
    ):
        self.bot = bot
        self.settings = settings
        self.database = database
        self.media_resolver = media_resolver
        self.logger = logger
        self.breaker = RelayCircuitBreaker(
            threshold=settings.relay_error_threshold,
            window_seconds=settings.relay_error_window_seconds,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot and not self.settings.allow_bot_relay:
            return
        if await self.database.is_relayed_message(message.id, message.channel.id):
            return
        if self.breaker.is_open():
            self.logger.warning("Relay circuit breaker is open; skipping message %s", message.id)
            return

        routes = await self.database.routes_for_source(message.guild.id, message.channel.id)
        if not routes:
            return

        relay_message = await self._normalize_message(message)
        for route in routes:
            if await self.database.is_source_message_mapped(message.id, message.channel.id, route.id):
                continue
            await self._relay_to_route(message, relay_message, route)

    async def _normalize_message(self, message: discord.Message) -> RelayMessage:
        resolution = await self.media_resolver.resolve(
            content=message.content,
            embeds=list(message.embeds),
            attachments=list(message.attachments),
            stickers=list(message.stickers),
            user_mentions={str(user.id): user.display_name for user in message.mentions},
            role_mentions={str(role.id): role.name for role in message.role_mentions},
            channel_mentions={str(channel.id): channel.name for channel in message.channel_mentions},
        )
        avatar_url = None
        if getattr(message.author, "display_avatar", None) is not None:
            avatar_url = str(message.author.display_avatar.url)
        return RelayMessage(
            source_guild_id=message.guild.id,
            source_channel_id=message.channel.id,
            source_channel_name=getattr(message.channel, "name", str(message.channel.id)),
            source_message_id=message.id,
            source_message_url=message.jump_url,
            author_user_id=message.author.id,
            author_display_name=getattr(message.author, "display_name", message.author.name),
            author_avatar_url=avatar_url,
            clean_text=resolution.clean_text,
            attachments=list(message.attachments),
            embeds=list(message.embeds),
            stickers=list(message.stickers),
            detected_links=resolution.detected_links,
            media_items=resolution.media_items,
            created_at=message.created_at.astimezone(timezone.utc),
        )

    async def _relay_to_route(
        self,
        source_message: discord.Message,
        relay_message: RelayMessage,
        route: RelayRoute,
    ) -> None:
        destination = self.bot.get_channel(route.destination_channel_id)
        if destination is None:
            destination = await self.bot.fetch_channel(route.destination_channel_id)
        if not isinstance(destination, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await self.database.audit(
                event_type="relay_destination_invalid",
                guild_id=route.guild_id,
                channel_id=route.destination_channel_id,
                message_id=relay_message.source_message_id,
                details={"route_id": route.id},
            )
            return

        try:
            sent = await self._send_relay(destination, source_message, relay_message)
            await self.database.record_message_map(
                source_message_id=relay_message.source_message_id,
                source_channel_id=relay_message.source_channel_id,
                destination_message_id=sent.id,
                destination_channel_id=route.destination_channel_id,
                route_id=route.id,
            )
            await self.database.audit(
                event_type="relay_message_sent",
                actor_id=relay_message.author_user_id,
                guild_id=route.guild_id,
                channel_id=route.destination_channel_id,
                message_id=sent.id,
                details={
                    "route_id": route.id,
                    "source_message_id": relay_message.source_message_id,
                    "source_channel_id": relay_message.source_channel_id,
                    "media_items": [asdict(item) for item in relay_message.media_items],
                },
            )
            self.breaker.record_success()
        except Exception as exc:
            self.breaker.record_failure()
            self.logger.exception("Relay failed for route %s", route.id)
            await self.database.audit(
                event_type="relay_message_failed",
                actor_id=relay_message.author_user_id,
                guild_id=route.guild_id,
                channel_id=route.destination_channel_id,
                message_id=relay_message.source_message_id,
                details={"route_id": route.id, "error": str(exc)},
            )

    async def _send_relay(
        self,
        destination: discord.abc.Messageable,
        source_message: discord.Message,
        relay_message: RelayMessage,
    ) -> discord.Message:
        content = build_relay_content(relay_message, settings=self.settings)
        files = await self._files_from_attachments(source_message.attachments)
        embeds = media_cards_to_embeds(relay_message.media_items)
        embeds.extend(image_links_to_embeds(relay_message.media_items))
        view = build_media_link_view(
            relay_message.media_items,
            enabled=self.settings.media_link_buttons or self.settings.media_mode == "button",
        )

        if self.settings.webhook_relay_mode and isinstance(destination, discord.TextChannel):
            webhook = await self._get_or_create_webhook(destination)
            if webhook is not None:
                return await webhook.send(
                    content=relay_message.clean_text or None,
                    username=f"{relay_message.author_display_name} - #{relay_message.source_channel_name}",
                    avatar_url=relay_message.author_avatar_url,
                    files=files or None,
                    embeds=embeds or None,
                    allowed_mentions=safe_allowed_mentions(),
                    view=view,
                    wait=True,
                )

        return await destination.send(
            content=content,
            files=files or None,
            embeds=embeds or None,
            allowed_mentions=safe_allowed_mentions(),
            view=view,
            suppress_embeds=self.settings.media_mode != "native_unfurl",
        )

    async def _files_from_attachments(self, attachments: list[discord.Attachment]) -> list[discord.File]:
        files: list[discord.File] = []
        total_size = 0
        for attachment in attachments:
            size = getattr(attachment, "size", 0) or 0
            if size > MAX_DISCORD_UPLOAD_BYTES or total_size + size > MAX_DISCORD_UPLOAD_BYTES:
                continue
            try:
                files.append(await attachment.to_file(use_cached=True))
                total_size += size
            except discord.HTTPException:
                self.logger.warning("Could not re-upload attachment %s", getattr(attachment, "id", "unknown"))
        return files

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        try:
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                if webhook.name == "Loki Relay" and webhook.user == self.bot.user:
                    return webhook
            return await channel.create_webhook(name="Loki Relay", reason="Relay webhook mode")
        except discord.Forbidden:
            self.logger.warning("Missing webhook permissions for channel %s; falling back to bot mode", channel.id)
            return None


class RelayCorePlugin(BasePlugin):
    name = "relay_core"
    slot = PluginSlot.RELAY_CORE
    version = "0.1.0"
    enabled_by_default = True
    dependencies = ["media_resolver", "moderation_audit"]
    config_schema = {
        "webhook_relay_mode": {"type": "boolean"},
        "allow_bot_relay": {"type": "boolean"},
    }

    def __init__(self):
        self.cog: RelayCoreCog | None = None

    async def setup(self, bot: commands.Bot, services: dict[str, Any]) -> None:
        self.cog = RelayCoreCog(
            bot,
            settings=services["settings"],
            database=services["database"],
            media_resolver=services["media_resolver"],
            logger=logging.getLogger("loki.relay"),
        )
        await bot.add_cog(self.cog)

    async def teardown(self) -> None:
        self.cog = None

    async def healthcheck(self) -> dict[str, Any]:
        return {
            "ok": True,
            "plugin": self.name,
            "slot": self.slot.value,
            "circuit_open": self.cog.breaker.is_open() if self.cog else False,
        }

    def event_subscriptions(self) -> list[str]:
        return ["on_message"]

