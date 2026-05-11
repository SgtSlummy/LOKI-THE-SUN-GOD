from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("loki.outbound_guard")

DEFAULT_DEDUPE_WINDOW_SECONDS = 600
DEFAULT_HISTORY_LIMIT = 12
_RECENT_SENDS: dict[tuple[str, str], float] = {}
_GUARD_ACTIVE: ContextVar[bool] = ContextVar("loki_outbound_guard_active", default=False)
_EXPLICIT_DEDUPE_KEY: ContextVar[str | None] = ContextVar("loki_outbound_dedupe_key", default=None)
_INSTALLED = False
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_DISCORD_JUMP_RE = re.compile(r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\S+", re.IGNORECASE)
_MARKDOWN_NOISE_RE = re.compile(r"[*_`~>|]+")
_SPACE_RE = re.compile(r"\s+")


def _signature_from_dedupe_key(dedupe_key: str) -> str:
    raw = json.dumps({"dedupe_key": dedupe_key}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def push_outbound_dedupe_key(dedupe_key: str | None):
    return _EXPLICIT_DEDUPE_KEY.set(dedupe_key)


def pop_outbound_dedupe_key(token) -> None:
    _EXPLICIT_DEDUPE_KEY.reset(token)


def _window_seconds() -> int:
    return DEFAULT_DEDUPE_WINDOW_SECONDS


def _history_limit() -> int:
    return DEFAULT_HISTORY_LIMIT


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "id"):
        return str(getattr(value, "id"))
    return str(value)


def _embed_payload(embed: Any) -> Any:
    if embed is None:
        return None
    if hasattr(embed, "to_dict"):
        return _jsonable(embed.to_dict())
    return str(embed)


def _normalize_visible_text(value: Any) -> str:
    text = str(value or "")
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _DISCORD_JUMP_RE.sub("", text)
    text = _MARKDOWN_NOISE_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip().casefold()
    return text


def _visible_embed_payload(embed: Any) -> list[str]:
    if embed is None:
        return []
    if not hasattr(embed, "to_dict"):
        return [_normalize_visible_text(embed)]

    data = embed.to_dict()
    parts: list[str] = []
    for key in ("title", "description", "url"):
        if data.get(key):
            parts.append(_normalize_visible_text(data.get(key)))
    footer = data.get("footer") or {}
    if footer.get("text"):
        parts.append(_normalize_visible_text(footer.get("text")))
    for field in data.get("fields") or []:
        parts.append(_normalize_visible_text(field.get("name")))
        parts.append(_normalize_visible_text(field.get("value")))
    for key in ("image", "thumbnail", "video"):
        media = data.get(key) or {}
        if media.get("url"):
            parts.append(_normalize_visible_text(media.get("url")))
    return [part for part in parts if part]


def _file_payload(file: Any) -> Any:
    if file is None:
        return None
    return {
        "filename": str(getattr(file, "filename", "") or ""),
        "spoiler": bool(getattr(file, "spoiler", False)),
    }


def _view_payload(view: Any) -> Any:
    if view is None:
        return None
    children = []
    for child in getattr(view, "children", []) or []:
        options = []
        for option in getattr(child, "options", []) or []:
            options.append(
                {
                    "label": _normalize_visible_text(getattr(option, "label", "")),
                    "description": _normalize_visible_text(getattr(option, "description", "")),
                }
            )
        children.append(
            {
                "type": child.__class__.__name__,
                "label": _normalize_visible_text(getattr(child, "label", "")),
                "url": _normalize_visible_text(getattr(child, "url", "")),
                "disabled": bool(getattr(child, "disabled", False)),
                "options": options,
            }
        )
    return {"type": view.__class__.__name__, "children": children}


def _visible_object_text(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("label", "name", "text", "title"):
        attr_value = getattr(value, attr, None)
        if attr_value:
            return _normalize_visible_text(attr_value)
    return _normalize_visible_text(value)


def _poll_payload(poll: Any) -> Any:
    if poll is None:
        return None
    question = getattr(poll, "question", None)
    answers = []
    for answer in getattr(poll, "answers", []) or []:
        answers.append(_visible_object_text(answer))
    return {
        "question": _visible_object_text(question),
        "answers": [answer for answer in answers if answer],
    }


def _explicit_embeds(kwargs: dict[str, Any]) -> list[Any]:
    embeds = []
    if kwargs.get("embed") is not None:
        embeds.append(kwargs["embed"])
    embeds.extend(kwargs.get("embeds") or [])
    return embeds


def _explicit_files(kwargs: dict[str, Any]) -> list[Any]:
    files = []
    if kwargs.get("file") is not None:
        files.append(kwargs["file"])
    files.extend(kwargs.get("files") or [])
    return files


def _outbound_parts(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    content = kwargs.get("content", args[0] if args else None)
    if content is not None:
        content = str(content)
    files = [_file_payload(file) for file in _explicit_files(kwargs)]
    return {
        "content": _normalize_visible_text(content or ""),
        "embeds": [_visible_embed_payload(embed) for embed in _explicit_embeds(kwargs)],
        "files": files,
        "stickers": [_visible_object_text(sticker) for sticker in (kwargs.get("stickers") or [])],
        "poll": _poll_payload(kwargs.get("poll")),
        "view": _view_payload(kwargs.get("view")),
    }


def outbound_signature(args: tuple[Any, ...] = (), kwargs: dict[str, Any] | None = None) -> str:
    payload = _outbound_parts(args, kwargs or {})
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _message_parts(message: Any) -> dict[str, Any]:
    return {
        "content": _normalize_visible_text(getattr(message, "content", "") or ""),
        "embeds": [_visible_embed_payload(embed) for embed in (getattr(message, "embeds", None) or [])],
        "files": [
            {
                "filename": str(getattr(attachment, "filename", "") or ""),
                "spoiler": bool(getattr(attachment, "is_spoiler", lambda: False)()),
            }
            for attachment in (getattr(message, "attachments", None) or [])
        ],
    }


def _payload_matches_message(payload: dict[str, Any], message: Any) -> bool:
    existing = _message_parts(message)
    if payload["content"] != existing["content"]:
        return False
    if payload["embeds"] and payload["embeds"] != existing["embeds"][: len(payload["embeds"])]:
        return False
    if payload["files"]:
        existing_files = existing["files"][: len(payload["files"])]
        if payload["files"] != existing_files:
            return False
    return True


def _bot_user_id_from(target: Any) -> int | None:
    candidates = [
        getattr(getattr(target, "bot", None), "user", None),
        getattr(getattr(target, "client", None), "user", None),
        getattr(getattr(target, "_state", None), "user", None),
        getattr(getattr(getattr(target, "_state", None), "_get_client", lambda: None)(), "user", None),
    ]
    interaction = getattr(target, "_parent", None)
    if interaction is not None:
        candidates.extend(
            [
                getattr(getattr(interaction, "client", None), "user", None),
                getattr(getattr(interaction, "_state", None), "user", None),
            ]
        )
    for candidate in candidates:
        user_id = getattr(candidate, "id", None)
        if user_id is not None:
            return int(user_id)
    return None


def _webhook_id_from(target: Any) -> int | None:
    webhook_id = getattr(target, "id", None)
    if target.__class__.__name__.lower().endswith("webhook") and webhook_id is not None:
        return int(webhook_id)
    return None


def _channel_from(target: Any) -> Any | None:
    for attr in ("channel", "_channel"):
        channel = getattr(target, attr, None)
        if channel is not None:
            return channel
    interaction = getattr(target, "_parent", None)
    if interaction is not None:
        channel = getattr(interaction, "channel", None)
        if channel is not None:
            return channel
    if hasattr(target, "history"):
        return target
    return None


def _target_id(target: Any, kwargs: dict[str, Any]) -> str:
    thread = kwargs.get("thread")
    if thread is not None and getattr(thread, "id", None) is not None:
        return f"channel:{int(thread.id)}"

    channel = _channel_from(target)
    channel_id = getattr(channel, "id", None)
    if channel_id is not None:
        return f"channel:{int(channel_id)}"

    interaction = getattr(target, "_parent", None)
    channel_id = getattr(interaction, "channel_id", None)
    if channel_id is not None:
        return f"channel:{int(channel_id)}"

    webhook_channel_id = getattr(target, "channel_id", None)
    if webhook_channel_id is not None:
        return f"channel:{int(webhook_channel_id)}"

    target_id = getattr(target, "id", None)
    if target_id is not None:
        return f"{target.__class__.__name__}:{int(target_id)}"
    return f"object:{id(target)}"


def _prune_recent(now: float) -> None:
    expired = [key for key, expires_at in _RECENT_SENDS.items() if expires_at <= now]
    for key in expired:
        _RECENT_SENDS.pop(key, None)


async def _claim_send(target_id: str, signature: str, window_seconds: int) -> bool:
    from utils import db

    created_at = int(time.time())
    expires_at = created_at + window_seconds
    dedupe_key = f"outbound:{signature}"
    async with db.get() as conn:
        await conn.execute("DELETE FROM send_dedupe WHERE expires_at<=?", (created_at,))
        cur = await conn.execute(
            "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
            (target_id, dedupe_key, created_at, expires_at),
        )
        await conn.commit()
    return cur.rowcount == 1


async def _release_send(target_id: str, signature: str) -> None:
    from utils import db

    try:
        async with db.get() as conn:
            await conn.execute(
                "DELETE FROM send_dedupe WHERE target_id=? AND dedupe_key=?",
                (target_id, f"outbound:{signature}"),
            )
            await conn.commit()
    except Exception:
        log.exception("could not release outbound dedupe claim target=%s signature=%s", target_id, signature)


async def _history_has_duplicate(
    target: Any, payload: dict[str, Any], kwargs: dict[str, Any]
) -> tuple[bool | None, str]:
    limit = _history_limit()
    if limit <= 0:
        return False, "history_disabled"
    channel = _channel_from(target)
    if channel is None or not hasattr(channel, "history"):
        return False, "history_not_available"

    bot_user_id = _bot_user_id_from(target)
    webhook_id = _webhook_id_from(target)
    if bot_user_id is None and webhook_id is None:
        return None, "sender_identity_unknown"
    try:
        async for message in channel.history(limit=limit):
            message_author_id = getattr(getattr(message, "author", None), "id", None)
            message_webhook_id = getattr(message, "webhook_id", None)
            from_this_sender = (bot_user_id is not None and message_author_id == bot_user_id) or (
                webhook_id is not None and message_webhook_id == webhook_id
            )
            if from_this_sender and _payload_matches_message(payload, message):
                return True, "history_duplicate"
    except Exception:
        log.exception("could not inspect recent channel history before outbound send")
        return None, "history_check_error"
    return False, "history_clear"


async def _audit_suppressed(
    reason: str,
    *,
    owner_id: str | None,
    target_id: str,
    fingerprint: str,
    details: dict[str, Any] | None = None,
) -> None:
    from utils.guard_audit import record_guard_audit

    await record_guard_audit(
        "outbound_send_guard",
        reason,
        owner_id=owner_id,
        target_id=target_id,
        fingerprint=fingerprint,
        details=details,
    )


async def guarded_send(
    target: Any,
    original_send: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
) -> Any | None:
    if _GUARD_ACTIVE.get():
        return await original_send(target, *args, **kwargs)

    explicit_dedupe_key = _EXPLICIT_DEDUPE_KEY.get()
    payload = _outbound_parts(args, kwargs)
    signature = (
        _signature_from_dedupe_key(explicit_dedupe_key)
        if explicit_dedupe_key is not None
        else outbound_signature(args, kwargs)
    )
    target_id = _target_id(target, kwargs)
    window_seconds = _window_seconds()
    from utils import worker_singleton

    lease_ok, lease_reason, lease = await worker_singleton.verify_active_worker_lease()
    owner_id = lease.owner_id if lease is not None else None
    if not lease_ok:
        await _audit_suppressed(
            lease_reason,
            owner_id=owner_id,
            target_id=target_id,
            fingerprint=signature,
        )
        log.warning(
            "suppressed outbound post because worker lease is not current reason=%s target=%s signature=%s",
            lease_reason,
            target_id,
            signature,
        )
        worker_singleton.request_hard_shutdown(f"outbound send fenced by {lease_reason}")
        return None

    now = time.monotonic()
    _prune_recent(now)
    cache_key = (target_id, signature)
    if _RECENT_SENDS.get(cache_key, 0) > now:
        await _audit_suppressed(
            "process_cache_duplicate",
            owner_id=owner_id,
            target_id=target_id,
            fingerprint=signature,
        )
        log.warning(
            "suppressed duplicate outbound post from process cache target=%s signature=%s", target_id, signature
        )
        return None

    if explicit_dedupe_key is None:
        history_duplicate, history_reason = await _history_has_duplicate(target, payload, kwargs)
        if history_duplicate is None:
            await _audit_suppressed(
                history_reason,
                owner_id=owner_id,
                target_id=target_id,
                fingerprint=signature,
            )
            log.warning(
                "suppressed outbound post because history check was uncertain target=%s signature=%s",
                target_id,
                signature,
            )
            return None
        if history_duplicate:
            _RECENT_SENDS[cache_key] = now + window_seconds
            await _audit_suppressed(
                history_reason,
                owner_id=owner_id,
                target_id=target_id,
                fingerprint=signature,
            )
            log.warning(
                "suppressed duplicate outbound post found in channel history target=%s signature=%s",
                target_id,
                signature,
            )
            return None

    try:
        claimed = await _claim_send(target_id, signature, window_seconds)
    except Exception as exc:
        await _audit_suppressed(
            "dedupe_claim_error",
            owner_id=owner_id,
            target_id=target_id,
            fingerprint=signature,
            details={"error_type": type(exc).__name__},
        )
        log.warning(
            "suppressed outbound post because dedupe claim failed target=%s signature=%s error=%s",
            target_id,
            signature,
            type(exc).__name__,
        )
        return None
    if not claimed:
        _RECENT_SENDS[cache_key] = now + window_seconds
        await _audit_suppressed(
            "shared_dedupe_duplicate",
            owner_id=owner_id,
            target_id=target_id,
            fingerprint=signature,
        )
        log.warning(
            "suppressed duplicate outbound post from shared dedupe target=%s signature=%s", target_id, signature
        )
        return None

    lease_ok, lease_reason, lease = await worker_singleton.verify_active_worker_lease()
    owner_id = lease.owner_id if lease is not None else owner_id
    if not lease_ok:
        await _release_send(target_id, signature)
        await _audit_suppressed(
            lease_reason,
            owner_id=owner_id,
            target_id=target_id,
            fingerprint=signature,
            details={"stage": "post_dedupe_pre_send"},
        )
        log.warning(
            "suppressed outbound post because worker lease was lost before Discord send "
            "reason=%s target=%s signature=%s",
            lease_reason,
            target_id,
            signature,
        )
        worker_singleton.request_hard_shutdown(f"outbound send fenced by {lease_reason}")
        return None

    _RECENT_SENDS[cache_key] = now + window_seconds
    token = _GUARD_ACTIVE.set(True)
    try:
        return await original_send(target, *args, **kwargs)
    except Exception:
        if _RECENT_SENDS.get(cache_key) == now + window_seconds:
            _RECENT_SENDS.pop(cache_key, None)
        await _release_send(target_id, signature)
        raise
    finally:
        _GUARD_ACTIVE.reset(token)


def _patch_method(owner: Any, name: str) -> None:
    marker = f"_loki_original_{name}"
    if hasattr(owner, marker):
        return
    original = getattr(owner, name)
    setattr(owner, marker, original)

    async def wrapped(self, *args: Any, **kwargs: Any) -> Any | None:
        return await guarded_send(self, original, *args, **kwargs)

    wrapped.__name__ = getattr(original, "__name__", name)
    wrapped.__qualname__ = getattr(original, "__qualname__", f"{owner.__name__}.{name}")
    setattr(owner, name, wrapped)


def install_outbound_post_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import discord
    from discord.ext import commands

    _patch_method(discord.abc.Messageable, "send")
    _patch_method(discord.Webhook, "send")
    _patch_method(discord.InteractionResponse, "send_message")
    _patch_method(commands.Context, "send")
    _patch_method(commands.Context, "reply")
    _INSTALLED = True
    log.info("LOKI THE SUN GOD outbound post guard installed")


async def self_check() -> None:
    from utils import db, worker_singleton

    old_path = os.environ.get("LOKI_DB_PATH")
    old_database_url = os.environ.pop("DATABASE_URL", None)
    old_shutdown = worker_singleton.set_hard_shutdown_enabled(False)
    original_claim_send = _claim_send

    class Author:
        id = 999

    class State:
        user = Author()

    class Message:
        def __init__(self, content: str, embeds: list[Any] | None = None):
            self.content = content
            self.embeds = embeds or []
            self.attachments = []
            self.author = Author()
            self.webhook_id = None

    class Embed:
        def __init__(self, author_name: str, description: str):
            self.author_name = author_name
            self.description = description

        def to_dict(self) -> dict[str, Any]:
            return {
                "author": {"name": self.author_name},
                "description": self.description,
                "fields": [{"name": "Source", "value": self.description.splitlines()[-1]}],
            }

    class Target:
        _state = State()

        def __init__(self, target_id: int):
            self.id = target_id
            self.sent: list[str] = []
            self._history: list[Message] = []

        def history(self, *, limit: int):
            messages = list(self._history[:limit])

            class History:
                def __aiter__(self):
                    self._items = iter(messages)
                    return self

                async def __anext__(self):
                    try:
                        return next(self._items)
                    except StopIteration:
                        raise StopAsyncIteration

            return History()

    class NoHistoryTarget:
        id = 888
        _state = State()

        def __init__(self):
            self.sent: list[str] = []
            self._history: list[Message] = []

    async def original(target: Target, content: str | None = None, **kwargs: Any) -> Message:
        embeds = []
        if kwargs.get("embed") is not None:
            embeds.append(kwargs["embed"])
        embeds.extend(kwargs.get("embeds") or [])
        message = Message(content or "", embeds)
        target.sent.append(message.content)
        target._history.insert(0, message)
        return message

    async def guarded_with_key(target: Target, dedupe_key: str, content: str) -> Message | None:
        token = push_outbound_dedupe_key(dedupe_key)
        try:
            return await guarded_send(target, original, content)
        finally:
            pop_outbound_dedupe_key(token)

    async def broken_claim(target_id: str, signature: str, window_seconds: int) -> bool:
        raise RuntimeError("simulated dedupe claim failure")

    try:
        with tempfile.TemporaryDirectory(prefix="loki-outbound-guard-") as tmp:
            os.environ["LOKI_DB_PATH"] = str(Path(tmp) / "bot.db")
            await db.init()
            _RECENT_SENDS.clear()
            worker_singleton.clear_hard_shutdown_request()
            lease = await worker_singleton.claim_worker_lease("outbound-self-check-owner", replace_existing=True)
            worker_singleton.set_active_worker_lease(lease)
            audit_since = int(time.time()) - 1
            base_id = int(time.time() * 1000)

            target = Target(base_id)
            first = await guarded_send(target, original, "mechanical duplicate check")
            second = await guarded_send(target, original, "mechanical duplicate check")
            if first is None or second is not None or target.sent != ["mechanical duplicate check"]:
                raise AssertionError("Outbound post guard did not suppress an identical second send.")

            other = Target(base_id + 1)
            other._history.append(Message("already posted"))
            historical = await guarded_send(other, original, "already posted")
            if historical is not None or other.sent:
                raise AssertionError("Outbound post guard did not suppress a matching prior channel post.")

            embed_target = Target(base_id + 2)
            first_embed = Embed(
                "Cannibal, Cannabis the III rd in #The Vibez 101 FM",
                "Dude\n\n[view message](https://discord.com/channels/1/2/3)",
            )
            second_embed = Embed(
                "Cannibal, Cannabis the III rd in #The Vibez101 FM",
                "Dude\n\n[view message](https://discord.com/channels/1/2/4)",
            )
            sent_embed = await guarded_send(embed_target, original, embed=first_embed)
            duplicate_embed = await guarded_send(embed_target, original, embed=second_embed)
            if sent_embed is None or duplicate_embed is not None or len(embed_target.sent) != 1:
                raise AssertionError("Outbound post guard did not suppress a visually identical relay embed.")

            cross_a = Target(base_id + 3)
            cross_b = Target(base_id + 4)
            first_cross = await guarded_send(cross_a, original, "channel-scoped duplicate body")
            second_cross = await guarded_send(cross_b, original, "channel-scoped duplicate body")
            if (
                first_cross is None
                or second_cross is None
                or cross_a.sent != ["channel-scoped duplicate body"]
                or cross_b.sent != ["channel-scoped duplicate body"]
            ):
                raise AssertionError("Outbound post guard did not allow the same post body in separate destinations.")

            dm_a = NoHistoryTarget()
            first_private = await guarded_send(dm_a, original, "private duplicate", ephemeral=True)
            second_private = await guarded_send(dm_a, original, "private duplicate", ephemeral=True)
            if first_private is None or second_private is not None or dm_a.sent != ["private duplicate"]:
                raise AssertionError("Outbound post guard did not suppress duplicate no-history private sends.")

            relay_target = Target(base_id + 5)
            first_relay = await guarded_with_key(relay_target, "relay:source-message:1:dest", "same relay body")
            second_relay = await guarded_with_key(relay_target, "relay:source-message:2:dest", "same relay body")
            third_relay = await guarded_with_key(relay_target, "relay:source-message:2:dest", "same relay body")
            if (
                first_relay is None
                or second_relay is None
                or third_relay is not None
                or relay_target.sent != ["same relay body", "same relay body"]
            ):
                raise AssertionError("Outbound post guard did not honor explicit source-message dedupe keys.")

            globals()["_claim_send"] = broken_claim
            failed_target = Target(base_id + 6)
            failed = await guarded_send(failed_target, original, "dedupe claim failure")
            if failed is not None or failed_target.sent:
                raise AssertionError("Outbound post guard did not fail closed when the DB claim failed.")
            globals()["_claim_send"] = original_claim_send

            stolen = await worker_singleton.claim_worker_lease("outbound-self-check-new-owner", replace_existing=True)
            fenced_target = Target(base_id + 7)
            fenced = await guarded_send(fenced_target, original, "lost lease send")
            if fenced is not None or fenced_target.sent or not worker_singleton.hard_shutdown_requested():
                raise AssertionError("Outbound post guard did not fence out a stale worker before sending.")

            async with db.get() as conn:
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM guard_audit WHERE event_type=? AND created_at>=?",
                    ("outbound_send_guard", audit_since),
                )
                audit_count = (await cur.fetchone())[0]
            if audit_count < 6:
                raise AssertionError("Outbound post guard did not write durable audit rows for suppressed sends.")

            await worker_singleton.release_worker_lease(stolen)
    finally:
        globals()["_claim_send"] = original_claim_send
        worker_singleton.clear_active_worker_lease()
        worker_singleton.clear_hard_shutdown_request()
        worker_singleton.set_hard_shutdown_enabled(old_shutdown)
        if old_path is None:
            os.environ.pop("LOKI_DB_PATH", None)
        else:
            os.environ["LOKI_DB_PATH"] = old_path
        if old_database_url is not None:
            os.environ["DATABASE_URL"] = old_database_url


def run_self_check() -> None:
    asyncio.run(self_check())
