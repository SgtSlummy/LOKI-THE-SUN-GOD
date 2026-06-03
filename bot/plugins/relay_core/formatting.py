from __future__ import annotations

import discord

from bot.models.media import MediaItem, MediaKind
from bot.models.relay import RelayMessage
from bot.settings import Settings

MAX_MESSAGE_CHARS = 2000


def safe_allowed_mentions() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


def build_relay_content(
    relay: RelayMessage,
    *,
    settings: Settings | None = None,
    include_native_links: bool | None = None,
) -> str:
    header = f"**{relay.author_display_name}** — from #{relay.source_channel_name}"
    body_parts = [relay.clean_text] if relay.clean_text else []
    should_include_links = include_native_links
    if should_include_links is None:
        should_include_links = settings is not None and settings.media_mode == "native_unfurl"
    if should_include_links and relay.detected_links:
        body_parts.extend(relay.detected_links)

    body = "\n".join(part for part in body_parts if part).strip()
    content = f"{header}\n{body}" if body else header
    if len(content) <= MAX_MESSAGE_CHARS:
        return content
    return content[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"


def media_cards_to_embeds(media_items: list[MediaItem]) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    for item in media_items:
        if item.kind not in {MediaKind.VIDEO_CARD, MediaKind.SOCIAL_CARD, MediaKind.GENERIC_CARD}:
            continue
        embed = discord.Embed(title=item.title or item.provider or "Media")
        if item.provider:
            embed.set_author(name=f"Provider: {item.provider}")
        if item.thumbnail_url:
            embed.set_thumbnail(url=item.thumbnail_url)
        if item.metadata.get("description"):
            embed.description = str(item.metadata["description"])[:4096]
        embeds.append(embed)
    return embeds[:10]


def image_links_to_embeds(media_items: list[MediaItem]) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    for item in media_items:
        if item.kind not in {MediaKind.IMAGE, MediaKind.GIF} or item.uploadable:
            continue
        if not item.source_url:
            continue
        embed = discord.Embed(title=item.title or item.filename or "Media")
        embed.set_image(url=item.source_url)
        embeds.append(embed)
    return embeds[:10]


def build_media_link_view(media_items: list[MediaItem], *, enabled: bool) -> discord.ui.View | None:
    if not enabled:
        return None
    view = discord.ui.View(timeout=None)
    added = 0
    for item in media_items:
        if item.source_url and item.kind in {MediaKind.VIDEO_CARD, MediaKind.SOCIAL_CARD, MediaKind.GENERIC_CARD}:
            view.add_item(discord.ui.Button(label="Open media", style=discord.ButtonStyle.link, url=item.source_url))
            added += 1
        if added >= 5:
            break
    return view if added else None


def components_v2_supported() -> bool:
    return hasattr(discord.ui, "MediaGallery") and hasattr(discord.ui, "LayoutView")

