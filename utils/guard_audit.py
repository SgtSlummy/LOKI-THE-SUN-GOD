from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("loki.guard_audit")


def _safe_details(details: dict[str, Any] | None) -> str | None:
    if not details:
        return None
    safe = {
        str(key): value
        for key, value in details.items()
        if key not in {"content", "message", "token", "env", "secret", "raw"}
    }
    return json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True)[:2000]


async def record_guard_audit(
    event_type: str,
    reason: str,
    *,
    owner_id: str | None = None,
    target_id: str | None = None,
    fingerprint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    from utils import db

    try:
        async with db.get() as conn:
            await conn.execute(
                "INSERT INTO guard_audit(event_type,reason,owner_id,target_id,fingerprint,details,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    event_type,
                    reason,
                    owner_id,
                    target_id,
                    fingerprint,
                    _safe_details(details),
                    int(time.time()),
                ),
            )
            await conn.commit()
    except Exception:
        log.exception("failed to write guard audit event_type=%s reason=%s", event_type, reason)
