import re
import time
from datetime import timedelta
from typing import Any

_RECENT_SENDS: dict[tuple[str, str], float] = {}

DURATION_RE = re.compile(r"(\d+)([smhdw])")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(s: str) -> int:
    total = 0
    for num, unit in DURATION_RE.findall(s.lower()):
        total += int(num) * UNITS[unit]
    return total


def fmt_duration(secs: int) -> str:
    return str(timedelta(seconds=int(secs)))


def now() -> int:
    return int(time.time())


def _prune_recent_sends(current: float) -> None:
    expired = [key for key, expires_at in _RECENT_SENDS.items() if expires_at <= current]
    for key in expired:
        _RECENT_SENDS.pop(key, None)


def _embed_signature(embed: Any) -> str:
    if embed is None:
        return ""
    return "|".join(
        str(part or "")
        for part in (
            getattr(embed, "title", ""),
            getattr(embed, "description", ""),
            getattr(embed, "url", ""),
            getattr(getattr(embed, "footer", None), "text", ""),
        )
    )


async def _claim_dedupe(target_id: str, dedupe_key: str, dedupe_window: float) -> bool:
    from utils import db

    created_at = int(time.time())
    expires_at = created_at + max(1, int(dedupe_window))
    async with db.get() as conn:
        await conn.execute("DELETE FROM send_dedupe WHERE expires_at<=?", (created_at,))
        cur = await conn.execute(
            "INSERT OR IGNORE INTO send_dedupe(target_id,dedupe_key,created_at,expires_at) VALUES(?,?,?,?)",
            (target_id, dedupe_key, created_at, expires_at),
        )
        await conn.commit()
    return cur.rowcount == 1


async def _release_dedupe(target_id: str, dedupe_key: str) -> None:
    try:
        from utils import db

        async with db.get() as conn:
            await conn.execute(
                "DELETE FROM send_dedupe WHERE target_id=? AND dedupe_key=?",
                (target_id, dedupe_key),
            )
            await conn.commit()
    except Exception:
        pass


async def safe_send(
    target,
    *,
    dedupe_key: str | None = None,
    dedupe_window: float = 5.0,
    dedupe_target_id: int | str | None = None,
    dedupe_required: bool = False,
    **kwargs,
):
    """
    Best-effort duplicate-send guardrail for races/retries.
    Returns the created message, or None if a matching send was suppressed.
    """
    explicit_dedupe_key = dedupe_key is not None
    target_id = str(dedupe_target_id if dedupe_target_id is not None else getattr(target, "id", id(target)))
    if dedupe_key is None:
        dedupe_key = "|".join(
            str(part)
            for part in (
                kwargs.get("content", ""),
                _embed_signature(kwargs.get("embed")),
            )
        )
    current = time.monotonic()
    _prune_recent_sends(current)
    cache_key = (target_id, dedupe_key)
    cached_until = _RECENT_SENDS.get(cache_key)
    if cached_until is not None and cached_until > current:
        return None
    expires_at = current + dedupe_window
    _RECENT_SENDS[cache_key] = expires_at
    try:
        claimed = await _claim_dedupe(target_id, dedupe_key, dedupe_window)
    except Exception:
        if dedupe_required:
            return None
        claimed = True
    if not claimed:
        return None
    try:
        token = None
        if explicit_dedupe_key:
            from utils.outbound_post_guard import pop_outbound_dedupe_key, push_outbound_dedupe_key

            token = push_outbound_dedupe_key(dedupe_key)
        try:
            return await target.send(**kwargs)
        finally:
            if token is not None:
                pop_outbound_dedupe_key(token)
    except Exception:
        if _RECENT_SENDS.get(cache_key) == expires_at:
            _RECENT_SENDS.pop(cache_key, None)
        await _release_dedupe(target_id, dedupe_key)
        raise


def xp_for_level(level: int) -> int:
    return 5 * (level**2) + 50 * level + 100


def level_from_xp(xp: int) -> int:
    lvl = 0
    while xp >= xp_for_level(lvl):
        xp -= xp_for_level(lvl)
        lvl += 1
    return lvl


INVITE_RE = re.compile(r"(discord\.gg|discord(app)?\.com/invite)/\S+", re.I)
