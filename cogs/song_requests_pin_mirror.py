from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import aiohttp
import discord
from discord.ext import commands, tasks

log = logging.getLogger("loki.song_requests_pin_mirror")

TRUTHY = {"1", "true", "yes", "on"}
IS_COMPONENTS_V2 = 1 << 15
DEFAULT_ENABLED = False
DEFAULT_GUILD_ID = 1463393482306486387
DEFAULT_SOURCE_CHANNEL_ID = 1503116743793574009
DEFAULT_SOURCE_MESSAGE_ID = 0
DEFAULT_TARGET_CHANNEL_ID = 1499435617971343491
DEFAULT_REFRESH_SECONDS = 30
DEFAULT_SOURCE_HISTORY_LIMIT = 10
DEFAULT_TARGET_HISTORY_LIMIT = 50
DEFAULT_COMMAND_CLEANUP_AGE_SECONDS = 60
DEFAULT_COMMAND_PREFIXES = ("/", "!", ".", "?", "$", "-")
DEFAULT_FORWARD_SOURCE_MESSAGE = False
API_BASE = "https://discord.com/api/v10"
MESSAGE_REFERENCE_TYPE_FORWARD = 1
URL_RE = re.compile(r"https?://[^\s<>)\]]+")


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


def _env_prefixes(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    prefixes = tuple(part.strip() for part in value.split(",") if part.strip())
    return prefixes or default


LOOP_INTERVAL_SECONDS = _env_int(
    "SONG_REQUESTS_PIN_MIRROR_REFRESH_SECONDS",
    DEFAULT_REFRESH_SECONDS,
    minimum=5,
)


@dataclass(frozen=True)
class SongRequestsPinMirrorConfig:
    enabled: bool = DEFAULT_ENABLED
    guild_id: int = DEFAULT_GUILD_ID
    source_channel_id: int = DEFAULT_SOURCE_CHANNEL_ID
    source_message_id: int = DEFAULT_SOURCE_MESSAGE_ID
    target_channel_id: int = DEFAULT_TARGET_CHANNEL_ID
    managed_message_id: int = 0
    forward_source_message: bool = DEFAULT_FORWARD_SOURCE_MESSAGE
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS
    source_history_limit: int = DEFAULT_SOURCE_HISTORY_LIMIT
    target_history_limit: int = DEFAULT_TARGET_HISTORY_LIMIT
    command_cleanup_age_seconds: int = DEFAULT_COMMAND_CLEANUP_AGE_SECONDS
    command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES

    @classmethod
    def from_env(cls) -> SongRequestsPinMirrorConfig:
        return cls(
            enabled=_env_bool("SONG_REQUESTS_PIN_MIRROR_ENABLED", DEFAULT_ENABLED),
            guild_id=_env_int("SONG_REQUESTS_PIN_MIRROR_GUILD_ID", DEFAULT_GUILD_ID, minimum=1),
            source_channel_id=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_SOURCE_CHANNEL_ID",
                DEFAULT_SOURCE_CHANNEL_ID,
                minimum=1,
            ),
            source_message_id=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_SOURCE_MESSAGE_ID",
                DEFAULT_SOURCE_MESSAGE_ID,
                minimum=0,
            ),
            target_channel_id=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_TARGET_CHANNEL_ID",
                DEFAULT_TARGET_CHANNEL_ID,
                minimum=1,
            ),
            managed_message_id=_env_int("SONG_REQUESTS_PIN_MIRROR_MANAGED_MESSAGE_ID", 0, minimum=0),
            forward_source_message=_env_bool(
                "SONG_REQUESTS_PIN_MIRROR_FORWARD_SOURCE_MESSAGE",
                DEFAULT_FORWARD_SOURCE_MESSAGE,
            ),
            refresh_seconds=LOOP_INTERVAL_SECONDS,
            source_history_limit=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_SOURCE_HISTORY_LIMIT",
                DEFAULT_SOURCE_HISTORY_LIMIT,
                minimum=1,
            ),
            target_history_limit=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_TARGET_HISTORY_LIMIT",
                DEFAULT_TARGET_HISTORY_LIMIT,
                minimum=1,
            ),
            command_cleanup_age_seconds=_env_int(
                "SONG_REQUESTS_PIN_MIRROR_COMMAND_CLEANUP_AGE_SECONDS",
                DEFAULT_COMMAND_CLEANUP_AGE_SECONDS,
                minimum=1,
            ),
            command_prefixes=_env_prefixes(
                "SONG_REQUESTS_PIN_MIRROR_COMMAND_PREFIXES",
                DEFAULT_COMMAND_PREFIXES,
            ),
        )


