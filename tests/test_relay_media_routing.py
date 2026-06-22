from datetime import datetime, timezone

from bot.models.media import MediaItem, MediaKind
from bot.models.relay import RelayMessage
from bot.services.relay_media import RelayMediaConfig, select_relay_channel_key, should_ignore_source_channel


def make_relay(*, clean_text="", media_items=None, source_channel_id=10):
    return RelayMessage(
        source_guild_id=1,
        source_channel_id=source_channel_id,
        source_channel_name="source",
        source_message_id=100,
        source_message_url="https://discord.com/channels/1/10/100",
        author_user_id=123,
        author_display_name="User",
        author_avatar_url=None,
        clean_text=clean_text,
        attachments=[],
        embeds=[],
        stickers=[],
        detected_links=[],
        media_items=media_items or [],
        created_at=datetime.now(timezone.utc),
    )


def test_route_selection_sends_text_only_to_messages_channel():
    relay = make_relay(clean_text="hello")

    assert select_relay_channel_key(relay) == "messages"


def test_route_selection_sends_static_image_attachment_to_pictures_channel():
    relay = make_relay(media_items=[MediaItem(kind=MediaKind.IMAGE, source_url="https://x/image.png")])

    assert select_relay_channel_key(relay) == "pictures"


def test_route_selection_sends_gif_and_video_to_gifs_channel():
    assert select_relay_channel_key(make_relay(media_items=[MediaItem(kind=MediaKind.GIF)])) == "gifs"
    assert select_relay_channel_key(make_relay(media_items=[MediaItem(kind=MediaKind.VIDEO)])) == "gifs"
    assert select_relay_channel_key(make_relay(media_items=[MediaItem(kind=MediaKind.VIDEO_CARD)])) == "gifs"


def test_route_selection_sends_stickers_and_custom_emojis_to_emotes_channel():
    assert select_relay_channel_key(make_relay(media_items=[MediaItem(kind=MediaKind.STICKER)])) == "emotes"
    assert select_relay_channel_key(make_relay(media_items=[MediaItem(kind=MediaKind.EMOTE)])) == "emotes"


def test_route_selection_prioritizes_specific_media_channel_over_general_messages():
    relay = make_relay(clean_text="look", media_items=[MediaItem(kind=MediaKind.IMAGE)])

    assert select_relay_channel_key(relay) == "pictures"


def test_route_selection_ignores_configured_output_channels_to_prevent_loops():
    config = RelayMediaConfig(channel_ids={"messages": 10, "pictures": 20})

    assert should_ignore_source_channel(10, config) is True
    assert should_ignore_source_channel(99, config) is False
