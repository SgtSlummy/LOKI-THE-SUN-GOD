from __future__ import annotations

import re
import time

from utils import db

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}|token\s+[A-Za-z0-9._-]+)\b"
)
DISCORD_TOKEN_RE = re.compile(r"\b[MNO][A-Za-z\d_-]{20,}\.[A-Za-z\d_-]{6,}\.[A-Za-z\d_-]{20,}\b")


def redact_discord_content(content: str) -> str:
    redacted = EMAIL_RE.sub("[email]", content or "")
    redacted = DISCORD_TOKEN_RE.sub("[secret]", redacted)
    redacted = SECRET_RE.sub("[secret]", redacted)
    return redacted


def public_memory_allowed(*, is_private_channel: bool, author_opted_out: bool, deleted: bool = False) -> bool:
    return not is_private_channel and not author_opted_out and not deleted


def remember_public_message(*, guild_id: int, channel_id: int, user_id: int, content: str) -> None:
    redacted = redact_discord_content(content)
    if not redacted.strip():
        return
    db.sync_exec(
        """
        INSERT INTO loki_memory_entries(guild_id, channel_id, user_id, redacted_content, confidence, created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (guild_id, channel_id, user_id, redacted[:2000], 0.4, int(time.time())),
    )


def recent_public_memory(guild_id: int, limit: int = 8) -> list[str]:
    rows = db.sync_all(
        """
        SELECT redacted_content FROM loki_memory_entries
        WHERE guild_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (guild_id, max(1, min(20, limit))),
    )
    return [row["redacted_content"] for row in rows]