class DiscordAPIError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, payload: Any):
        super().__init__(f"{method} {path} failed with HTTP {status}: {payload!r}")
        self.method = method
        self.path = path
        self.status = status
        self.payload = payload


def _message_id(message: dict[str, Any] | None) -> int | None:
    if not message:
        return None
    try:
        return int(message.get("id"))
    except (TypeError, ValueError):
        return None


def _author_id(message: dict[str, Any]) -> int | None:
    try:
        return int((message.get("author") or {}).get("id"))
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def message_age_seconds(message: dict[str, Any], now: datetime) -> float:
    created_at = _parse_timestamp(message.get("timestamp"))
    if created_at is None:
        return 0.0
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return max(0.0, (now - created_at).total_seconds())


def _component_id(component: dict[str, Any]) -> dict[str, int]:
    component_id = component.get("id")
    return {"id": component_id} if isinstance(component_id, int) else {}


def _media_payload(media: dict[str, Any] | None) -> dict[str, str] | None:
    url = (media or {}).get("url")
    if not url:
        return None
    return {"url": str(url)}


def _media_item_payload(item: dict[str, Any]) -> dict[str, Any] | None:
    media = _media_payload(item.get("media") if isinstance(item.get("media"), dict) else None)
    if media is None:
        return None
    payload: dict[str, Any] = {"media": media}
    if item.get("description"):
        payload["description"] = str(item["description"])[:1024]
    if item.get("spoiler"):
        payload["spoiler"] = True
    return payload


def _iter_component_text_content(components: Any):
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, dict):
            continue
        if component.get("type") == 10 and component.get("content"):
            yield str(component["content"])
        yield from _iter_component_text_content(component.get("components"))
        accessory = component.get("accessory")
        if isinstance(accessory, dict):
            yield from _iter_component_text_content([accessory])


def control_url_from_source(source_message: dict[str, Any]) -> str | None:
    urls: list[str] = []
    for content in _iter_component_text_content(source_message.get("components")):
        urls.extend(match.group(0).rstrip(".,;:") for match in URL_RE.finditer(content))

    for url in urls:
        if "divabot.xyz" in url and "/webplayer" in url:
            return url
    for url in urls:
        if "divabot.xyz" in url:
            return url
    return None


