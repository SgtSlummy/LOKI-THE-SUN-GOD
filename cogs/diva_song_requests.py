from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import discord
from discord.ext import commands, tasks

from utils.helpers import safe_send

log = logging.getLogger("loki.diva_song_requests")

TRUTHY = {"1", "true", "yes", "on"}
MANAGED_MARKER = "LOKI THE SUN GOD Diva song-request mirror"
DEFAULT_ENABLED = False
DEFAULT_GUILD_ID = 1463393482306486387
DEFAULT_CHANNEL_ID = 1499435617971343491
DEFAULT_AUTHOR_ID = 983091121569804359
DEFAULT_SOURCE_MESSAGE_ID = 1503116743793574009
DEFAULT_DASHBOARD_URL = "https://divabot.xyz/dashboard/1463393482306486387/song-requests"
DEFAULT_REFRESH_SECONDS = 30
DEFAULT_HISTORY_LIMIT = 100
MAX_CONTENT_LENGTH = 2000
MAX_EMBEDS = 10
HASH_LENGTH = 16
REQUIRED_CHANNEL_PERMISSIONS = (
    ("send_messages", "Send Messages"),
    ("embed_links", "Embed Links"),
    ("read_message_history", "Read Message History"),
    ("manage_messages", "Manage Messages"),
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        log.warning("Ignoring invalid integer for %s: %r", name, value)
        return default
    if parsed < minimum:
        log.warning("Ignoring %s=%s because it is below minimum %s", name, parsed, minimum)
        return default
    return parsed


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


LOOP_INTERVAL_SECONDS = _env_int(
    "DIVA_SONG_EMBED_REFRESH_SECONDS",
    DEFAULT_REFRESH_SECONDS,
    minimum=5,
)


@dataclass(frozen=True)
class DivaSongRequestsConfig:
    enabled: bool = DEFAULT_ENABLED
    guild_id: int = DEFAULT_GUILD_ID
    channel_id: int = DEFAULT_CHANNEL_ID
    author_id: int = DEFAULT_AUTHOR_ID
    source_message_id: int = DEFAULT_SOURCE_MESSAGE_ID
    managed_message_id: int = 0
    dashboard_url: str = DEFAULT_DASHBOARD_URL
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS
    history_limit: int = DEFAULT_HISTORY_LIMIT

    @classmethod
    def from_env(cls) -> DivaSongRequestsConfig:
        return cls(
            enabled=_env_bool("DIVA_SONG_EMBED_ENABLED", DEFAULT_ENABLED),
            guild_id=_env_int("DIVA_SONG_EMBED_GUILD_ID", DEFAULT_GUILD_ID, minimum=1),
            channel_id=_env_int("DIVA_SONG_EMBED_CHANNEL_ID", DEFAULT_CHANNEL_ID, minimum=1),
            author_id=_env_int("DIVA_SONG_EMBED_AUTHOR_ID", DEFAULT_AUTHOR_ID, minimum=1),
            source_message_id=_env_int(
                "DIVA_SONG_EMBED_SOURCE_MESSAGE_ID",
                DEFAULT_SOURCE_MESSAGE_ID,
                minimum=0,
            ),
            managed_message_id=_env_int("DIVA_SONG_EMBED_MANAGED_MESSAGE_ID", 0, minimum=0),
            dashboard_url=_env_str("DIVA_SONG_EMBED_DASHBOARD_URL", DEFAULT_DASHBOARD_URL),
            refresh_seconds=LOOP_INTERVAL_SECONDS,
            history_limit=_env_int("DIVA_SONG_EMBED_HISTORY_LIMIT", DEFAULT_HISTORY_LIMIT, minimum=10),
        )


def _int_matches(value: Any, expected: int) -> bool:
    if value is None:
        return False
    try:
        return int(value) == expected
    except (TypeError, ValueError):
        return False


def _message_id(message: Any) -> int | None:
    message_id = getattr(message, "id", None)
    try:
        return int(message_id) if message_id is not None else None
    except (TypeError, ValueError):
        return None


def _channel_id(message: Any) -> int | None:
    channel = getattr(message, "channel", None)
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        channel_id = getattr(message, "channel_id", None)
    try:
        return int(channel_id) if channel_id is not None else None
    except (TypeError, ValueError):
        return None


def _sender_ids(message: Any) -> Iterable[Any]:
    author = getattr(message, "author", None)
    yield getattr(author, "id", None)
    yield getattr(message, "application_id", None)
    yield getattr(message, "webhook_id", None)


def _created_at(message: Any) -> datetime:
    created_at = getattr(message, "created_at", None)
    if not isinstance(created_at, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def is_configured_source_message(message: Any, config: DivaSongRequestsConfig) -> bool:
    if not config.source_message_id:
        return False
    return _channel_id(message) == config.channel_id and _message_id(message) == config.source_message_id


def is_diva_source_message(message: Any, config: DivaSongRequestsConfig) -> bool:
    if _channel_id(message) != config.channel_id:
        return False
    if config.source_message_id:
        return is_configured_source_message(message, config)
    return any(_int_matches(sender_id, config.author_id) for sender_id in _sender_ids(message))


def select_diva_source_message(
    messages: Iterable[Any],
    config: DivaSongRequestsConfig,
) -> Any | None:
    candidates = [message for message in messages if is_diva_source_message(message, config)]
    candidates.sort(key=lambda message: (_created_at(message), _message_id(message) or 0), reverse=True)
    return candidates[0] if candidates else None


def _embed_to_jsonable(embed: Any) -> Any:
    if hasattr(embed, "to_dict"):
        return embed.to_dict()
    return str(embed)


def diva_source_fingerprint(source_message: Any) -> str:
    payload = {
        "content": str(getattr(source_message, "content", "") or ""),
        "embeds": [_embed_to_jsonable(embed) for embed in (getattr(source_message, "embeds", None) or [])],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:HASH_LENGTH]


def _content_with_limit(content: str | None) -> str | None:
    content = str(content or "").strip()
    if not content:
        return None
    if len(content) <= MAX_CONTENT_LENGTH:
        return content
    return content[: MAX_CONTENT_LENGTH - 3].rstrip() + "..."


def _clone_embed(embed: discord.Embed) -> discord.Embed:
    return discord.Embed.from_dict(embed.to_dict())


def build_diva_song_requests_payload(
    source_message: Any,
    config: DivaSongRequestsConfig,
) -> dict[str, Any]:
    source_embeds = list(getattr(source_message, "embeds", None) or [])
    return {
        "content": _content_with_limit(getattr(source_message, "content", "") or ""),
        "embeds": [_clone_embed(embed) for embed in source_embeds[:MAX_EMBEDS]],
        "allowed_mentions": discord.AllowedMentions.none(),
    }


def _footer_text(embed: Any) -> str:
    footer = getattr(embed, "footer", None)
    text = getattr(footer, "text", None)
    if text:
        return str(text)
    if hasattr(embed, "to_dict"):
        data = embed.to_dict()
        return str((data.get("footer") or {}).get("text") or "")
    return ""


def managed_message_fingerprint(message: Any) -> str | None:
    for embed in getattr(message, "embeds", None) or []:
        footer_text = _footer_text(embed)
        marker, separator, fingerprint = footer_text.partition(" | fp:")
        if separator and MANAGED_MARKER in marker:
            return fingerprint.strip() or None
    return None


def is_managed_dashboard_fallback_message(message: Any) -> bool:
    for embed in getattr(message, "embeds", None) or []:
        footer_text = _footer_text(embed)
        if MANAGED_MARKER in footer_text and "source:0" in footer_text:
            return True
    return False


def missing_diva_mirror_permissions(channel: Any, member: Any) -> list[str]:
    if channel is None or member is None or not hasattr(channel, "permissions_for"):
        return []
    permissions = channel.permissions_for(member)
    return [
        label
        for attr, label in REQUIRED_CHANNEL_PERMISSIONS
        if not bool(getattr(permissions, attr, False))
    ]


def is_managed_mirror_message(message: Any, bot_user_id: int | None = None) -> bool:
    if bot_user_id is not None:
        author_id = getattr(getattr(message, "author", None), "id", None)
        if not _int_matches(author_id, bot_user_id):
            return False
    return managed_message_fingerprint(message) is not None


class DivaSongRequestsMirror(commands.Cog):
    """Mirror the Wreckingball song-request message into one managed LOKI THE SUN GOD embed."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = DivaSongRequestsConfig.from_env()
        self._sync_lock = asyncio.Lock()
        if self.config.enabled:
            self.refresh_loop.start()
        else:
            log.info("Diva song-request mirror disabled")

    def cog_unload(self):
        self.refresh_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.config.enabled or not is_diva_source_message(message, self.config):
            return
        await self._sync_once(source_message=message, reason="new source message")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not self.config.enabled or not is_diva_source_message(after, self.config):
            return
        await self._sync_once(source_message=after, reason="source edit")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if not self.config.enabled or payload.channel_id != self.config.channel_id:
            return
        if self.config.source_message_id and payload.message_id != self.config.source_message_id:
            return
        channel = await self._resolve_channel()
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        if is_diva_source_message(message, self.config):
            await self._sync_once(source_message=message, reason="raw source edit")

    @tasks.loop(seconds=LOOP_INTERVAL_SECONDS)
    async def refresh_loop(self):
        await self._sync_once(reason="scheduled refresh")

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        await self.bot.wait_until_ready()
        await self._log_channel_permission_status()

    async def _resolve_channel(self) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(self.config.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.config.channel_id)
            except discord.HTTPException as exc:
                log.warning("Could not fetch Diva song-request channel %s: %s", self.config.channel_id, exc)
                return None
        if not hasattr(channel, "history"):
            log.warning("Diva song-request channel %s does not expose message history", self.config.channel_id)
            return None
        return channel

    async def _history(self, channel: Any) -> list[discord.Message]:
        try:
            return [message async for message in channel.history(limit=self.config.history_limit)]
        except discord.Forbidden:
            log.warning(
                "Missing Read Message History permission for Diva song-request channel %s",
                self.config.channel_id,
            )
        except discord.HTTPException as exc:
            log.warning("Could not read Diva song-request channel %s history: %s", self.config.channel_id, exc)
        return []

    async def _fetch_seed_source(self, channel: Any) -> discord.Message | None:
        if not self.config.source_message_id or not hasattr(channel, "fetch_message"):
            return None
        try:
            message = await channel.fetch_message(self.config.source_message_id)
        except discord.NotFound:
            return None
        except discord.Forbidden:
            log.warning(
                "Missing Read Message History permission for Diva source message %s",
                self.config.source_message_id,
            )
            return None
        except discord.HTTPException as exc:
            log.warning("Could not fetch Diva source message %s: %s", self.config.source_message_id, exc)
            return None
        return message if is_diva_source_message(message, self.config) else None

    def _bot_user_id(self) -> int | None:
        user_id = getattr(getattr(self.bot, "user", None), "id", None)
        try:
            return int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            return None

    async def _log_channel_permission_status(self) -> None:
        channel = await self._resolve_channel()
        if channel is None:
            return
        guild = getattr(channel, "guild", None)
        member = getattr(guild, "me", None)
        bot_user_id = self._bot_user_id()
        if member is None and bot_user_id is not None and hasattr(guild, "get_member"):
            member = guild.get_member(bot_user_id)
        if member is None:
            log.warning("Could not inspect Diva mirror permissions for channel %s", self.config.channel_id)
            return

        missing = missing_diva_mirror_permissions(channel, member)
        if missing:
            log.warning(
                "Diva mirror channel %s missing permission(s): %s",
                self.config.channel_id,
                ", ".join(missing),
            )
            return
        log.info("Diva mirror channel %s permissions look ready", self.config.channel_id)

    async def _find_managed_message(self, channel: Any, messages: list[discord.Message]) -> discord.Message | None:
        bot_user_id = self._bot_user_id()
        if self.config.managed_message_id and hasattr(channel, "fetch_message"):
            try:
                message = await channel.fetch_message(self.config.managed_message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None
            if message is not None and (
                bot_user_id is None or _int_matches(getattr(getattr(message, "author", None), "id", None), bot_user_id)
            ):
                return message
        for message in messages:
            if is_managed_mirror_message(message, bot_user_id):
                return message
        return None

    async def _sync_once(
        self,
        *,
        source_message: discord.Message | None = None,
        reason: str,
    ) -> None:
        if not self.config.enabled or self._sync_lock.locked():
            return
        async with self._sync_lock:
            channel = await self._resolve_channel()
            if channel is None:
                return
            messages = await self._history(channel)
            managed_message = await self._find_managed_message(channel, messages)
            source_message = source_message or select_diva_source_message(messages, self.config)
            if source_message is None:
                source_message = await self._fetch_seed_source(channel)
            if source_message is None:
                if managed_message is not None:
                    if is_managed_dashboard_fallback_message(managed_message) and hasattr(managed_message, "delete"):
                        try:
                            await managed_message.delete()
                        except discord.Forbidden:
                            log.warning(
                                "Missing permission to delete stale Diva fallback message %s",
                                managed_message.id,
                            )
                        except discord.HTTPException as exc:
                            log.warning("Could not delete stale Diva fallback message %s: %s", managed_message.id, exc)
                        else:
                            log.info("Deleted stale Diva fallback message %s via %s", managed_message.id, reason)
                        return
                    log.info(
                        "No Diva source message %s found for channel %s during %s; keeping existing mirror",
                        self.config.source_message_id,
                        self.config.channel_id,
                        reason,
                    )
                    return
                log.info(
                    "No Diva source message %s found for channel %s during %s; not posting mirror",
                    self.config.source_message_id,
                    self.config.channel_id,
                    reason,
                )
                return
            payload = build_diva_song_requests_payload(source_message, self.config)
            fingerprint = diva_source_fingerprint(source_message)
            if managed_message is not None:
                if diva_source_fingerprint(managed_message) == fingerprint:
                    return
                try:
                    await managed_message.edit(**payload)
                except discord.Forbidden:
                    log.warning("Missing permission to edit Diva mirror message %s", managed_message.id)
                except discord.HTTPException as exc:
                    log.warning("Could not edit Diva mirror message %s: %s", managed_message.id, exc)
                else:
                    log.info("Updated Diva song-request mirror message %s via %s", managed_message.id, reason)
                return

            try:
                sent = await safe_send(
                    channel,
                    dedupe_key=f"diva-song-requests-mirror:{self.config.channel_id}",
                    dedupe_window=60,
                    dedupe_required=True,
                    **payload,
                )
            except discord.Forbidden:
                log.warning(
                    "Missing Send Messages or Embed Links permission for Diva mirror channel %s",
                    self.config.channel_id,
                )
                return
            except discord.HTTPException as exc:
                log.warning("Could not send Diva mirror message to channel %s: %s", self.config.channel_id, exc)
                return
            if sent is not None:
                log.info("Posted Diva song-request mirror message %s via %s", sent.id, reason)


async def setup(bot: commands.Bot):
    await bot.add_cog(DivaSongRequestsMirror(bot))
