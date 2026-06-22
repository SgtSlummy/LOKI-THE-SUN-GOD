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
        should_include_links = False
    if should_include_links and relay.detected_links:
        body_parts.extend(relay.detected_links)

    body = "\n".join(part for part in body_parts if part).strip()
    content = f"{header}\n{body}" if body else header
    if len(content) <= MAX_MESSAGE_CHARS:
        return content
    return content[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"




def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"

def build_relay_embeds(relay: RelayMessage) -> list[discord.Embed]:
    title = f"Message from #{relay.source_channel_name}"
    if relay.media_items:
        first_title = relay.media_items[0].title
        if first_title:
            title = first_title
    embed = discord.Embed(
        title=_truncate(title, 256),
        description=_truncate(relay.clean_text, 4096) if relay.clean_text else None,
        timestamp=relay.created_at,
    )
    if relay.author_display_name:
        embed.set_author(name=_truncate(relay.author_display_name, 256), icon_url=relay.author_avatar_url or None)
    embed.add_field(name="Source", value=f"#{relay.source_channel_name}", inline=True)
    embed.add_field(name="Original poster", value=_truncate(relay.author_display_name, 1024), inline=True)
    embed.add_field(name="Original", value=f"[Jump to message]({relay.source_message_url})", inline=False)
    if relay.attachments:
        embed.add_field(name="Attachments", value=str(len(relay.attachments)), inline=True)
    embed.set_footer(text="Relayed by Loki")
    return [embed]

def media_cards_to_embeds(media_items: list[MediaItem]) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    for item in media_items:
        if item.kind not in {MediaKind.VIDEO_CARD, MediaKind.SOCIAL_CARD, MediaKind.GENERIC_CARD}:
            continue
        embed = discord.Embed(title=_truncate(item.title or item.provider or "Media", 256), url=item.source_url)
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
        embed = discord.Embed(title=_truncate(item.title or item.filename or "Media", 256), url=item.source_url)
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

