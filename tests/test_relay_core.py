from datetime import datetime, timezone

from bot.models.media import MediaResolution
from bot.models.relay import RelayMessage
from bot.plugins.relay_core.formatting import build_relay_content, safe_allowed_mentions


def test_relay_content_includes_author_source_and_clean_text_only():
    relay = RelayMessage(
        source_guild_id=1,
        source_channel_id=10,
        source_channel_name="source-channel",
        source_message_id=100,
        source_message_url="https://discord.com/channels/1/10/100",
        author_user_id=123,
        author_display_name="Display Name",
        author_avatar_url=None,
        clean_text="This is clean text.",
        attachments=[],
        embeds=[],
        stickers=[],
        detected_links=[],
        media_items=[],
        created_at=datetime.now(timezone.utc),
    )

    assert build_relay_content(relay) == (
        "**Display Name** — from #source-channel\n"
        "This is clean text."
    )


def test_allowed_mentions_are_fully_disabled_for_relays():
    allowed = safe_allowed_mentions()

    assert allowed.to_dict() == {"parse": []}


def test_media_resolution_carries_detected_links_separately_from_clean_text():
    resolution = MediaResolution(
        clean_text="Watch this",
        detected_links=["https://youtu.be/dQw4w9WgXcQ"],
        media_items=[],
    )

    assert "https://" not in resolution.clean_text
    assert resolution.detected_links == ["https://youtu.be/dQw4w9WgXcQ"]
