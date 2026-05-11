from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse

import aiohttp

URL_RE = re.compile(r"https?://[^\s<]+", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
MUSIC_METADATA_SEPARATOR_RE = re.compile(r"\s+[·•]\s+")
MAX_HTML_BYTES = 256 * 1024
FETCH_TIMEOUT_SECONDS = 5
MAX_REDIRECTS = 3
IMAGE_CONTENT_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
IMAGE_EXTENSIONS = (".gif", ".jpg", ".jpeg", ".png", ".webp")
BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


@dataclass(frozen=True)
class LinkPreview:
    url: str
    title: str
    description: str = ""
    image_url: str | None = None
    site_name: str | None = None

    @property
    def display_name(self) -> str:
        if self.site_name and not urlparse(self.site_name).scheme:
            return self.site_name
        host = urlparse(self.url).hostname or ""
        return host.removeprefix("www.")


def extract_music_artists(preview: LinkPreview) -> str:
    service = f"{preview.site_name or ''} {preview.display_name}".casefold()
    if "spotify" not in service:
        return ""

    description = clean_text(preview.description)
    if not description:
        return ""

    parts = [part for part in MUSIC_METADATA_SEPARATOR_RE.split(description) if part]
    if parts and any(part.casefold() == "song" for part in parts):
        return parts[0]
    if len(parts) >= 2:
        return parts[0]
    if len(description) <= 120 and not urlparse(description).scheme:
        return description
    return ""


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "meta":
            return

        key = (attr_map.get("property") or attr_map.get("name") or "").strip().lower()
        content = clean_text(attr_map.get("content") or "")
        if key and content and key not in self.meta:
            self.meta[key] = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def title(self) -> str:
        return clean_text(" ".join(self._title_parts))


def clean_text(value: str | None) -> str:
    return SPACE_RE.sub(" ", html.unescape(value or "")).strip()


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    urls = []
    for match in URL_RE.finditer(text):
        cleaned = _clean_matched_url(match.group(0))
        if cleaned:
            urls.append(cleaned)
    return urls


def strip_urls(text: str | None) -> str:
    if not text:
        return ""
    stripped = URL_RE.sub(" ", text)
    stripped = re.sub(r"<\s*", " ", stripped)
    return clean_text(stripped)


def is_safe_preview_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False

    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        return False

    try:
        return _is_public_ip(ipaddress.ip_address(host))
    except ValueError:
        return True


async def resolve_link_previews(urls: Iterable[str]) -> list[LinkPreview]:
    urls = list(urls)
    if not urls:
        return []

    previews: list[LinkPreview] = []
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in urls:
            preview = await resolve_link_preview(url, session=session)
            if preview is not None:
                previews.append(preview)
            if len(previews) >= 9:
                break
    return previews


async def resolve_link_preview(url: str, *, session: aiohttp.ClientSession | None = None) -> LinkPreview | None:
    url = _clean_matched_url(url)
    if not is_safe_preview_url(url):
        return None
    if _looks_like_image_url(url):
        return LinkPreview(url=url, title=_domain_title(url), image_url=url, site_name=_domain_title(url))
    if not await _url_resolves_safely(url):
        return None

    owns_session = session is None
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    active_session = session or aiohttp.ClientSession(timeout=timeout)
    try:
        try:
            async with active_session.get(
                url,
                allow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                headers={"User-Agent": "LOKIRelay/1.0 (+https://discord.com)"},
            ) as response:
                final_url = str(response.url)
                if not is_safe_preview_url(final_url) or not await _url_resolves_safely(final_url):
                    return None
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type in IMAGE_CONTENT_TYPES:
                    return LinkPreview(url=final_url, title=_domain_title(final_url), image_url=final_url)
                if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
                    return None
                body = await response.content.read(MAX_HTML_BYTES + 1)
        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
            return None
    finally:
        if owns_session:
            await active_session.close()

    if len(body) > MAX_HTML_BYTES:
        body = body[:MAX_HTML_BYTES]
    html_text = body.decode(response.charset or "utf-8", errors="replace")
    return parse_html_preview(final_url, html_text)


def parse_html_preview(url: str, html_text: str) -> LinkPreview | None:
    parser = _MetadataParser()
    try:
        parser.feed(html_text)
    except Exception:
        return None

    meta = parser.meta
    title = _first_value(meta, "og:title", "twitter:title") or parser.title
    description = _first_value(meta, "og:description", "twitter:description", "description")
    image_url = _first_value(meta, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
    site_name = _first_value(meta, "og:site_name", "application-name")

    title = clean_text(title)
    description = clean_text(description)
    image_url = _normalize_preview_image(url, image_url)
    site_name = clean_text(site_name)

    if _is_login_wall(url, title, description, image_url):
        return None
    if not title and not image_url:
        return None

    return LinkPreview(
        url=url,
        title=title or _domain_title(url),
        description=description,
        image_url=image_url,
        site_name=site_name or None,
    )


def _first_value(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return ""


def _clean_matched_url(url: str) -> str:
    cleaned = (url or "").strip().strip("<>")
    while cleaned and cleaned[-1] in ".,!?;:>":
        cleaned = cleaned[:-1]
    while cleaned.endswith(")") and cleaned.count("(") < cleaned.count(")"):
        cleaned = cleaned[:-1]
    while cleaned.endswith("]") and cleaned.count("[") < cleaned.count("]"):
        cleaned = cleaned[:-1]
    while cleaned.endswith("}") and cleaned.count("{") < cleaned.count("}"):
        cleaned = cleaned[:-1]
    return cleaned


def _normalize_preview_image(base_url: str, image_url: str) -> str | None:
    if not image_url:
        return None
    joined = urljoin(base_url, html.unescape(image_url.strip()))
    return joined if is_safe_preview_url(joined) else None


def _looks_like_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def _domain_title(url: str) -> str:
    host = urlparse(url).hostname or "Link"
    return host.removeprefix("www.")


def _is_login_wall(url: str, title: str, description: str, image_url: str | None) -> bool:
    if image_url:
        return False
    host = (urlparse(url).hostname or "").lower()
    if not any(domain in host for domain in ("facebook.com", "instagram.com", "threads.net")):
        return False
    text = f"{title} {description}".casefold()
    return ("log in" in text or "login" in text or "sign up" in text) and "view" in text


async def _url_resolves_safely(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return _is_public_ip(ip)

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        return False
    return all(_is_public_ip(ipaddress.ip_address(address)) for address in addresses)


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