def sanitize_component_for_mirror(
    component: dict[str, Any],
    *,
    control_url: str | None = None,
) -> dict[str, Any] | None:
    component_type = component.get("type")
    if component_type == 10:
        content = str(component.get("content") or "")
        return {"type": 10, **_component_id(component), "content": content}

    if component_type == 12:
        items = [
            item_payload
            for item in component.get("items", [])
            if isinstance(item, dict)
            for item_payload in [_media_item_payload(item)]
            if item_payload is not None
        ]
        if not items:
            return None
        return {"type": 12, **_component_id(component), "items": items[:10]}

    if component_type == 14:
        payload: dict[str, Any] = {"type": 14, **_component_id(component)}
        if "divider" in component:
            payload["divider"] = bool(component["divider"])
        if isinstance(component.get("spacing"), int):
            payload["spacing"] = component["spacing"]
        return payload

    if component_type == 17:
        children = sanitize_components_for_mirror(component.get("components", []), control_url=control_url)
        if not children:
            return None
        payload = {"type": 17, **_component_id(component), "components": children}
        if isinstance(component.get("accent_color"), int):
            payload["accent_color"] = component["accent_color"]
        return payload

    if component_type == 1:
        children = sanitize_components_for_mirror(component.get("components", []), control_url=control_url)
        if not children:
            return None
        return {"type": 1, **_component_id(component), "components": children[:5]}

    if component_type == 2:
        payload: dict[str, Any] = {"type": 2, **_component_id(component)}
        for key in ("label", "emoji"):
            if key in component and component[key] is not None:
                payload[key] = component[key]

        source_url = component.get("url")
        if source_url:
            payload["style"] = 5
            payload["url"] = str(source_url)
        elif control_url:
            return None
        else:
            if "style" in component and component["style"] is not None:
                payload["style"] = component["style"]
            if "custom_id" in component and component["custom_id"] is not None:
                payload["custom_id"] = component["custom_id"]
            payload["disabled"] = True

        if "url" in payload and not payload.get("label") and "emoji" not in payload:
            payload["label"] = "Open Player"
        if "disabled" in component:
            payload["disabled"] = bool(component["disabled"])
        return payload

    if component_type == 9:
        children = sanitize_components_for_mirror(component.get("components", []), control_url=control_url)
        accessory = component.get("accessory")
        payload: dict[str, Any] = {"type": 9, **_component_id(component)}
        if children:
            payload["components"] = children
        if isinstance(accessory, dict):
            sanitized_accessory = sanitize_component_for_mirror(accessory, control_url=control_url)
            if sanitized_accessory is not None:
                payload["accessory"] = sanitized_accessory
        return payload if len(payload) > 2 else None

    if component_type == 11:
        media = _media_payload(component.get("media") if isinstance(component.get("media"), dict) else None)
        if media is None:
            return None
        payload = {"type": 11, **_component_id(component), "media": media}
        if component.get("description"):
            payload["description"] = str(component["description"])[:1024]
        if component.get("spoiler"):
            payload["spoiler"] = True
        return payload

    return None


