from types import SimpleNamespace

import pytest

from bot.models.media import MediaKind
from bot.services.media_resolver import MediaResolver


@pytest.mark.asyncio
async def test_video_attachment_is_normalized_as_moving_media():
    resolver = MediaResolver(fetch_external_metadata=False)
    attachment = SimpleNamespace(
        id=2,
        url="https://cdn.discordapp.com/attachments/1/clip.mp4",
        proxy_url=None,
        filename="clip.mp4",
        content_type="video/mp4",
        size=256_000,
        description=None,
    )

    result = await resolver.resolve(content="", embeds=[], attachments=[attachment], stickers=[])

    assert result.media_items[0].kind == MediaKind.VIDEO
    assert result.media_items[0].uploadable is True


@pytest.mark.asyncio
async def test_tenor_and_giphy_links_become_moving_media_cards_without_visible_raw_url():
    resolver = MediaResolver(fetch_external_metadata=False)

    result = await resolver.resolve(
        content="funny https://tenor.com/view/cat-gif-123 and https://giphy.com/gifs/dance-456",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    assert "https://" not in result.clean_text
    providers = {item.provider for item in result.media_items}
    assert {"Tenor", "Giphy"}.issubset(providers)
    assert all(item.kind == MediaKind.GIF for item in result.media_items)
    assert all(item.visible_url is None for item in result.media_items)


@pytest.mark.asyncio
async def test_direct_video_link_becomes_video_media_without_visible_raw_url():
    resolver = MediaResolver(fetch_external_metadata=False)

    result = await resolver.resolve(
        content="clip https://example.com/video.webm?download=1",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    assert "https://" not in result.clean_text
    assert result.media_items[0].kind == MediaKind.VIDEO
    assert result.media_items[0].provider == "Direct"


@pytest.mark.asyncio
async def test_custom_static_and_animated_emoji_tokens_are_detected_as_emote_media():
    resolver = MediaResolver(fetch_external_metadata=False)

    result = await resolver.resolve(
        content="party <:party:123456789012345678> dance <a:dance:987654321098765432>",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    emotes = [item for item in result.media_items if item.kind == MediaKind.EMOTE]
    assert [item.title for item in emotes] == ["party", "dance"]
    assert emotes[0].metadata["animated"] is False
    assert emotes[1].metadata["animated"] is True
    assert emotes[0].source_url.endswith("/123456789012345678.png")
    assert emotes[1].source_url.endswith("/987654321098765432.gif")


@pytest.mark.asyncio
async def test_private_and_local_urls_are_not_fetched_or_relayed_as_media():
    resolver = MediaResolver(fetch_external_metadata=True)

    result = await resolver.resolve(
        content="unsafe http://127.0.0.1/admin and http://192.168.1.10/status",
        embeds=[],
        attachments=[],
        stickers=[],
    )

    assert "http://" not in result.clean_text
    assert result.media_items == []
