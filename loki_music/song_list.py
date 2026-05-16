from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class SongListImportError(ValueError):
    """Raised when a pasted song list cannot be safely imported."""


@dataclass(frozen=True)
class SongListEntry:
    query: str
    source_url: str = ""
    provider: str = "manual"

    @property
    def used_spotify_metadata(self) -> bool:
        return self.provider == "spotify" and bool(self.source_url) and self.query != self.source_url


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_URL_RE = re.compile(r"https?://[^\s<>)]+")
_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)]|\[[x ]\])\s*", flags=re.IGNORECASE)
_SPOTIFY_UNSUPPORTED_PATHS = {"album", "playlist", "artist", "show", "episode"}
_MAX_ENTRIES = 50


def _strip_wrapping_punctuation(value: str) -> str:
    return value.strip().strip("<>[](){}.,;!?")


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower()
    return host == domain or host.endswith(f".{domain}")


def _normalize_url(url: str) -> str:
    cleaned = _strip_wrapping_punctuation(url)
    parsed = urlsplit(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned
    host = (parsed.hostname or parsed.netloc).lower()
    if _host_matches(host, "spotify.com"):
        return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", ""))
    return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/"), parsed.query, ""))


def _spotify_kind(url: str) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or parsed.netloc).lower()
    if not _host_matches(host, "spotify.com"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0].lower() if parts else None


def _provider_for_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or parsed.netloc).lower()
    if _host_matches(host, "spotify.com"):
        return "spotify"
    if _host_matches(host, "youtube.com") or host == "youtu.be":
        return "youtube"
    if _host_matches(host, "soundcloud.com"):
        return "soundcloud"
    return "url"


def _clean_label(value: str) -> str:
    cleaned = _PREFIX_RE.sub("", value).strip()
    cleaned = cleaned.strip(' "\'`|:-–—')
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _entry_from_line(line: str) -> SongListEntry | None:
    stripped = _PREFIX_RE.sub("", line).strip()
    if not stripped:
        return None

    markdown = _MARKDOWN_LINK_RE.search(stripped)
    if markdown:
        label = _clean_label(markdown.group(1))
        url = _normalize_url(markdown.group(2))
        provider = _provider_for_url(url)
        if provider == "spotify" and _spotify_kind(url) in _SPOTIFY_UNSUPPORTED_PATHS:
            raise SongListImportError(
                "Spotify playlist expansion is not available yet; paste track titles or track links with titles."
            )
        return SongListEntry(query=label or url, source_url=url, provider=provider)

    urls = [_normalize_url(match.group(0)) for match in _URL_RE.finditer(stripped)]
    if urls:
        first_url = urls[0]
        provider = _provider_for_url(first_url)
        if provider == "spotify" and _spotify_kind(first_url) in _SPOTIFY_UNSUPPORTED_PATHS:
            raise SongListImportError(
                "Spotify playlist expansion is not available yet; paste track titles or track links with titles."
            )
        label = _clean_label(_URL_RE.sub(" ", stripped))
        return SongListEntry(query=label or first_url, source_url=first_url, provider=provider)

    query = _clean_label(stripped)
    return SongListEntry(query=query) if query else None


def parse_song_list(payload: str, *, max_entries: int = _MAX_ENTRIES) -> list[SongListEntry]:
    """Parse a pasted Diva-style song list into safe queue/search entries.

    Spotify track links are treated as metadata: if the pasted line includes a
    markdown or plain-text label, LOKI searches that label through Lavalink
    sources rather than claiming direct Spotify streaming. Spotify playlist and
    album expansion intentionally fail closed until a dedicated resolver exists.
    """

    entries: list[SongListEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_line in str(payload or "").splitlines():
        entry = _entry_from_line(raw_line)
        if entry is None:
            continue
        key = (entry.provider, entry.source_url or entry.query, entry.query)
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
        if len(entries) >= max_entries:
            break

    if not entries:
        raise SongListImportError("Paste one song per line, or paste Diva/Spotify/YouTube/SoundCloud song-list lines.")
    return entries
