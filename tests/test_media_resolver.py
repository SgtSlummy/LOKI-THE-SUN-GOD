from types import SimpleNamespace

import pytest

from bot.models.media import MediaKind
from bot.services.media_resolver import MediaResolver


@pytest.mark.asyncio
async def test_discord_gif_attachment_is_normalized_as_uploadable_gif():
    resolver = MediaResolver()
    attachment = SimpleNamespace(
        id=1,
        url="https://cdn.discordapp.com/attachments/1/dance.gif",
        proxy_url="https://media.discordapp.net/attachments/1/dance.gif",
        filename="dance.gif",
        content_type="image/gif",
        size=128_000,
        description=None,
    )

    result = await resolver.resolve(content="", embeds=[], attachments=[attachment], stickers=[])

    assert len(result.media_items) == 1
    item = result.media_items[0]
    assert item.kind == MediaKind.GIF
    assert item.filename == "dance.gif"
    assert item.uploadable is True
    assert item.content_type == "image/gif"


@pytest.mark.asyncio
async def test_youtube_link_becomes_clean_card_without_exposing_raw_url():
    resolver = MediaResolver(fetch_external_metadata=False)

    result = await resolver.resolve(
        content="Watch this https://youtu.be/dQw4w9WgXcQ",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    cards = [item for item in result.media_items if item.provider == "YouTube"]

    assert len(cards) == 1
    assert cards[0].kind == MediaKind.VIDEO_CARD
    assert cards[0].title == "YouTube video dQw4w9WgXcQ"
    assert cards[0].thumbnail_url.endswith("/dQw4w9WgXcQ/hqdefault.jpg")
    assert cards[0].visible_url is None


@pytest.mark.asyncio
async def test_social_link_gets_provider_fallback_card():
    resolver = MediaResolver(fetch_external_metadata=False)

    result = await resolver.resolve(
        content="New post https://x.com/openai/status/12345",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    assert result.media_items[0].provider == "X"
    assert result.media_items[0].kind == MediaKind.SOCIAL_CARD
    assert result.media_items[0].title == "X post"
    assert result.media_items[0].visible_url is None

