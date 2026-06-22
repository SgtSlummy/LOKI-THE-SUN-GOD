from __future__ import annotations

from dataclasses import dataclass, field

from bot.models.media import MediaKind
from bot.models.relay import RelayMessage

DEFAULT_RELAY_CHANNEL_NAMES = {
    "messages": "loki-messages",
    "pictures": "loki-pictures",
    "gifs": "loki-gifs",
    "emotes": "loki-emotes",
    "music": "loki-music-relay",
}

PICTURE_KINDS = {MediaKind.IMAGE}
MOVING_KINDS = {MediaKind.GIF, MediaKind.VIDEO, MediaKind.VIDEO_CARD}
EMOTE_KINDS = {MediaKind.EMOTE, MediaKind.STICKER}


@dataclass(slots=True)
class RelayMediaConfig:
    channel_ids: dict[str, int] = field(default_factory=dict)
    channel_names: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RELAY_CHANNEL_NAMES))
    duplicate_text_with_media: bool = False

    @property
    def output_channel_ids(self) -> set[int]:
        return {channel_id for channel_id in self.channel_ids.values() if channel_id is not None}


def should_ignore_source_channel(source_channel_id: int, config: RelayMediaConfig) -> bool:
    return source_channel_id in config.output_channel_ids


def select_relay_channel_key(relay: RelayMessage) -> str:
    kinds = {item.kind for item in relay.media_items}
    if kinds & EMOTE_KINDS:
        return "emotes"
    if kinds & MOVING_KINDS:
        return "gifs"
    if kinds & PICTURE_KINDS:
        return "pictures"
    return "messages"