def sanitize_components_for_mirror(components: Any, *, control_url: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(components, list):
        return []
    sanitized = [
        sanitized_component
        for component in components
        if isinstance(component, dict)
        for sanitized_component in [sanitize_component_for_mirror(component, control_url=control_url)]
        if sanitized_component is not None
    ]
    return sanitized[:40]


def _text_display_components_from_message(source_message: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[str] = []
    content = str(source_message.get("content") or "").strip()
    if content:
        parts.append(content)
    for embed in source_message.get("embeds") or []:
        if not isinstance(embed, dict):
            continue
        title = str(embed.get("title") or "").strip()
        description = str(embed.get("description") or "").strip()
        if title:
            parts.append(f"### {title}")
        if description:
            parts.append(description)
    if not parts:
        return [{"type": 10, "content": "_No song request message is available yet._"}]
    return [{"type": 10, "content": "\n\n".join(parts)[:4000]}]


def _open_player_action_row(control_url: str) -> dict[str, Any]:
    return {
        "type": 1,
        "components": [
            {
                "type": 2,
                "style": 5,
                "label": "Open Diva Webplayer",
                "url": control_url,
            }
        ],
    }


def mirror_components_from_source(source_message: dict[str, Any]) -> list[dict[str, Any]]:
    control_url = control_url_from_source(source_message)
    components = sanitize_components_for_mirror(
        source_message.get("components"),
        control_url=control_url,
    )
    if components and control_url:
        components.append(_open_player_action_row(control_url))
        return components[:40]
    return components or _text_display_components_from_message(source_message)


def mirror_payload_from_source(source_message: dict[str, Any], *, include_flags: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": None,
        "embeds": None,
        "components": mirror_components_from_source(source_message),
        "allowed_mentions": {"parse": []},
    }
    if include_flags:
        payload["flags"] = IS_COMPONENTS_V2
    return payload


def forward_payload_from_source(
    source_message: dict[str, Any],
    config: SongRequestsPinMirrorConfig,
) -> dict[str, Any] | None:
    source_message_id = _message_id(source_message)
    if source_message_id is None:
        return None
    return {
        "message_reference": {
            "type": MESSAGE_REFERENCE_TYPE_FORWARD,
            "guild_id": str(config.guild_id),
            "channel_id": str(config.source_channel_id),
            "message_id": str(source_message_id),
        },
        "allowed_mentions": {"parse": []},
    }


def mirror_fingerprint(source_message: dict[str, Any]) -> str:
    payload = {"components": mirror_components_from_source(source_message)}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _snapshot_message_payload(message: dict[str, Any]) -> dict[str, Any]:
    snapshots = message.get("message_snapshots")
    if isinstance(snapshots, list) and snapshots:
        snapshot_message = (snapshots[0] or {}).get("message")
        if isinstance(snapshot_message, dict):
            return snapshot_message
    return message


def _canonical_forward_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical_forward_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _canonical_forward_value(child)
        for key, child in value.items()
        if not (key == "disabled" and child is False)
    }


def forward_fingerprint(message: dict[str, Any]) -> str:
    payload_source = _snapshot_message_payload(message)
    payload = {
        "content": str(payload_source.get("content") or ""),
        "embeds": _canonical_forward_value(payload_source.get("embeds") or []),
        "components": _canonical_forward_value(payload_source.get("components") or []),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def is_command_cleanup_candidate(
    message: dict[str, Any],
    *,
    config: SongRequestsPinMirrorConfig,
    managed_message_id: int | None,
    bot_user_id: int | None,
    now: datetime,
) -> bool:
    message_id = _message_id(message)
    if message_id is not None and managed_message_id is not None and message_id == managed_message_id:
        return False
    if message.get("pinned"):
        return False
    if message_age_seconds(message, now) < config.command_cleanup_age_seconds:
        return False

    content = str(message.get("content") or "").strip()
    if content.startswith(config.command_prefixes):
        return True
    if message.get("interaction_metadata") is not None:
        return True
    if int(message.get("type") or 0) != 0:
        return True
    author = message.get("author") or {}
    if author.get("bot"):
        return _author_id(message) != bot_user_id
    return False


class SongRequestsPinMirror(commands.Cog):
    """Mirror the Diva song-request channel into one pinned jukebox message."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = SongRequestsPinMirrorConfig.from_env()
        self._managed_message_id = self.config.managed_message_id or None
        self._sync_lock = asyncio.Lock()
        self._bot_user_id: int | None = None
        if self.config.enabled:
            self.refresh_loop.start()
        else:
            log.info("Song requests pinned mirror disabled")

    def cog_unload(self):
        self.refresh_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.config.enabled:
            return
        channel_id = getattr(getattr(message, "channel", None), "id", None)
        if channel_id == self.config.source_channel_id:
            await self._sync_once(reason="source message")
        elif channel_id == self.config.target_channel_id:
            await self._cleanup_target_commands(reason="target message")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if self.config.enabled and payload.channel_id == self.config.source_channel_id:
            await self._sync_once(reason="source edit")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if self.config.enabled and payload.channel_id == self.config.source_channel_id:
            await self._sync_once(reason="source delete")

    @tasks.loop(seconds=LOOP_INTERVAL_SECONDS)
    async def refresh_loop(self):
        await self._sync_once(reason="scheduled refresh")

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        await self.bot.wait_until_ready()

    async def _sync_once(self, *, reason: str) -> None:
        if not self.config.enabled or self._sync_lock.locked():
            return
        async with self._sync_lock:
            source_message = await self._latest_source_message()
            if source_message is None:
                log.info(
                    "No source song-request message found in channel %s during %s",
                    self.config.source_channel_id,
                    reason,
                )
                await self._cleanup_target_commands(reason=reason)
                return

            managed_message = await self._find_managed_message()
            if managed_message is None:
                managed_message = await self._create_managed_message(source_message, reason=reason)
            else:
                replacement_message = await self._edit_managed_message(managed_message, source_message, reason=reason)
                if replacement_message is not None:
                    managed_message = replacement_message

            managed_id = _message_id(managed_message)
            if managed_id is not None:
                self._managed_message_id = managed_id
                await self._ensure_pinned(managed_message, reason=reason)
            await self._cleanup_target_commands(reason=reason)

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        audit_reason: str | None = None,
    ) -> Any:
        token = os.getenv("DISCORD_TOKEN") or getattr(getattr(self.bot, "http", None), "token", None)
        if not token:
            raise DiscordAPIError(method, path, 0, "DISCORD_TOKEN is not configured")
        headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": "LOKISongRequestsPinMirror",
        }
        if audit_reason:
            headers["X-Audit-Log-Reason"] = quote(audit_reason, safe=" ")
        if payload is not None:
            headers["Content-Type"] = "application/json"

        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        async with aiohttp.ClientSession() as session:
            async with session.request(method, f"{API_BASE}{path}", headers=headers, data=data) as response:
                if response.status == 429:
                    retry_payload = await response.json(content_type=None)
                    await asyncio.sleep(float(retry_payload.get("retry_after") or 1.0) + 0.25)
                    return await self._api_request(method, path, payload=payload, audit_reason=audit_reason)
                if response.status in {200, 201}:
                    return await response.json(content_type=None)
                if response.status == 204:
                    return None
                try:
                    error_payload = await response.json(content_type=None)
                except aiohttp.ContentTypeError:
                    error_payload = await response.text()
                raise DiscordAPIError(method, path, response.status, error_payload)

    async def _bot_id(self) -> int | None:
        if self._bot_user_id is not None:
            return self._bot_user_id
        user_id = getattr(getattr(self.bot, "user", None), "id", None)
        if user_id is None:
            user = await self._api_request("GET", "/users/@me")
            user_id = (user or {}).get("id")
        try:
            self._bot_user_id = int(user_id)
        except (TypeError, ValueError):
            self._bot_user_id = None
        return self._bot_user_id

    async def _latest_source_message(self) -> dict[str, Any] | None:
        if self.config.source_message_id:
            try:
                message = await self._api_request(
                    "GET",
                    f"/channels/{self.config.source_channel_id}/messages/{self.config.source_message_id}",
                )
            except DiscordAPIError as exc:
                log.warning(
                    "Could not fetch configured song-request source message %s in channel %s: %s",
                    self.config.source_message_id,
                    self.config.source_channel_id,
                    exc,
                )
                return None
            return message if isinstance(message, dict) else None

        messages = await self._api_request(
            "GET",
            f"/channels/{self.config.source_channel_id}/messages?limit={self.config.source_history_limit}",
        )
        if not isinstance(messages, list):
            return None
        for message in messages:
            if isinstance(message, dict) and (
                message.get("components") or message.get("content") or message.get("embeds")
            ):
                return message
        return None

    async def _find_managed_message(self) -> dict[str, Any] | None:
        bot_user_id = await self._bot_id()
        if self._managed_message_id:
            try:
                message = await self._api_request(
                    "GET",
                    f"/channels/{self.config.target_channel_id}/messages/{self._managed_message_id}",
                )
            except DiscordAPIError as exc:
                if exc.status not in {403, 404}:
                    log.warning("Could not fetch managed song-request mirror %s: %s", self._managed_message_id, exc)
            else:
                if bot_user_id is None or _author_id(message) == bot_user_id:
                    return message

        try:
            pins = await self._api_request("GET", f"/channels/{self.config.target_channel_id}/pins?limit=50")
        except DiscordAPIError as exc:
            log.warning("Could not list pinned song-request mirror messages: %s", exc)
            return None
        if not isinstance(pins, list):
            return None
        for message in pins:
            if isinstance(message, dict) and (bot_user_id is None or _author_id(message) == bot_user_id):
                return message
        return None

    async def _create_managed_message(self, source_message: dict[str, Any], *, reason: str) -> dict[str, Any] | None:
        if self.config.forward_source_message:
            forward_payload = forward_payload_from_source(source_message, self.config)
            if forward_payload is not None:
                try:
                    message = await self._api_request(
                        "POST",
                        f"/channels/{self.config.target_channel_id}/messages",
                        payload=forward_payload,
                        audit_reason=f"LOKI THE SUN GOD song requests pin forward: {reason}",
                    )
                except DiscordAPIError as exc:
                    log.warning(
                        "Could not forward song-request source %s into %s; falling back to mirror: %s",
                        _message_id(source_message),
                        self.config.target_channel_id,
                        exc,
                    )
                else:
                    log.info("Forwarded song-request source message %s via %s", (message or {}).get("id"), reason)
                    return message

        try:
            message = await self._api_request(
                "POST",
                f"/channels/{self.config.target_channel_id}/messages",
                payload=mirror_payload_from_source(source_message, include_flags=True),
                audit_reason=f"LOKI THE SUN GOD song requests pin mirror: {reason}",
            )
        except DiscordAPIError as exc:
            log.warning("Could not create pinned song-request mirror in %s: %s", self.config.target_channel_id, exc)
            return None
        log.info("Created pinned song-request mirror message %s via %s", (message or {}).get("id"), reason)
        return message

    async def _edit_managed_message(
        self,
        managed_message: dict[str, Any],
        source_message: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any] | None:
        managed_id = _message_id(managed_message)
        if managed_id is None:
            return None

        if self.config.forward_source_message:
            if forward_fingerprint(managed_message) == forward_fingerprint(source_message):
                return managed_message
            replacement = await self._create_managed_message(source_message, reason=reason)
            if replacement is None:
                return managed_message
            await self._delete_message(managed_id, reason=f"replace forwarded song-request mirror: {reason}")
            return replacement

        if managed_message.get("message_snapshots"):
            replacement = await self._create_managed_message(source_message, reason=reason)
            if replacement is None:
                return managed_message
            await self._delete_message(managed_id, reason=f"replace forwarded song-request mirror: {reason}")
            return replacement

        if mirror_fingerprint(managed_message) == mirror_fingerprint(source_message):
            return managed_message
        try:
            await self._api_request(
                "PATCH",
                f"/channels/{self.config.target_channel_id}/messages/{managed_id}",
                payload=mirror_payload_from_source(source_message, include_flags=False),
                audit_reason=f"LOKI THE SUN GOD song requests pin mirror: {reason}",
            )
        except DiscordAPIError as exc:
            log.warning("Could not edit pinned song-request mirror %s: %s", managed_id, exc)
            return managed_message
        log.info("Updated pinned song-request mirror message %s via %s", managed_id, reason)
        return managed_message

    async def _delete_message(self, message_id: int, *, reason: str) -> None:
        try:
            await self._api_request(
                "DELETE",
                f"/channels/{self.config.target_channel_id}/messages/{message_id}",
                audit_reason=f"LOKI THE SUN GOD song requests pin mirror: {reason}",
            )
        except DiscordAPIError as exc:
            if exc.status == 404:
                return
            log.warning("Could not delete replaced song-request mirror %s: %s", message_id, exc)

    async def _ensure_pinned(self, managed_message: dict[str, Any] | None, *, reason: str) -> None:
        managed_id = _message_id(managed_message)
        if managed_id is None or (managed_message or {}).get("pinned"):
            return
        try:
            await self._api_request(
                "PUT",
                f"/channels/{self.config.target_channel_id}/messages/pins/{managed_id}",
                audit_reason=f"LOKI THE SUN GOD song requests pin mirror: {reason}",
            )
        except DiscordAPIError as exc:
            log.warning("Could not pin song-request mirror %s: %s", managed_id, exc)
            return
        log.info("Pinned song-request mirror message %s via %s", managed_id, reason)

    async def _cleanup_target_commands(self, *, reason: str) -> None:
        if self.config.command_cleanup_age_seconds <= 0:
            return
        try:
            messages = await self._api_request(
                "GET",
                f"/channels/{self.config.target_channel_id}/messages?limit={self.config.target_history_limit}",
            )
        except DiscordAPIError as exc:
            log.warning("Could not read target channel for song-request command cleanup: %s", exc)
            return
        if not isinstance(messages, list):
            return

        now = datetime.now(timezone.utc)
        bot_user_id = await self._bot_id()
        managed_id = self._managed_message_id
        deleted = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            if not is_command_cleanup_candidate(
                message,
                config=self.config,
                managed_message_id=managed_id,
                bot_user_id=bot_user_id,
                now=now,
            ):
                continue
            message_id = _message_id(message)
            if message_id is None:
                continue
            try:
                await self._api_request(
                    "DELETE",
                    f"/channels/{self.config.target_channel_id}/messages/{message_id}",
                    audit_reason=f"LOKI THE SUN GOD song requests command cleanup: {reason}",
                )
            except DiscordAPIError as exc:
                if exc.status == 404:
                    continue
                log.warning("Could not delete old song-request command message %s: %s", message_id, exc)
                continue
            deleted += 1
        if deleted:
            log.info(
                "Deleted %s old command message(s) from song-request mirror target %s via %s",
                deleted,
                self.config.target_channel_id,
                reason,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SongRequestsPinMirror(bot))
