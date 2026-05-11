import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import discord
from discord.ext import commands

from utils import runtime_paths
from utils.helpers import safe_send
from utils.link_previews import LinkPreview, extract_music_artists, extract_urls, resolve_link_previews, strip_urls

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
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")
CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]{1,32}:\d+>")


@dataclass
class RelayBackfillResult:
    scanned: int = 0
    relays_sent: int = 0
    failed_sources: int = 0


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
    ):
        is_image = attachment_type.startswith("image/") and "gif" not in attachment_type
        is_file_gif_or_video = attachment_type.startswith("video/") or attachment_type == "image/gif"
        urls = extract_urls(body)
        cleaned_body = self._clean_relay_body(body, message)
        emoji_image_url = self._custom_emoji_image_url(cleaned_body)
        preview_embeds = self._preview_embeds(await resolve_link_previews(urls))
        source_marker = self._source_marker(message)
        source_markers = (
            source_marker,
            self._legacy_source_marker(message.guild.id, message.id),
        )

        sent_count = 0
        for channel in destinations:
            try:
                if await self._destination_already_has_source(channel, source_markers):
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
                    sent = await safe_send(
                        channel,
                        embeds=[context_embed, *preview_embeds],
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

    async def _destination_already_has_source(self, channel: RelayChannel, source_markers: tuple[str, ...]) -> bool:
        if not hasattr(channel, "history"):
            return False
        try:
            async for existing in channel.history(limit=12):
                if self._message_mentions_source(existing, source_markers):
                    return True
        except discord.HTTPException as exc:
            relay_log.info("source history check failed for %s(%s): %s", channel.name, channel.id, exc)
        except Exception:
            relay_log.exception("source history check crashed for %s(%s)", channel.name, channel.id)
        return False

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
    def _preview_visible_text(value: str, *, fallback: str, limit: int) -> str:
        text = strip_urls(value)
        if not text:
            text = strip_urls(fallback)
        return text[:limit]


async def setup(bot: commands.Bot):
    await bot.add_cog(Relay(bot))
