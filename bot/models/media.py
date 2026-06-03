from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MediaKind(str, Enum):
    IMAGE = "image"
    GIF = "gif"
    FILE = "file"
    VIDEO = "video"
    VIDEO_CARD = "video_card"
    SOCIAL_CARD = "social_card"
    STICKER = "sticker"
    GENERIC_CARD = "generic_card"


@dataclass(slots=True)
class MediaItem:
    kind: MediaKind
    source_url: str | None = None
    provider: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    media_type: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None
    uploadable: bool = False
    visible_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MediaResolution:
    clean_text: str
    detected_links: list[str]
    media_items: list[MediaItem]

