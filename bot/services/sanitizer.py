from __future__ import annotations

import re

URL_RE = re.compile(r"https?://[^\s<>\])]+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", re.IGNORECASE)
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")


def _clean_url(url: str) -> str:
    return url.rstrip(".,!?;:")


def extract_links(text: str | None) -> list[str]:
    if not text:
        return []
    links: list[str] = []
    seen: set[str] = set()

    for match in MARKDOWN_LINK_RE.finditer(text):
        url = _clean_url(match.group(2))
        if url not in seen:
            links.append(url)
            seen.add(url)

    for match in URL_RE.finditer(text):
        url = _clean_url(match.group(0))
        if url not in seen:
            links.append(url)
            seen.add(url)

    return links


def _replace_markdown_link(match: re.Match[str]) -> str:
    return match.group(1)


def neutralize_mentions(
    text: str,
    *,
    user_mentions: dict[str, str] | None = None,
    role_mentions: dict[str, str] | None = None,
    channel_mentions: dict[str, str] | None = None,
) -> str:
    user_mentions = user_mentions or {}
    role_mentions = role_mentions or {}
    channel_mentions = channel_mentions or {}

    def user_replacement(match: re.Match[str]) -> str:
        user_id = match.group(1)
        return user_mentions.get(user_id, f"user {user_id}")

    def role_replacement(match: re.Match[str]) -> str:
        role_id = match.group(1)
        return role_mentions.get(role_id, f"role {role_id}")

    def channel_replacement(match: re.Match[str]) -> str:
        channel_id = match.group(1)
        return f"#{channel_mentions.get(channel_id, f'channel-{channel_id}')}"

    text = re.sub(r"@(everyone|here)\b", r"\1", text, flags=re.IGNORECASE)
    text = USER_MENTION_RE.sub(user_replacement, text)
    text = ROLE_MENTION_RE.sub(role_replacement, text)
    text = CHANNEL_MENTION_RE.sub(channel_replacement, text)
    return text


def sanitize_message_text(
    text: str | None,
    *,
    user_mentions: dict[str, str] | None = None,
    role_mentions: dict[str, str] | None = None,
    channel_mentions: dict[str, str] | None = None,
) -> str:
    if not text:
        return ""
    clean = MARKDOWN_LINK_RE.sub(_replace_markdown_link, text)
    clean = URL_RE.sub("", clean)
    clean = neutralize_mentions(
        clean,
        user_mentions=user_mentions,
        role_mentions=role_mentions,
        channel_mentions=channel_mentions,
    )
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\s+\n", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = re.sub(r"\s+([.,!?;:])", r"\1", clean)
    return clean.strip()

