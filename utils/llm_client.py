from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import aiohttp

from loki_npc.memory import redact_discord_content

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TAROT_ROUTER_BASE_URL = "http://127.0.0.1:8642/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_MAX_PROMPT_CHARS = 1800
DEFAULT_MAX_COMPLETION_TOKENS = 500
DISCORD_MESSAGE_LIMIT = 1900
TRUTHY = {"1", "true", "yes", "on"}


class LLMConfigError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


def tarot_router_enabled() -> bool:
    return os.getenv("TAROT_ROUTER_ENABLED", "false").strip().lower() in TRUTHY


def openai_base_url() -> str:
    if tarot_router_enabled():
        return (os.getenv("TAROT_ROUTER_BASE_URL") or DEFAULT_TAROT_ROUTER_BASE_URL).strip().rstrip("/")
    return (os.getenv("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")


def configured_api_key() -> str:
    if tarot_router_enabled():
        return (os.getenv("TAROT_ROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").casefold() in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def configured_model() -> str:
    return (os.getenv("LOKI_LLM_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def max_prompt_chars() -> int:
    try:
        return max(100, min(6000, int(os.getenv("LOKI_LLM_MAX_PROMPT_CHARS", DEFAULT_MAX_PROMPT_CHARS))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_PROMPT_CHARS


def max_completion_tokens() -> int:
    try:
        return max(64, min(2000, int(os.getenv("LOKI_LLM_MAX_COMPLETION_TOKENS", DEFAULT_MAX_COMPLETION_TOKENS))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_COMPLETION_TOKENS


def sanitize_prompt(prompt: str) -> str:
    clean = redact_discord_content(" ".join((prompt or "").split()))
    limit = max_prompt_chars()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip()


def discord_safe_chunks(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    clean = (text or "").strip() or "The model returned an empty response."
    chunks = []
    while clean:
        chunks.append(clean[:limit])
        clean = clean[limit:]
    return chunks


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise LLMProviderError("The LLM provider returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        content = "\n".join(part for part in parts if part)
    if not content:
        raise LLMProviderError("The LLM provider returned an empty response.")
    return str(content).strip()


async def ask_loki_llm(prompt: str) -> str:
    base_url = openai_base_url()
    key = configured_api_key()
    if not key and not (tarot_router_enabled() and _loopback_url(base_url)):
        raise LLMConfigError("OPENAI_API_KEY is not configured. Add it in AI and Router Settings.")

    clean_prompt = sanitize_prompt(prompt)
    if not clean_prompt:
        raise LLMConfigError("Prompt is required.")

    body = {
        "model": configured_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are LOKI THE SUN GOD, a concise Discord server assistant. "
                    "Answer clearly, avoid secrets, and keep replies suitable for Discord."
                ),
            },
            {"role": "user", "content": clean_prompt},
        ],
        "max_completion_tokens": max_completion_tokens(),
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/chat/completions", json=body, headers=headers) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    error = data.get("error") if isinstance(data, dict) else None
                    detail = error.get("message") if isinstance(error, dict) else str(data)
                    raise LLMProviderError(f"LLM provider returned HTTP {response.status}: {detail}")
    except aiohttp.ClientError as exc:
        raise LLMProviderError(f"LLM provider request failed: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("The LLM provider returned an unexpected response.")
    return _extract_chat_content(data)
