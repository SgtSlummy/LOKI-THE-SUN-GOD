from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

DEFAULT_WRECKINGBALL_AUTHOR_NAMES = {"wreckingball", "diva music bot"}


@dataclass(slots=True)
class WreckingballCleanupResult:
    dry_run: bool
    keep: int
    scanned_count: int
    candidate_count: int
    planned_delete_ids: list[int]
    deleted_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _author_name(message: Any) -> str:
    author = getattr(message, "author", None)
    return str(getattr(author, "display_name", None) or getattr(author, "name", "")).strip().casefold()


def is_wreckingball_message(message: Any, *, author_names: set[str] | None = None, bot_user_ids: set[int] | None = None) -> bool:
    author = getattr(message, "author", None)
    if author is None or not getattr(author, "bot", False):
        return False
    if bot_user_ids and getattr(author, "id", None) in bot_user_ids:
        return True
    names = {name.casefold() for name in (author_names or DEFAULT_WRECKINGBALL_AUTHOR_NAMES)}
    return _author_name(message) in names


def select_wreckingball_deletes(
    messages: Iterable[Any],
    *,
    keep: int = 2,
    author_names: set[str] | None = None,
    bot_user_ids: set[int] | None = None,
) -> list[Any]:
    by_channel: dict[int, list[Any]] = defaultdict(list)
    for message in messages:
        if not is_wreckingball_message(message, author_names=author_names, bot_user_ids=bot_user_ids):
            continue
        channel_id = getattr(getattr(message, "channel", None), "id", 0)
        by_channel[int(channel_id)].append(message)

    selected: list[Any] = []
    for channel_messages in by_channel.values():
        ordered = sorted(channel_messages, key=lambda item: (getattr(item, "created_at", None), getattr(item, "id", 0)))
        if keep <= 0:
            selected.extend(ordered)
        elif len(ordered) > keep:
            selected.extend(ordered[:-keep])
    return sorted(selected, key=lambda item: (getattr(getattr(item, "channel", None), "id", 0), getattr(item, "created_at", None), getattr(item, "id", 0)))


async def cleanup_wreckingball_messages(
    messages: Iterable[Any],
    *,
    dry_run: bool = True,
    keep: int = 2,
    author_names: set[str] | None = None,
    bot_user_ids: set[int] | None = None,
    reason: str = "Loki Wreckingball cleanup",
) -> WreckingballCleanupResult:
    materialized = list(messages)
    candidates = [
        message
        for message in materialized
        if is_wreckingball_message(message, author_names=author_names, bot_user_ids=bot_user_ids)
    ]
    selected = select_wreckingball_deletes(candidates, keep=keep, author_names=author_names, bot_user_ids=bot_user_ids)
    result = WreckingballCleanupResult(
        dry_run=dry_run,
        keep=keep,
        scanned_count=len(materialized),
        candidate_count=len(candidates),
        planned_delete_ids=[int(getattr(message, "id")) for message in selected],
    )
    if dry_run:
        return result

    for message in selected:
        try:
            await message.delete(reason=reason)
            result.deleted_ids.append(int(getattr(message, "id")))
        except Exception as exc:  # pragma: no cover - exact discord exceptions vary by version
            result.errors.append(f"{getattr(message, 'id', 'unknown')}: {exc}")
    return result
