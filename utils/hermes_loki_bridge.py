from __future__ import annotations

import re


def normalize_hermes_prompt(prompt: str) -> str:
    cleaned = " ".join((prompt or "").strip().split())
    if not cleaned:
        return "Hermes operator says: status check."
    return f"Hermes operator says: {cleaned}"


def should_post_transcript_to_discord(*, channel_id: str | None, post: bool) -> bool:
    return bool(post and (channel_id or "").strip())


def transcript_message(prompt: str, answer: str) -> str:
    prompt = normalize_hermes_prompt(prompt).removeprefix("Hermes operator says: ").strip()
    answer = (answer or "").strip() or "No response text."
    return f"**Hermes ⇄ LOKI**\n**Hermes:** {prompt}\n**LOKI:** {answer[:1500]}"


def chunk_discord_text(text: str, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:limit])
        remaining = remaining[limit:]
    return chunks


def legacy_bot_search_terms() -> re.Pattern[str]:
    return re.compile(r"\b(loki|ralph|carlclone|carl\s*clone|sun\s*god)\b", re.IGNORECASE)
