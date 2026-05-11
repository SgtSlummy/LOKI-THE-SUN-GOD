from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import discord
from discord.ext import commands, tasks

log = logging.getLogger("loki.wreckingball_cleanup")

TRUTHY = {"1", "true", "yes", "on"}
DEFAULT_ENABLED = True
DEFAULT_CHANNEL_ID = 1471988991879549110
DEFAULT_AUTHOR_ID = 983091121569804359
DEFAULT_MAX_AGE_SECONDS = 180
DEFAULT_MAX_VISIBLE = 2
DEFAULT_SCAN_LIMIT = 50
DEFAULT_INTERVAL_SECONDS = 30


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


def _csv_values(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _env_ints(name: str) -> list[int]:
    values = []
    for part in _csv_values(os.getenv(name)):
        try:
            parsed = int(part)
        except ValueError:
            log.warning("Ignoring invalid integer in %s: %r", name, part)
            continue
        if parsed <= 0:
            log.warning("Ignoring non-positive integer in %s: %s", name, parsed)
            continue
        values.append(parsed)
    return values


def _env_channel_int_map(name: str, *, minimum: int = 0) -> dict[int, int]:
    values = {}
    for part in _csv_values(os.getenv(name)):
        channel_text, separator, value_text = part.partition(":")
        if not separator:
            log.warning("Ignoring invalid channel override in %s: %r", name, part)
            continue
        try:
            channel_id = int(channel_text.strip())
            value = int(value_text.strip())
        except ValueError:
            log.warning("Ignoring invalid channel override in %s: %r", name, part)
            continue
        if channel_id <= 0:
            log.warning("Ignoring non-positive channel id in %s: %s", name, channel_id)
            continue
        if value < minimum:
            log.warning("Ignoring %s override %s because it is below minimum %s", name, part, minimum)
            continue
        values[channel_id] = value
    return values


LOOP_INTERVAL_SECONDS = _env_int(
    "WRECKINGBALL_CLEANUP_INTERVAL_SECONDS",
    DEFAULT_INTERVAL_SECONDS,
    minimum=1,
)


@dataclass(frozen=True)
class WreckingballCleanupRule:
    channel_id: int = DEFAULT_CHANNEL_ID
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
    max_visible: int = DEFAULT_MAX_VISIBLE
    scan_limit: int = DEFAULT_SCAN_LIMIT


@dataclass(frozen=True)
class WreckingballCleanupConfig:
    enabled: bool = DEFAULT_ENABLED
    channel_id: int = DEFAULT_CHANNEL_ID
    author_id: int = DEFAULT_AUTHOR_ID
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
    max_visible: int = DEFAULT_MAX_VISIBLE
    scan_limit: int = DEFAULT_SCAN_LIMIT
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    channel_rules: tuple[WreckingballCleanupRule, ...] = ()

    @classmethod
    def from_env(cls) -> WreckingballCleanupConfig:
        channel_id = _env_int("WRECKINGBALL_CLEANUP_CHANNEL_ID", DEFAULT_CHANNEL_ID, minimum=1)
        max_age_seconds = _env_int(
            "WRECKINGBALL_CLEANUP_MAX_AGE_SECONDS",
            DEFAULT_MAX_AGE_SECONDS,
            minimum=0,
        )
        max_visible = _env_int("WRECKINGBALL_CLEANUP_MAX_VISIBLE", DEFAULT_MAX_VISIBLE, minimum=0)
        scan_limit = _env_int("WRECKINGBALL_CLEANUP_SCAN_LIMIT", DEFAULT_SCAN_LIMIT, minimum=1)

        channel_ids = _env_ints("WRECKINGBALL_CLEANUP_CHANNEL_IDS") or [channel_id]
        max_age_by_channel = _env_channel_int_map(
            "WRECKINGBALL_CLEANUP_MAX_AGE_SECONDS_BY_CHANNEL",
            minimum=0,
        )
        max_visible_by_channel = _env_channel_int_map(
            "WRECKINGBALL_CLEANUP_MAX_VISIBLE_BY_CHANNEL",
            minimum=0,
        )
        scan_limit_by_channel = _env_channel_int_map(
            "WRECKINGBALL_CLEANUP_SCAN_LIMIT_BY_CHANNEL",
            minimum=1,
        )
        channel_rules = tuple(
            WreckingballCleanupRule(
                channel_id=configured_channel_id,
                max_age_seconds=max_age_by_channel.get(configured_channel_id, max_age_seconds),
                max_visible=max_visible_by_channel.get(configured_channel_id, max_visible),
                scan_limit=scan_limit_by_channel.get(configured_channel_id, scan_limit),
            )
            for configured_channel_id in dict.fromkeys(channel_ids)
        )

        return cls(
            enabled=_env_bool("WRECKINGBALL_CLEANUP_ENABLED", DEFAULT_ENABLED),
            channel_id=channel_id,
            author_id=_env_int("WRECKINGBALL_CLEANUP_AUTHOR_ID", DEFAULT_AUTHOR_ID, minimum=1),
            max_age_seconds=max_age_seconds,
            max_visible=max_visible,
            scan_limit=scan_limit,
            interval_seconds=LOOP_INTERVAL_SECONDS,
            channel_rules=channel_rules,
        )

    @property
    def rules(self) -> tuple[WreckingballCleanupRule, ...]:
        if self.channel_rules:
            return self.channel_rules
        return (
            WreckingballCleanupRule(
                channel_id=self.channel_id,
                max_age_seconds=self.max_age_seconds,
                max_visible=self.max_visible,
                scan_limit=self.scan_limit,
            ),
        )


def _int_matches(value: Any, expected: int) -> bool:
    if value is None:
        return False
    try:
        return int(value) == expected
    except (TypeError, ValueError):
        return False


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


def matching_wreckingball_cleanup_rule(
    message: Any,
    config: WreckingballCleanupConfig,
) -> WreckingballCleanupRule | None:
    message_channel_id = _channel_id(message)
    if message_channel_id is None:
        return None
    if not any(_int_matches(sender_id, config.author_id) for sender_id in _sender_ids(message)):
        return None
    for rule in config.rules:
        if message_channel_id == rule.channel_id:
            return rule
    return None


def is_wreckingball_cleanup_candidate(message: Any, config: WreckingballCleanupConfig) -> bool:
    return matching_wreckingball_cleanup_rule(message, config) is not None


def _is_wreckingball_cleanup_candidate_for_rule(
    message: Any,
    *,
    config: WreckingballCleanupConfig,
    rule: WreckingballCleanupRule,
) -> bool:
    if _channel_id(message) != rule.channel_id:
        return False
    return any(_int_matches(sender_id, config.author_id) for sender_id in _sender_ids(message))


def _created_at(message: Any) -> datetime | None:
    created_at = getattr(message, "created_at", None)
    if not isinstance(created_at, datetime):
        return None
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _message_age_seconds(message: Any, now: datetime) -> float:
    created_at = _created_at(message)
    if created_at is None:
        return 0
    return max(0.0, (now - created_at).total_seconds())


def _sort_key(message: Any) -> datetime:
    return _created_at(message) or datetime.min.replace(tzinfo=timezone.utc)


def select_wreckingball_cleanup_messages(
    messages: Iterable[Any],
    *,
    now: datetime,
    config: WreckingballCleanupConfig,
    rule: WreckingballCleanupRule | None = None,
) -> list[Any]:
    if not config.enabled:
        return []
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    messages_to_delete = []
    for cleanup_rule in (rule,) if rule is not None else config.rules:
        candidates = [
            message
            for message in messages
            if _is_wreckingball_cleanup_candidate_for_rule(
                message,
                config=config,
                rule=cleanup_rule,
            )
        ]
        candidates.sort(key=_sort_key, reverse=True)

        for index, message in enumerate(candidates):
            older_than_visible_cap = index >= cleanup_rule.max_visible
            older_than_age_cap = (
                cleanup_rule.max_age_seconds > 0
                and _message_age_seconds(message, now) >= cleanup_rule.max_age_seconds
            )
            if older_than_visible_cap or older_than_age_cap:
                messages_to_delete.append(message)
    return messages_to_delete


class WreckingballCleanup(commands.Cog):
    """Keep Wreckingball app output from piling up in the configured channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = WreckingballCleanupConfig.from_env()
        self._cleanup_lock = asyncio.Lock()
        if self.config.enabled:
            self.cleanup_loop.start()
        else:
            log.info("Wreckingball cleanup disabled")

    def cog_unload(self):
        self.cleanup_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        rule = matching_wreckingball_cleanup_rule(message, self.config)
        if rule is None:
            return
        await self._cleanup_once("new matching message", rules=(rule,))

    @tasks.loop(seconds=LOOP_INTERVAL_SECONDS)
    async def cleanup_loop(self):
        await self._cleanup_once("scheduled cleanup")

    @cleanup_loop.before_loop
    async def before_cleanup_loop(self):
        await self.bot.wait_until_ready()

    async def _resolve_channel(self, rule: WreckingballCleanupRule) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(rule.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(rule.channel_id)
            except discord.HTTPException as exc:
                log.warning("Could not fetch Wreckingball cleanup channel %s: %s", rule.channel_id, exc)
                return None
        if not hasattr(channel, "history"):
            log.warning("Wreckingball cleanup channel %s does not expose message history", rule.channel_id)
            return None
        return channel

    async def _cleanup_once(
        self,
        reason: str,
        *,
        rules: tuple[WreckingballCleanupRule, ...] | None = None,
    ) -> None:
        if not self.config.enabled or self._cleanup_lock.locked():
            return
        async with self._cleanup_lock:
            for rule in rules or self.config.rules:
                channel = await self._resolve_channel(rule)
                if channel is None:
                    continue

                try:
                    messages = [message async for message in channel.history(limit=rule.scan_limit)]
                except discord.Forbidden:
                    log.warning(
                        "Missing Read Message History permission for Wreckingball cleanup channel %s",
                        rule.channel_id,
                    )
                    continue
                except discord.HTTPException as exc:
                    log.warning(
                        "Could not read Wreckingball cleanup channel %s history: %s",
                        rule.channel_id,
                        exc,
                    )
                    continue

                now = datetime.now(timezone.utc)
                messages_to_delete = select_wreckingball_cleanup_messages(
                    messages,
                    now=now,
                    config=self.config,
                    rule=rule,
                )
                deleted = await self._delete_messages(messages_to_delete, reason, rule)
                if deleted:
                    log.info(
                        "Deleted %s Wreckingball message(s) from channel %s via %s",
                        deleted,
                        rule.channel_id,
                        reason,
                    )

    async def _delete_messages(
        self,
        messages: Iterable[discord.Message],
        reason: str,
        rule: WreckingballCleanupRule | None = None,
    ) -> int:
        deleted = 0
        audit_reason = f"LOKI THE SUN GOD Wreckingball cleanup: {reason}"
        channel_id = rule.channel_id if rule is not None else self.config.channel_id
        for message in messages:
            try:
                await message.delete(reason=audit_reason)
            except TypeError:
                await message.delete()
            except discord.NotFound:
                continue
            except discord.Forbidden:
                log.warning(
                    "Missing Manage Messages permission for Wreckingball cleanup channel %s",
                    channel_id,
                )
                break
            except discord.HTTPException as exc:
                log.warning("Could not delete Wreckingball message %s: %s", getattr(message, "id", "?"), exc)
                continue
            deleted += 1
        return deleted


async def setup(bot: commands.Bot):
    await bot.add_cog(WreckingballCleanup(bot))
