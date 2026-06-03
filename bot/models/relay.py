from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bot.models.media import MediaItem


@dataclass(slots=True)
class RelayRoute:
    id: int
    guild_id: int
    source_channel_id: int
    destination_channel_id: int
    direction: str
    enabled: bool
    created_by: int | None
    created_at: datetime | str


@dataclass(slots=True)
class RelayMessage:
    source_guild_id: int
    source_channel_id: int
    source_channel_name: str
    source_message_id: int
    source_message_url: str
    author_user_id: int
    author_display_name: str
    author_avatar_url: str | None
    clean_text: str
    attachments: list[Any]
    embeds: list[Any]
    stickers: list[Any]
    detected_links: list[str]
    media_items: list[MediaItem]
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

