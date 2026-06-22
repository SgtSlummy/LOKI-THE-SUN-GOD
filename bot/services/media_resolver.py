from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from bot.models.media import MediaItem, MediaKind, MediaResolution
from bot.services.sanitizer import extract_links, sanitize_message_text

MAX_DISCORD_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif"}
GIF_EXTENSIONS = {".gif"}
DIRECT_IMAGE_RE = re.compile(r"\.(?:jpg|jpeg|png|webp|bmp|avif)(?:\?.*)?$", re.IGNORECASE)
DIRECT_GIF_RE = re.compile(r"\.gif(?:\?.*)?$", re.IGNORECASE)
DIRECT_VIDEO_RE = re.compile(r"\.(?:mp4|mov|webm|m4v)(?:\?.*)?$", re.IGNORECASE)
CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d{15,25})>")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
TENOR_HOSTS = {"tenor.com", "www.tenor.com", "media.tenor.com"}
GIPHY_HOSTS = {"giphy.com", "www.giphy.com", "media.giphy.com", "i.giphy.com"}
SOCIAL_PROVIDERS = {
    "x.com": "X",
    "www.x.com": "X",
    "twitter.com": "X",
    "www.twitter.com": "X",
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "www.tiktok.com": "TikTok",
    "linkedin.com": "LinkedIn",
    "www.linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "www.facebook.com": "Facebook",
    "threads.net": "Threads",
    "www.threads.net": "Threads",
}


