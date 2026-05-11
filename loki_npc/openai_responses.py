from __future__ import annotations

import os
from typing import Any

from loki_npc.memory import redact_discord_content

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def configured_model() -> str:
    return (os.getenv("LOKI_LLM_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def configured_base_url() -> str:
    return (os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")


def build_responses_payload(
    *,
    user_prompt: str,
    persona: str,
    memory_context: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    context = "\n".join(f"- {redact_discord_content(item)}" for item in (memory_context or []) if item.strip())
    system = (
        "You are LOKI THE SUN GOD, a Discord NPC. Respond to users naturally, do not claim sentience, "
        "do not reveal secrets, and never change Discord settings unless a server-side admin permission "
        "check has already authorized a tool call.\n\n"
        f"Generated personality: {persona}"
    )
    if context:
        system += f"\n\nRelevant public community memory:\n{context}"
    return {
        "model": model or configured_model(),
        "store": False,
        "reasoning": {"effort": "low"},
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": redact_discord_content(user_prompt)},
        ],
    }


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


async def ask_npc(*, prompt: str, persona: str, memory_context: list[str] | None = None) -> str:
    import aiohttp

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = build_responses_payload(user_prompt=prompt, persona=persona, memory_context=memory_context)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{configured_base_url()}/responses", headers=headers, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"OpenAI Responses request failed with HTTP {response.status}: {data}")
    if not isinstance(data, dict):
        raise RuntimeError("OpenAI Responses API returned an unexpected payload.")
    return extract_output_text(data) or "I heard you, but the model returned no text."
