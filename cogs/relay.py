import logging
import os
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

from utils import runtime_paths
from utils.helpers import safe_send
from utils.link_previews import (
    LinkPreview,
    extract_music_artists,
    extract_urls,
    is_safe_preview_url,
    resolve_link_previews,
    strip_urls,
)

log = logging.getLogger("loki.relay")
relay_log = logging.getLogger("loki.relay.trace")

if not relay_log.handlers:
    relay_log.setLevel(logging.INFO)
    trace_path = runtime_paths.app_path("data", "relay.log")
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(trace_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    relay_log.addHandler(handler)
    relay_log.propagate = False


RelayChannel = discord.TextChannel | discord.VoiceChannel | discord.StageChannel
SourceChannel = discord.abc.GuildChannel | discord.Thread
MAX_BACKFILL_LIMIT = 100
MAX_PREVIEW_DOWNLOAD_BYTES = 8 * 1024 * 1024
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")
CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]{1,32}:\d+>")


@dataclass
class RelayBackfillResult:
    scanned: int = 0
    relays_sent: int = 0
    failed_sources: int = 0


@dataclass
class RelayRepairResult:
    scanned: int = 0
    repaired: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(frozen=True)
class PreviewFileSpec:
    source_url: str
    filename: str
    content: bytes


def _csv_values(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _csv_ints(raw: str | None) -> list[int]:
    values: list[int] = []
    for part in _csv_values(raw):
        if part.isdigit():
            values.append(int(part))
        else:
            log.warning("Ignoring non-numeric relay channel id: %s", part)
    return values


class Relay(commands.Cog):
    """Relay Friends-role messages between configured channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = os.getenv("RELAY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        self.guild_id = int(os.getenv("RELAY_GUILD_ID") or os.getenv("TEST_GUILD_ID") or "0")
        self.friends_role_name = os.getenv("RELAY_FRIENDS_ROLE_NAME", "Friends")
        self.target_channel_ids = _csv_ints(os.getenv("RELAY_TARGET_CHANNEL_IDS"))
        self.target_channel_names = _csv_values(os.getenv("RELAY_TARGET_CHANNEL_NAMES"))
        self.ignored_source_ids = set(_csv_values(os.getenv("RELAY_IGNORED_SOURCE_CHANNEL_IDS")))
        self.sensitive_source_ids = set(_csv_values(os.getenv("RELAY_SENSITIVE_CHANNEL_IDS")))

        self.target_channels: dict[int, RelayChannel] = {}
        self.friends_role_id: int | None = None
        self._recent_message_ids: dict[int, float] = {}
        self._inflight_message_ids: set[int] = set()

    async def cog_load(self):
        if self.enabled:
            relay_log.info("relay cog loaded; waiting for on_ready")
        else:
            relay_log.info("relay cog loaded disabled")

    @commands.hybrid_group(
        name="relay",
        invoke_without_command=True,
        description="Inspect LOKI THE SUN GOD's channel relay",
    )
    @commands.has_permissions(manage_guild=True)
    async def relay(self, ctx):
        await self.relay_status(ctx)

    @relay.command(name="status", description="Show LOKI THE SUN GOD's channel relay status")
    @commands.has_permissions(manage_guild=True)
    async def relay_status(self, ctx):
        embed = discord.Embed(title="LOKI THE SUN GOD Relay", color=0x5865F2)
        embed.add_field(name="Enabled", value="yes" if self.enabled else "no", inline=True)
        embed.add_field(name="Guild", value=str(self.guild_id or "not set"), inline=True)
        embed.add_field(
            name="Friends role",
            value=str(self.friends_role_id or f"not resolved ({self.friends_role_name})"),
            inline=True,
        )

        if self.target_channels:
            targets = "\n".join(
                f"{channel.mention if hasattr(channel, 'mention') else channel.name} (`{channel.id}`)"
                for channel in self.target_channels.values()
            )
        else:
            targets = "No target channels resolved."
        embed.add_field(name="Targets", value=targets[:1024], inline=False)
        embed.add_field(
            name="Ignored sources",
            value=", ".join(sorted(self.ignored_source_ids)) or "none",
            inline=False,
        )
        embed.add_field(
            name="Sensitive sources",
            value=", ".join(sorted(self.sensitive_source_ids)) or "none",
            inline=False,
        )
        await ctx.send(embed=embed)

    @relay.command(name="reload", description="Reload relay roles and channels")
    @commands.has_permissions(manage_guild=True)
    async def relay_reload(self, ctx):
        await self._refresh_state()
        await ctx.send("LOKI THE SUN GOD relay configuration reloaded.")

    @relay.command(name="backfill", description="Relay recent message history from configured relay channels")
    @commands.has_permissions(manage_guild=True)
    async def relay_backfill(self, ctx, channel: discord.TextChannel = None, limit: int = 25):
        if not self.enabled:
            return await ctx.send("LOKI THE SUN GOD relay is disabled.")

        await self._refresh_state()
        sources = self._backfill_sources(channel)
        if not sources:
            return await ctx.send("No configured relay source channels matched that request.")

        bounded_limit = max(1, min(int(limit or 25), MAX_BACKFILL_LIMIT))
        skip_message_id = getattr(getattr(ctx, "message", None), "id", None)
        result = await self._backfill_history(sources, limit=bounded_limit, skip_message_id=skip_message_id)
        summary = (
            "Relay backfill scanned "
            f"{result.scanned} message(s), sent {result.relays_sent} relay post(s)"
        )
        if result.failed_sources:
            summary += f", skipped {result.failed_sources} source channel(s) after read errors."
        else:
            summary += "."
        await ctx.send(summary)

    @relay.command(name="repair_gifs", description="Repair old relay GIF posts that rendered without media")
    @commands.has_permissions(manage_guild=True)
    async def relay_repair_gifs(self, ctx, channel: discord.TextChannel = None, limit: int = 100):
        if not self.enabled:
            return await ctx.send("LOKI THE SUN GOD relay is disabled.")

        await self._refresh_state()
        targets = self._repair_targets(channel)
        if not targets:
            return await ctx.send("No configured relay target channels matched that request.")

        bounded_limit = max(1, min(int(limit or 100), MAX_BACKFILL_LIMIT))
        result = await self._repair_broken_gif_relays(targets, limit=bounded_limit)
        await ctx.send(
            "Relay GIF repair scanned "
            f"{result.scanned} message(s), repaired {result.repaired}, "
            f"skipped {result.skipped}, failed {result.failed}."
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self._refresh_state()
        except Exception:
            log.exception("Relay on_ready failed")
            relay_log.exception("Relay on_ready failed")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if self.enabled and channel.guild.id == self.guild_id:
            await self._refresh_state()

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if self.enabled and after.guild.id == self.guild_id:
            await self._refresh_state()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if self.enabled and after.guild.id == self.guild_id and after.name == self.friends_role_name:
            self.friends_role_id = after.id

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.enabled:
            await self._handle_message(message)

    async def _refresh_state(self):
        self.target_channels.clear()

        if not self.enabled:
            relay_log.info("relay disabled")
            return
        if not self.guild_id:
            log.warning("Relay enabled but RELAY_GUILD_ID/TEST_GUILD_ID is missing")
            relay_log.info("relay missing guild id")
            return

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.guild_id)
            except discord.HTTPException as exc:
                log.warning("Relay guild %s is unavailable: %s", self.guild_id, exc)
                return

        try:
            await guild.fetch_roles()
        except discord.HTTPException as exc:
            log.warning("Relay could not fetch roles: %s", exc)

        self._resolve_role(guild)
        await self._resolve_targets(guild)
        resolved_targets = self._channel_list(self.target_channels.values())

        log.info(
            "Relay ready guild=%s role=%s targets=%s",
            guild.id,
            self.friends_role_id,
            resolved_targets or "none",
        )
        relay_log.info(
            "ready guild=%s role=%s targets=%s configured_ids=%s configured_names=%s ignored=%s",
            guild.id,
            self.friends_role_id,
            resolved_targets or "none",
            ",".join(str(channel_id) for channel_id in self.target_channel_ids) or "<none>",
            ",".join(self.target_channel_names) or "<none>",
            ",".join(sorted(self.ignored_source_ids)) or "<none>",
        )

    def _resolve_role(self, guild: discord.Guild):
        role = discord.utils.get(guild.roles, name=self.friends_role_name)
        self.friends_role_id = role.id if role else None
        if not self.friends_role_id:
            log.warning("Relay role not found: %s", self.friends_role_name)

    async def _resolve_targets(self, guild: discord.Guild):
        for channel_id in self.target_channel_ids:
            channel = guild.get_channel(channel_id)
            if channel is None:
                try:
                    fetched = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException as exc:
                    log.warning("Relay target channel fetch failed for %s: %s", channel_id, exc)
                    relay_log.info("target fetch failed id=%s error=%s", channel_id, exc)
                    continue
                channel = fetched if isinstance(fetched, discord.abc.GuildChannel) else None
            if (
                channel is not None
                and getattr(channel.guild, "id", None) == guild.id
                and self._is_relay_channel(channel)
            ):
                if self._is_sensitive_source(channel, guild):
                    log.warning("Relay target is sensitive and will not be used: %s", channel_id)
                    relay_log.info("target sensitive skipped id=%s", channel_id)
                    continue
                self.target_channels[channel.id] = channel
                relay_log.info("target resolved %s(%s)", channel.name, channel.id)
            else:
                log.warning("Relay target channel not found or unsupported: %s", channel_id)
                relay_log.info("target unsupported id=%s type=%s", channel_id, type(channel).__name__)

        for name in self.target_channel_names:
            channel = discord.utils.get(guild.channels, name=name)
            if channel is not None and self._is_relay_channel(channel):
                if self._is_sensitive_source(channel, guild):
                    log.warning("Relay target is sensitive and will not be used: %s", name)
                    relay_log.info("target sensitive skipped name=%s id=%s", name, channel.id)
                    continue
                self.target_channels[channel.id] = channel
                relay_log.info("target resolved %s(%s)", channel.name, channel.id)
            else:
                log.warning("Relay target channel not found by name: %s", name)
                relay_log.info("target name unresolved name=%s", name)

    async def _handle_message(self, message: discord.Message) -> int:
        reserved_message_id = False
        try:
            if not message.guild or message.guild.id != self.guild_id:
                return 0

            channel_id = getattr(message.channel, "id", None)
            channel_name = getattr(message.channel, "name", "<unknown>")
            self._prune_recent_message_ids()
            relay_log.info(
                "message id=%s channel=%s(%s) author=%s bot=%s content_len=%s attachments=%s",
                message.id,
                channel_name,
                channel_id,
                message.author,
                message.author.bot,
                len(message.content or ""),
                len(message.attachments),
            )

            if message.author.bot:
                relay_log.info("skip bot author")
                return 0
            if message.id in self._inflight_message_ids or message.id in self._recent_message_ids:
                relay_log.info("skip duplicate message id")
                return 0

            self._inflight_message_ids.add(message.id)
            reserved_message_id = True

            if not self.friends_role_id:
                relay_log.info("skip missing friends role")
                return 0
            if str(channel_id) in self.ignored_source_ids:
                relay_log.info("skip ignored source channel")
                return 0
            if self._is_sensitive_source(message.channel, message.guild):
                relay_log.info("skip sensitive source channel")
                return 0
            destinations = [channel for target_id, channel in self.target_channels.items() if target_id != channel_id]
            if not destinations:
                relay_log.info("skip no destinations for source=%s", channel_id)
                return 0
            relay_log.info(
                "destinations for source=%s(%s): %s",
                channel_name,
                channel_id,
                self._channel_list(destinations),
            )
            if not self._friends_can_view_source(message.channel, message.guild):
                relay_log.info("skip Friends role cannot view source channel")
                return 0

            member = message.author if isinstance(message.author, discord.Member) else None
            if member is None:
                try:
                    member = await message.guild.fetch_member(message.author.id)
                except discord.HTTPException as exc:
                    relay_log.info("skip member fetch failed: %s", exc)
                    return 0
            if self.friends_role_id not in {role.id for role in member.roles}:
                relay_log.info("skip author lacks Friends role")
                return 0

            author_name = f"{member.display_name} in #{channel_name}"
            avatar_url = member.display_avatar.url
            body = message.content.strip() if message.content else None
            attachment = message.attachments[0] if message.attachments else None
            attachment_type = (attachment.content_type or "") if attachment is not None else ""

            self._recent_message_ids[message.id] = time.time()

            return await self._send_message_to_targets(
                destinations=destinations,
                message=message,
                author_name=author_name,
                avatar_url=avatar_url,
                body=body,
                attachment=attachment,
                attachment_type=attachment_type,
            )
        except Exception:
            log.exception("Relay handler crashed")
            relay_log.exception("Relay handler crashed")
            return 0
        finally:
            if reserved_message_id:
                self._inflight_message_ids.discard(message.id)

    async def _backfill_history(
        self,
        source_channels: list[RelayChannel],
        *,
        limit: int,
        skip_message_id: int | None = None,
    ) -> RelayBackfillResult:
        result = RelayBackfillResult()
        bounded_limit = max(1, min(int(limit or 25), MAX_BACKFILL_LIMIT))
        for channel in source_channels:
            if not hasattr(channel, "history"):
                result.failed_sources += 1
                continue
            try:
                async for message in channel.history(limit=bounded_limit, oldest_first=True):
                    if skip_message_id is not None and message.id == skip_message_id:
                        continue
                    result.scanned += 1
                    result.relays_sent += await self._handle_message(message)
            except discord.HTTPException as exc:
                result.failed_sources += 1
                relay_log.info("backfill history read failed for %s(%s): %s", channel.name, channel.id, exc)
        return result

    def _backfill_sources(self, channel: discord.TextChannel | None) -> list[RelayChannel]:
        if channel is not None:
            source = self.target_channels.get(channel.id)
            if source is None or self._is_sensitive_source(source, source.guild):
                return []
            return [source]
        return [
            source
            for source in self.target_channels.values()
            if not self._is_sensitive_source(source, source.guild)
        ]

    def _repair_targets(self, channel: discord.TextChannel | None) -> list[RelayChannel]:
        if channel is not None:
            target = self.target_channels.get(channel.id)
            return [target] if target is not None else []
        return list(self.target_channels.values())

    async def _send_message_to_targets(
        self,
        *,
        destinations: list[RelayChannel],
        message: discord.Message,
        author_name: str,
        avatar_url: str,
        body: str | None,
        attachment: discord.Attachment | None,
        attachment_type: str,
        ignore_existing_source_message_id: int | None = None,
    ):
        is_image = attachment_type.startswith("image/") and "gif" not in attachment_type
        is_file_gif_or_video = attachment_type.startswith("video/") or attachment_type == "image/gif"
        urls = extract_urls(body)
        cleaned_body = self._clean_relay_body(body, message)
        emoji_image_url = self._custom_emoji_image_url(cleaned_body)
        link_previews = await resolve_link_previews(urls)
        source_embed_previews = self._source_embed_previews(message)
        merged_previews = self._merge_previews(link_previews, source_embed_previews)
        preview_embeds = self._preview_embeds(merged_previews)
        preview_file = await self._preview_file_spec(merged_previews, preview_embeds)
        source_marker = self._source_marker(message)
        source_markers = (
            source_marker,
            self._legacy_source_marker(message.guild.id, message.id),
        )

        sent_count = 0
        for channel in destinations:
            try:
                if await self._destination_already_has_source(
                    channel,
                    source_markers,
                    ignore_message_id=ignore_existing_source_message_id,
                ):
                    relay_log.info("skip existing source relay to %s(%s)", channel.name, channel.id)
                    continue

                dedupe_key = f"relay:{message.guild.id}:{message.id}:{channel.id}"
                dedupe_target_id = f"relay-channel:{channel.id}"
                sent = None
                context_embed = self._context_embed(
                    author_name=author_name,
                    avatar_url=avatar_url,
                    body=cleaned_body,
                    source_marker=source_marker,
                )
                if is_file_gif_or_video and attachment is not None:
                    file = await attachment.to_file()
                    sent = await safe_send(
                        channel,
                        embeds=[context_embed, *preview_embeds],
                        file=file,
                        allowed_mentions=discord.AllowedMentions.none(),
                        dedupe_key=dedupe_key,
                        dedupe_window=600,
                        dedupe_target_id=dedupe_target_id,
                        dedupe_required=True,
                    )
                else:
                    if is_image and attachment is not None:
                        context_embed.set_image(url=attachment.url)
                    elif emoji_image_url:
                        context_embed.set_image(url=emoji_image_url)
                    file = self._discord_file(preview_file) if preview_file is not None else None
                    sent = await safe_send(
                        channel,
                        embeds=[context_embed, *preview_embeds],
                        file=file,
                        allowed_mentions=discord.AllowedMentions.none(),
                        dedupe_key=dedupe_key,
                        dedupe_window=600,
                        dedupe_target_id=dedupe_target_id,
                        dedupe_required=True,
                    )
                if sent is None:
                    relay_log.info("suppressed duplicate relay to %s(%s)", channel.name, channel.id)
                else:
                    sent_count += 1
                    relay_log.info("relayed message to %s(%s)", channel.name, channel.id)
            except discord.HTTPException as exc:
                log.warning("Relay send failed for #%s: %s", channel.name, exc)
                relay_log.info("send failed to %s(%s): %s", channel.name, channel.id, exc)
        return sent_count

    async def _destination_already_has_source(
        self,
        channel: RelayChannel,
        source_markers: tuple[str, ...],
        *,
        ignore_message_id: int | None = None,
    ) -> bool:
        if not hasattr(channel, "history"):
            return False
        try:
            async for existing in channel.history(limit=12):
                if ignore_message_id is not None and getattr(existing, "id", None) == ignore_message_id:
                    continue
                if self._message_mentions_source(existing, source_markers):
                    return True
        except discord.HTTPException as exc:
            relay_log.info("source history check failed for %s(%s): %s", channel.name, channel.id, exc)
        except Exception:
            relay_log.exception("source history check crashed for %s(%s)", channel.name, channel.id)
        return False

    async def _repair_broken_gif_relays(
        self,
        target_channels: list[RelayChannel],
        *,
        limit: int,
    ) -> RelayRepairResult:
        result = RelayRepairResult()
        for channel in target_channels:
            if not hasattr(channel, "history"):
                result.failed += 1
                continue
            try:
                async for message in channel.history(limit=limit):
                    result.scanned += 1
                    repaired = await self._repair_broken_gif_message(channel, message)
                    if repaired is True:
                        result.repaired += 1
                    elif repaired is False:
                        result.skipped += 1
                    else:
                        result.failed += 1
            except discord.HTTPException as exc:
                result.failed += 1
                relay_log.info("repair history read failed for %s(%s): %s", channel.name, channel.id, exc)
        return result

    async def _repair_broken_gif_message(
        self,
        destination: RelayChannel,
        relay_message: discord.Message,
    ) -> bool | None:
        if not self._is_broken_tenor_relay_message(relay_message):
            return False
        if (
            self._relay_source_marker_from_message(relay_message) is not None
            and not self._is_message_from_this_bot(relay_message)
        ):
            relay_log.info("repair skipped relay message %s not authored by this bot", relay_message.id)
            return False

        marker = self._relay_source_marker_from_message(relay_message)
        if marker is not None:
            source_parts = self._source_message_ids_from_marker(marker)
            if source_parts is None or not self._repair_marker_allowed(source_parts[0], source_parts[1], destination):
                relay_log.info("repair skipped relay message %s with disallowed source marker", relay_message.id)
                return False

        source_message = await self._source_message_from_relay(relay_message, destination=destination)
        if source_message is None:
            return await self._repair_legacy_tenor_message(destination, relay_message)

        if not self._repair_source_allowed(source_message, destination):
            relay_log.info("repair skipped source %s after relay policy recheck", source_message.id)
            return False

        member = source_message.author if isinstance(source_message.author, discord.Member) else None
        if member is None:
            try:
                member = await source_message.guild.fetch_member(source_message.author.id)
            except discord.HTTPException as exc:
                relay_log.info("repair member fetch failed for source %s: %s", source_message.id, exc)
                return None
        if self.friends_role_id not in {role.id for role in member.roles}:
            relay_log.info("repair skipped source %s author lacks Friends role", source_message.id)
            return False
        author_name = f"{member.display_name} in #{getattr(source_message.channel, 'name', '<unknown>')}"
        avatar_url = member.display_avatar.url
        body = source_message.content.strip() if source_message.content else None
        attachment = source_message.attachments[0] if source_message.attachments else None
        attachment_type = (attachment.content_type or "") if attachment is not None else ""

        sent_count = await self._send_message_to_targets(
            destinations=[destination],
            message=source_message,
            author_name=author_name,
            avatar_url=avatar_url,
            body=body,
            attachment=attachment,
            attachment_type=attachment_type,
            ignore_existing_source_message_id=relay_message.id,
        )
        if not sent_count:
            return None

        try:
            await relay_message.delete()
        except discord.HTTPException as exc:
            relay_log.info("repair delete failed for relay message %s: %s", relay_message.id, exc)
            return None
        return True

    async def _repair_legacy_tenor_message(
        self,
        destination: RelayChannel,
        relay_message: discord.Message,
    ) -> bool | None:
        tenor_url = self._tenor_url_from_message(relay_message)
        if tenor_url is None:
            relay_log.info("repair source lookup failed for relay message %s", relay_message.id)
            return None

        previews = await resolve_link_previews([tenor_url])
        preview_embeds = self._preview_embeds(previews)
        preview_file = await self._preview_file_spec(previews, preview_embeds)
        if not preview_embeds:
            relay_log.info("repair legacy tenor preview resolution failed for relay message %s", relay_message.id)
            return None

        sent = await safe_send(
            destination,
            embeds=preview_embeds,
            file=self._discord_file(preview_file),
            allowed_mentions=discord.AllowedMentions.none(),
            dedupe_key=f"relay-legacy-repair:{destination.id}:{relay_message.id}",
            dedupe_window=600,
            dedupe_target_id=f"relay-channel:{destination.id}",
            dedupe_required=True,
        )
        if sent is None:
            return None

        try:
            await relay_message.delete()
        except discord.HTTPException as exc:
            relay_log.info("repair delete failed for legacy relay message %s: %s", relay_message.id, exc)
            return None
        return True

    def _is_message_from_this_bot(self, message: discord.Message) -> bool:
        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None)
        author_id = getattr(getattr(message, "author", None), "id", None)
        return bot_user_id is not None and author_id == bot_user_id

    def _repair_source_allowed(self, source_message: discord.Message, destination: RelayChannel) -> bool:
        guild = getattr(source_message, "guild", None)
        channel = getattr(source_message, "channel", None)
        channel_id = getattr(channel, "id", None)
        if guild is None or guild.id != self.guild_id:
            return False
        if channel_id not in self.target_channels:
            return False
        if channel_id == getattr(destination, "id", None):
            return False
        if str(channel_id) in self.ignored_source_ids:
            return False
        if self._is_sensitive_source(channel, guild):
            return False
        return self._friends_can_view_source(channel, guild)

    @classmethod
    def _message_mentions_source(cls, message: discord.Message, source_markers: tuple[str, ...]) -> bool:
        content = getattr(message, "content", "") or ""
        if any(source_marker in content for source_marker in source_markers):
            return True
        return any(
            cls._payload_contains_text(embed.to_dict(), source_marker)
            for embed in (getattr(message, "embeds", None) or [])
            if hasattr(embed, "to_dict")
            for source_marker in source_markers
        )

    @classmethod
    def _payload_contains_text(cls, payload: Any, needle: str) -> bool:
        if isinstance(payload, str):
            return needle in payload
        if isinstance(payload, dict):
            return any(cls._payload_contains_text(value, needle) for value in payload.values())
        if isinstance(payload, (list, tuple)):
            return any(cls._payload_contains_text(value, needle) for value in payload)
        return False

    def _friends_can_view_source(self, channel: SourceChannel, guild: discord.Guild) -> bool:
        if not self.friends_role_id:
            return False
        role = guild.get_role(self.friends_role_id)
        if role is None:
            return False

        target = channel.parent if isinstance(channel, discord.Thread) and channel.parent is not None else channel
        if not hasattr(target, "permissions_for"):
            return False

        permissions = target.permissions_for(role)
        if not permissions.view_channel:
            return False

        if isinstance(channel, discord.Thread):
            return permissions.read_message_history or permissions.send_messages_in_threads

        return True

    def _is_sensitive_source(self, channel: SourceChannel, guild: discord.Guild) -> bool:
        channel_ids = self._privacy_scope_ids(channel)
        if channel_ids & self.sensitive_source_ids:
            return True

        numeric_ids = [int(channel_id) for channel_id in channel_ids if channel_id.isdigit()]
        if not numeric_ids:
            return False

        try:
            from utils import db

            for channel_id in numeric_ids:
                ticket = db.sync_one(
                    "SELECT channel_id FROM tickets WHERE channel_id = ? AND status = 'open'",
                    (channel_id,),
                )
                if ticket is not None:
                    return True

            config = db.sync_one(
                "SELECT tickets_category_id FROM guild_config WHERE guild_id = ?",
                (int(guild.id),),
            )
            ticket_category_id = None
            if config is not None:
                ticket_category_id = config["tickets_category_id"]
            return ticket_category_id is not None and int(ticket_category_id) in numeric_ids
        except Exception as exc:
            relay_log.info("sensitive source DB check failed for %s: %s", channel_ids, exc)
            return False

    @staticmethod
    def _privacy_scope_ids(channel: SourceChannel) -> set[str]:
        scope_ids = {str(channel_id) for channel_id in [getattr(channel, "id", None)] if channel_id}
        for attr in ("parent_id", "category_id"):
            value = getattr(channel, attr, None)
            if value:
                scope_ids.add(str(value))
        parent = getattr(channel, "parent", None) or getattr(channel, "category", None)
        parent_id = getattr(parent, "id", None)
        if parent_id:
            scope_ids.add(str(parent_id))
        return scope_ids

    def _prune_recent_message_ids(self):
        cutoff = time.time() - 120
        stale = [message_id for message_id, seen_at in self._recent_message_ids.items() if seen_at < cutoff]
        for message_id in stale:
            self._recent_message_ids.pop(message_id, None)

    @staticmethod
    def _is_relay_channel(channel: object) -> bool:
        return isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel))

    @staticmethod
    def _channel_list(channels) -> str:
        return " | ".join(f"{channel.name}({channel.id})" for channel in channels)

    @classmethod
    def _clean_relay_body(cls, body: str | None, message: discord.Message) -> str:
        formatted = cls._format_mentions(body, message)
        if not formatted:
            return ""

        protected_tokens: list[str] = []

        def protect(match: re.Match[str]) -> str:
            protected_tokens.append(match.group(0))
            return f"__LOKI_EMOJI_{len(protected_tokens) - 1}__"

        cleaned = strip_urls(CUSTOM_EMOJI_RE.sub(protect, formatted))
        for index, token in enumerate(protected_tokens):
            cleaned = cleaned.replace(f"__LOKI_EMOJI_{index}__", token)
        return cleaned

    @staticmethod
    def _custom_emoji_image_url(body: str | None) -> str | None:
        body = (body or "").strip()
        match = CUSTOM_EMOJI_RE.fullmatch(body)
        if match is None:
            return None
        extension = "gif" if body.startswith("<a:") else "webp"
        emoji_id = body.rsplit(":", 1)[1].removesuffix(">")
        return f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=96&quality=lossless"

    @classmethod
    def _format_mentions(cls, body: str | None, message: discord.Message) -> str:
        if not body:
            return ""
        formatted = USER_MENTION_RE.sub(lambda match: cls._format_user_mention(match, message), body)
        formatted = ROLE_MENTION_RE.sub(lambda match: cls._format_role_mention(match, message), formatted)
        return CHANNEL_MENTION_RE.sub(lambda match: cls._format_channel_mention(match, message), formatted)

    @staticmethod
    def _format_user_mention(match: re.Match[str], message: discord.Message) -> str:
        user_id = match.group(1)
        mentioned_user = next(
            (user for user in getattr(message, "mentions", []) or [] if str(getattr(user, "id", "")) == user_id),
            None,
        )
        if mentioned_user is None:
            guild = getattr(message, "guild", None)
            if guild is not None and hasattr(guild, "get_member"):
                mentioned_user = guild.get_member(int(user_id))
        if mentioned_user is None:
            return match.group(0)
        return f"@{Relay._display_name(mentioned_user)}"

    @staticmethod
    def _format_role_mention(match: re.Match[str], message: discord.Message) -> str:
        role_id = match.group(1)
        mentioned_role = next(
            (role for role in getattr(message, "role_mentions", []) or [] if str(getattr(role, "id", "")) == role_id),
            None,
        )
        if mentioned_role is None:
            guild = getattr(message, "guild", None)
            mentioned_role = guild.get_role(int(role_id)) if guild is not None and hasattr(guild, "get_role") else None
        if mentioned_role is None:
            return match.group(0)
        return f"@{Relay._display_name(mentioned_role)}"

    @staticmethod
    def _format_channel_mention(match: re.Match[str], message: discord.Message) -> str:
        channel_id = match.group(1)
        mentioned_channel = next(
            (
                channel
                for channel in getattr(message, "channel_mentions", []) or []
                if str(getattr(channel, "id", "")) == channel_id
            ),
            None,
        )
        if mentioned_channel is None:
            guild = getattr(message, "guild", None)
            mentioned_channel = (
                guild.get_channel(int(channel_id)) if guild is not None and hasattr(guild, "get_channel") else None
            )
        if mentioned_channel is None:
            return match.group(0)
        return f"#{Relay._display_name(mentioned_channel)}"

    @staticmethod
    def _display_name(entity: Any) -> str:
        for attr in ("display_name", "global_name", "name"):
            value = getattr(entity, attr, None)
            if value:
                return str(value)
        return str(entity)

    @staticmethod
    def _source_marker(message: discord.Message) -> str:
        jump_url = getattr(message, "jump_url", None)
        if jump_url:
            return str(jump_url)
        guild_id = getattr(getattr(message, "guild", None), "id", None)
        channel_id = getattr(getattr(message, "channel", None), "id", None)
        if channel_id is None:
            channel_id = getattr(message, "channel_id", None)
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message.id}"

    @staticmethod
    def _legacy_source_marker(guild_id: int, message_id: int) -> str:
        return f"LOKI THE SUN GOD relay source {guild_id}:{message_id}"

    @staticmethod
    def _context_embed(*, author_name: str, avatar_url: str, body: str, source_marker: str) -> discord.Embed:
        embed = discord.Embed(color=0x5865F2, url=source_marker)
        if body:
            embed.description = body[:4096]
        embed.set_author(name=author_name, icon_url=avatar_url)
        return embed

    @staticmethod
    def _preview_embeds(previews: list[LinkPreview]) -> list[discord.Embed]:
        embeds: list[discord.Embed] = []
        for preview in previews[:9]:
            title = Relay._preview_visible_text(preview.title, fallback=preview.display_name, limit=256)
            description = Relay._preview_visible_text(preview.description, fallback="", limit=4096)
            site_name = Relay._preview_visible_text(preview.site_name or "", fallback=preview.display_name, limit=256)
            embed = discord.Embed(
                title=title,
                description=description or None,
                url=preview.url,
                color=0x5865F2,
            )
            if site_name:
                embed.set_author(name=site_name)
            artists = Relay._preview_visible_text(extract_music_artists(preview), fallback="", limit=1024)
            if artists:
                embed.add_field(name="Artists", value=artists, inline=False)
            if preview.image_url:
                embed.set_image(url=preview.image_url)
            embeds.append(embed)
        return embeds

    @staticmethod
    def _source_embed_previews(message: discord.Message) -> list[LinkPreview]:
        previews: list[LinkPreview] = []
        for embed in getattr(message, "embeds", None) or []:
            preview = Relay._source_embed_preview(embed)
            if preview is not None:
                previews.append(preview)
        return previews

    @staticmethod
    def _source_embed_preview(embed: discord.Embed) -> LinkPreview | None:
        media_url = Relay._embed_media_url(embed)
        preview_url = Relay._safe_url(getattr(embed, "url", None)) or media_url
        title = str(getattr(embed, "title", "") or "")
        description = str(getattr(embed, "description", "") or "")
        site_name = str(getattr(getattr(embed, "provider", None), "name", "") or "")

        if not preview_url or (not title and not description and not media_url):
            return None

        return LinkPreview(
            url=preview_url,
            title=title or site_name or Relay._preview_visible_text(preview_url, fallback="", limit=256),
            description=description,
            image_url=media_url,
            site_name=site_name or None,
        )

    @staticmethod
    def _embed_media_url(embed: discord.Embed) -> str | None:
        for attr in ("image", "thumbnail"):
            media_url = Relay._safe_url(getattr(getattr(embed, attr, None), "url", None))
            if media_url:
                return media_url
        return None

    @staticmethod
    def _safe_url(value: str | None) -> str | None:
        url = str(value or "").strip()
        if not url:
            return None
        return url if is_safe_preview_url(url) else None

    @staticmethod
    def _merge_previews(*preview_groups: list[LinkPreview]) -> list[LinkPreview]:
        merged: list[LinkPreview] = []
        indexes: dict[str, int] = {}
        for preview_group in preview_groups:
            for preview in preview_group:
                key = Relay._preview_key(preview)
                if not key:
                    merged.append(preview)
                    continue
                existing_index = indexes.get(key)
                if existing_index is None:
                    indexes[key] = len(merged)
                    merged.append(preview)
                    continue
                existing = merged[existing_index]
                if not existing.image_url and preview.image_url:
                    merged[existing_index] = preview
        return merged

    @staticmethod
    def _preview_key(preview: LinkPreview) -> str:
        key = preview.url or preview.image_url or preview.title
        return key.casefold()

    @staticmethod
    def _is_broken_tenor_relay_message(message: discord.Message) -> bool:
        if getattr(getattr(message, "author", None), "bot", False) is not True:
            return False
        if getattr(message, "attachments", None):
            return False
        for embed in getattr(message, "embeds", None) or []:
            if Relay._is_tenor_embed(embed):
                return True
        return False

    @staticmethod
    def _is_tenor_embed(embed: discord.Embed) -> bool:
        title = str(getattr(embed, "title", "") or "")
        description = str(getattr(embed, "description", "") or "")
        author_name = str(getattr(getattr(embed, "author", None), "name", "") or "")
        provider_name = str(getattr(getattr(embed, "provider", None), "name", "") or "")
        url = str(getattr(embed, "url", "") or "")
        host = (urlparse(url).hostname or "").lower()
        is_tenor = (
            "tenor" in host
            or "tenor" in author_name.casefold()
            or "tenor" in provider_name.casefold()
            or "discover & share gifs" in title.casefold()
            or description == "Click to view the GIF"
        )
        return is_tenor

    @staticmethod
    def _relay_source_marker_from_message(message: discord.Message) -> str | None:
        for embed in getattr(message, "embeds", None) or []:
            url = str(getattr(embed, "url", "") or "").strip()
            if "discord.com/channels/" in url:
                return url
        return None

    @staticmethod
    def _tenor_url_from_message(message: discord.Message) -> str | None:
        for embed in getattr(message, "embeds", None) or []:
            if Relay._is_tenor_embed(embed):
                url = str(getattr(embed, "url", "") or "").strip()
                if url:
                    return url
        return None

    async def _source_message_from_relay(
        self,
        relay_message: discord.Message,
        *,
        destination: RelayChannel | None = None,
    ) -> discord.Message | None:
        marker = self._relay_source_marker_from_message(relay_message)
        if not marker:
            return None
        source_parts = self._source_message_ids_from_marker(marker)
        if source_parts is None:
            return None
        guild_id, channel_id, message_id = source_parts
        if not self._repair_marker_allowed(guild_id, channel_id, destination):
            relay_log.info("repair marker rejected before fetch guild=%s channel=%s", guild_id, channel_id)
            return None
        source_channel = self.bot.get_channel(channel_id)
        if source_channel is None:
            try:
                source_channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        if not hasattr(source_channel, "fetch_message"):
            return None
        try:
            return await source_channel.fetch_message(message_id)
        except discord.HTTPException:
            return None

    def _repair_marker_allowed(
        self,
        guild_id: int,
        channel_id: int,
        destination: RelayChannel | None = None,
    ) -> bool:
        if guild_id != self.guild_id:
            return False
        if channel_id not in self.target_channels:
            return False
        if destination is not None and channel_id == getattr(destination, "id", None):
            return False
        return str(channel_id) not in self.ignored_source_ids

    @staticmethod
    def _source_message_ids_from_marker(marker: str) -> tuple[int, int, int] | None:
        match = re.search(r"discord\.com/channels/(\d+)/(\d+)/(\d+)", marker)
        if match is None:
            return None
        return tuple(int(value) for value in match.groups())

    async def _preview_file_spec(
        self,
        previews: list[LinkPreview],
        preview_embeds: list[discord.Embed],
    ) -> PreviewFileSpec | None:
        for index, preview in enumerate(previews):
            if not self._needs_attached_preview(preview):
                continue
            if index >= len(preview_embeds):
                continue
            content = await self._download_preview_file(preview.image_url)
            if not content:
                continue
            filename = self._preview_filename(preview.image_url, preview.title)
            preview_embeds[index].set_image(url=f"attachment://{filename}")
            return PreviewFileSpec(source_url=preview.image_url, filename=filename, content=content)
        return None

    @staticmethod
    def _needs_attached_preview(preview: LinkPreview) -> bool:
        image_url = str(preview.image_url or "")
        if not image_url.lower().endswith(".gif"):
            return False
        host = (urlparse(preview.url).hostname or urlparse(image_url).hostname or "").lower()
        return "tenor.com" in host or "tenor.co" in host

    async def _download_preview_file(self, url: str | None) -> bytes | None:
        if not url:
            return None
        if not is_safe_preview_url(url):
            return None
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"User-Agent": "LOKIRelay/1.0 (+https://discord.com)"}) as response:
                    if response.status != 200:
                        return None
                    final_url = str(response.url)
                    if not is_safe_preview_url(final_url):
                        return None
                    content_type = str(response.headers.get("Content-Type", "")).lower()
                    if content_type and "gif" not in content_type and "octet-stream" not in content_type:
                        return None
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_PREVIEW_DOWNLOAD_BYTES:
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > MAX_PREVIEW_DOWNLOAD_BYTES:
                            return None
                        chunks.append(chunk)
                    return b"".join(chunks)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None

    @staticmethod
    def _preview_filename(url: str | None, title: str | None) -> str:
        path = urlparse(str(url or "")).path
        candidate = os.path.basename(path).strip() or Relay._slugify_filename(title or "preview")
        stem, dot, extension = candidate.rpartition(".")
        if dot and extension.lower() == "gif":
            sanitized = Relay._slugify_filename(stem)
            return f"{sanitized or 'preview'}.gif"
        base = stem if dot else candidate
        sanitized = Relay._slugify_filename(base)
        return f"{sanitized or 'preview'}.gif"

    @staticmethod
    def _slugify_filename(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
        return cleaned[:80]

    @staticmethod
    def _discord_file(preview_file: PreviewFileSpec | None) -> discord.File | None:
        if preview_file is None:
            return None
        return discord.File(BytesIO(preview_file.content), filename=preview_file.filename)

    @staticmethod
    def _preview_visible_text(value: str, *, fallback: str, limit: int) -> str:
        text = strip_urls(value)
        if not text:
            text = strip_urls(fallback)
        return text[:limit]


async def setup(bot: commands.Bot):
    await bot.add_cog(Relay(bot))