class MediaResolver:
    def __init__(self, *, fetch_external_metadata: bool = True, upload_limit_bytes: int = MAX_DISCORD_UPLOAD_BYTES):
        self.fetch_external_metadata = fetch_external_metadata
        self.upload_limit_bytes = upload_limit_bytes

    async def resolve(
        self,
        *,
        content: str | None,
        embeds: list[Any],
        attachments: list[Any],
        stickers: list[Any],
        user_mentions: dict[str, str] | None = None,
        role_mentions: dict[str, str] | None = None,
        channel_mentions: dict[str, str] | None = None,
    ) -> MediaResolution:
        detected_links = extract_links(content)
        clean_text = sanitize_message_text(
            content,
            user_mentions=user_mentions,
            role_mentions=role_mentions,
            channel_mentions=channel_mentions,
        )
        media_items: list[MediaItem] = []

        for attachment in attachments:
            media_items.append(self._attachment_to_media_item(attachment))

        for sticker in stickers:
            item = self._sticker_to_media_item(sticker)
            if item is not None:
                media_items.append(item)

        media_items.extend(self._custom_emojis_to_media_items(content or ""))

        for link in detected_links:
            item = await self._link_to_media_item(link, embeds)
            if item is not None:
                media_items.append(item)

        return MediaResolution(clean_text=clean_text, detected_links=detected_links, media_items=media_items)

    def _attachment_to_media_item(self, attachment: Any) -> MediaItem:
        filename = getattr(attachment, "filename", None) or "attachment"
        content_type = getattr(attachment, "content_type", None)
        size = getattr(attachment, "size", None)
        url = getattr(attachment, "url", None)
        kind = self._classify_attachment(filename, content_type)
        return MediaItem(
            kind=kind,
            source_url=url,
            provider="Discord",
            title=filename,
            filename=filename,
            content_type=content_type,
            size=size,
            uploadable=size is not None and size <= self.upload_limit_bytes,
            metadata={
                "proxy_url": getattr(attachment, "proxy_url", None),
                "description": getattr(attachment, "description", None),
            },
        )

    def _classify_attachment(self, filename: str, content_type: str | None) -> MediaKind:
        lower = filename.lower()
        if content_type == "image/gif" or any(lower.endswith(ext) for ext in GIF_EXTENSIONS):
            return MediaKind.GIF
        if (content_type or "").startswith("image/") or any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return MediaKind.IMAGE
        if (content_type or "").startswith("video/"):
            return MediaKind.VIDEO
        if lower.endswith((".mp4", ".mov", ".webm", ".m4v")):
            return MediaKind.VIDEO
        return MediaKind.FILE

    def _custom_emojis_to_media_items(self, content: str) -> list[MediaItem]:
        items: list[MediaItem] = []
        seen: set[str] = set()
        for match in CUSTOM_EMOJI_RE.finditer(content):
            animated = bool(match.group(1))
            name = match.group(2)
            emoji_id = match.group(3)
            if emoji_id in seen:
                continue
            seen.add(emoji_id)
            extension = "gif" if animated else "png"
            items.append(
                MediaItem(
                    kind=MediaKind.EMOTE,
                    source_url=f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}",
                    provider="Discord",
                    title=name,
                    uploadable=False,
                    metadata={"emoji_id": emoji_id, "animated": animated},
                )
            )
        return items

    def _sticker_to_media_item(self, sticker: Any) -> MediaItem | None:
        url = getattr(sticker, "url", None)
        name = getattr(sticker, "name", None)
        if not url and hasattr(sticker, "cdn_url"):
            url = getattr(sticker, "cdn_url")
        if not url:
            return None
        return MediaItem(
            kind=MediaKind.STICKER,
            source_url=str(url),
            provider="Discord",
            title=name or "Sticker",
            uploadable=False,
        )

    async def _link_to_media_item(self, url: str, embeds: list[Any]) -> MediaItem | None:
        if not self._is_safe_external_url(url):
            return None
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in YOUTUBE_HOSTS:
            return await self._youtube_card(url)
        if host in TENOR_HOSTS:
            return self._moving_media_card(url, "Tenor")
        if host in GIPHY_HOSTS:
            return self._moving_media_card(url, "Giphy")
        if host in SOCIAL_PROVIDERS:
            return await self._social_card(url, SOCIAL_PROVIDERS[host])
        if DIRECT_GIF_RE.search(parsed.path):
            return self._direct_media_item(url, MediaKind.GIF)
        if DIRECT_VIDEO_RE.search(parsed.path):
            return self._direct_media_item(url, MediaKind.VIDEO)
        if DIRECT_IMAGE_RE.search(parsed.path):
            return self._direct_media_item(url, MediaKind.IMAGE)

        embed_card = self._card_from_existing_embeds(url, embeds)
        if embed_card is not None:
            return embed_card
        return await self._generic_card(url)

    def _direct_media_item(self, url: str, kind: MediaKind) -> MediaItem:
        parsed = urlparse(url)
        filename = parsed.path.rsplit("/", 1)[-1] or ("image.gif" if kind == MediaKind.GIF else "image")
        return MediaItem(
            kind=kind,
            source_url=url,
            provider="Direct",
            title=filename,
            filename=filename,
            uploadable=False,
            metadata={"original_url_hash": self._url_hash(url)},
        )

    def _moving_media_card(self, url: str, provider: str) -> MediaItem:
        return MediaItem(
            kind=MediaKind.GIF,
            source_url=url,
            provider=provider,
            title=f"{provider} GIF",
            visible_url=None,
            uploadable=False,
            metadata={"original_url_hash": self._url_hash(url), "moving": True},
        )

    async def _youtube_card(self, url: str) -> MediaItem:
        video_id = self._youtube_video_id(url)
        title = f"YouTube video {video_id}" if video_id else "YouTube video"
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None
        metadata: dict[str, Any] = {"original_url_hash": self._url_hash(url), "video_id": video_id}

        if self.fetch_external_metadata:
            fetched = await self._fetch_json(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
            )
            if fetched:
                title = fetched.get("title") or title
                thumbnail = fetched.get("thumbnail_url") or thumbnail
                metadata["oembed"] = fetched

        return MediaItem(
            kind=MediaKind.VIDEO_CARD,
            source_url=url,
            provider="YouTube",
            title=title,
            thumbnail_url=thumbnail,
            visible_url=None,
            uploadable=False,
            metadata=metadata,
        )

    async def _social_card(self, url: str, provider: str) -> MediaItem:
        metadata: dict[str, Any] = {"original_url_hash": self._url_hash(url)}
        title = f"{provider} post"
        thumbnail_url = None

        if self.fetch_external_metadata:
            fetched = await self._fetch_oembed(url, provider)
            if fetched:
                title = fetched.get("title") or title
                thumbnail_url = fetched.get("thumbnail_url")
                metadata["oembed"] = fetched

        return MediaItem(
            kind=MediaKind.SOCIAL_CARD,
            source_url=url,
            provider=provider,
            title=title,
            thumbnail_url=thumbnail_url,
            visible_url=None,
            uploadable=False,
            metadata=metadata,
        )

    async def _generic_card(self, url: str) -> MediaItem | None:
        if not self.fetch_external_metadata:
            return None
        metadata = await self._fetch_open_graph(url)
        if not metadata:
            return None
        return MediaItem(
            kind=MediaKind.GENERIC_CARD,
            source_url=url,
            provider=metadata.get("site_name") or urlparse(url).netloc,
            title=metadata.get("title") or urlparse(url).netloc,
            thumbnail_url=metadata.get("image"),
            visible_url=None,
            uploadable=False,
            metadata={"original_url_hash": self._url_hash(url), "open_graph": metadata},
        )

    def _card_from_existing_embeds(self, url: str, embeds: list[Any]) -> MediaItem | None:
        for embed in embeds:
            embed_url = getattr(embed, "url", None)
            if embed_url and embed_url != url:
                continue
            title = getattr(embed, "title", None)
            provider = getattr(getattr(embed, "provider", None), "name", None)
            thumbnail = getattr(getattr(embed, "thumbnail", None), "url", None)
            image = getattr(getattr(embed, "image", None), "url", None)
            if title or thumbnail or image:
                return MediaItem(
                    kind=MediaKind.GENERIC_CARD,
                    source_url=url,
                    provider=provider or urlparse(url).netloc,
                    title=title or urlparse(url).netloc,
                    thumbnail_url=thumbnail or image,
                    visible_url=None,
                    uploadable=False,
                    metadata={"original_url_hash": self._url_hash(url), "from_discord_embed": True},
                )
        return None

    def _youtube_video_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in {"youtu.be", "www.youtu.be"}:
            return parsed.path.strip("/").split("/")[0] or None
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id:
            return query_id
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] in {"shorts", "embed"} and len(parts) > 1:
            return parts[1]
        return None

    def _is_safe_external_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").strip().casefold()
        if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return True
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)

    async def _fetch_oembed(self, url: str, provider: str) -> dict[str, Any] | None:
        endpoints = {
            "X": "https://publish.twitter.com/oembed",
            "Instagram": "https://graph.facebook.com/v20.0/instagram_oembed",
            "TikTok": "https://www.tiktok.com/oembed",
        }
        endpoint = endpoints.get(provider)
        if not endpoint:
            return None
        return await self._fetch_json(endpoint, params={"url": url})

    async def _fetch_json(self, url: str, *, params: dict[str, str]) -> dict[str, Any] | None:
        if not self._is_safe_external_url(url):
            return None
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url, params=params) as response:
                    if response.status >= 400:
                        return None
                    data = await response.json(content_type=None)
                    return data if isinstance(data, dict) else None
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None

    async def _fetch_open_graph(self, url: str) -> dict[str, str] | None:
        if not self._is_safe_external_url(url):
            return None
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        return None
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" not in content_type and "application/xhtml" not in content_type:
                        return None
                    html = (await response.content.read(262_144)).decode(response.charset or "utf-8", errors="replace")
        except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError):
            return None

        metadata: dict[str, str] = {}
        for key in ("title", "site_name", "image", "description"):
            match = re.search(
                rf'<meta\s+(?:property|name)=["\']og:{key}["\']\s+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if match:
                metadata[key] = match.group(1)
        if not metadata.get("title"):
            title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
        return metadata or None

    def _url_hash(self, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

