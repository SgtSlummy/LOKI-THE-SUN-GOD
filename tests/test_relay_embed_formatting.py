from datetime import datetime, timezone

import discord

from bot.models.media import MediaItem, MediaKind
from bot.models.relay import RelayMessage
from bot.plugins.relay_core.formatting import build_relay_embeds, media_cards_to_embeds


def make_relay():
    return RelayMessage(
        source_guild_id=1,
        source_channel_id=10,
        source_channel_name="general",
        source_message_id=100,
        source_message_url="https://discord.com/channels/1/10/100",
        author_user_id=123,
        author_display_name="Display Name",
        author_avatar_url="https://cdn.example/avatar.png",
        clean_text="Look at this",
        attachments=[],
        embeds=[],
        stickers=[],
        detected_links=["https://youtu.be/dQw4w9WgXcQ"],
        media_items=[
            MediaItem(
                kind=MediaKind.VIDEO_CARD,
                source_url="https://youtu.be/dQw4w9WgXcQ",
                provider="YouTube",
                title="A Video",
                thumbnail_url="https://img.example/thumb.jpg",
            )
        ],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_clean_relay_embed_contains_author_source_jump_and_clean_text():
    embed = build_relay_embeds(make_relay())[0]
    data = embed.to_dict()

    assert data["author"]["name"] == "Display Name"
    assert data["description"] == "Look at this"
    assert "https://youtu" not in data["description"]
    fields = {field["name"]: field["value"] for field in data["fields"]}
    assert fields["Source"] == "#general"
    assert fields["Original"] == "[Jump to message](https://discord.com/channels/1/10/100)"
    assert data["footer"]["text"] == "Relayed by Loki"


def test_link_card_embed_uses_clickable_title_url_without_raw_url_in_description():
    embeds = media_cards_to_embeds(make_relay().media_items)
    data = embeds[0].to_dict()

    assert data["title"] == "A Video"
    assert data["url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert "description" not in data or "https://youtu" not in data["description"]


def test_multiple_links_create_limited_clean_embeds():
    items = [
        MediaItem(kind=MediaKind.GENERIC_CARD, source_url=f"https://example.com/{i}", title=f"Title {i}")
        for i in range(20)
    ]

    embeds = media_cards_to_embeds(items)

    assert len(embeds) == 10
    assert all(isinstance(embed, discord.Embed) for embed in embeds)
    assert embeds[0].url == "https://example.com/0"
