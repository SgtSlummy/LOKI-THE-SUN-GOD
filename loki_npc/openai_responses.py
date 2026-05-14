from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from loki_npc.memory import redact_discord_content

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
MAX_HERMES_QUERY_CHARS = 8_000


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


def hermes_fallback_enabled() -> bool:
    return os.getenv("LOKI_NPC_HERMES_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}


def hosted_brain_missing_message() -> str:
    return (
        "My hosted NPC brain is not configured in this runtime yet. "
        "An operator needs to set OPENAI_API_KEY, OPENAI_BASE_URL, and LOKI_LLM_MODEL "
        "for the Railway worker, or install/configure the Hermes CLI inside the worker image."
    )


def _resolve_hermes_executable() -> str | None:
    found = shutil.which("hermes")
    if not found:
        return None
    return str(Path(found).expanduser().resolve())


def _sanitize_hermes_query(query: str) -> str:
    cleaned = "".join(ch for ch in query if ch in "\n\r\t" or ord(ch) >= 32)
    return cleaned.strip()[:MAX_HERMES_QUERY_CHARS]


def _hermes_subprocess_env(hermes_path: str) -> dict[str, str]:
    allowed_names = (
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATHEXT",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
    )
    env = {name: value for name in allowed_names if (value := os.getenv(name))}
    path_entries = [str(Path(hermes_path).parent)]
    if os.name == "nt":
        system_root = os.getenv("SystemRoot")
        if system_root:
            path_entries.extend([str(Path(system_root) / "System32"), system_root])
    else:
        path_entries.extend(["/usr/local/bin", "/usr/bin", "/bin"])
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_entries))
    env["NO_COLOR"] = "1"
    return env


def ask_hermes_cli(*, prompt: str, persona: str, memory_context: list[str] | None = None) -> str:
    context = "\n".join(f"- {redact_discord_content(item)}" for item in (memory_context or []) if item.strip())
    query = (
        "You are LOKI THE SUN GOD speaking through Hermes for a Discord community. "
        "Respond naturally, do not reveal secrets, and do not claim admin actions happened "
        "unless tools verified them.\n\n"
        f"Persona: {persona}\n"
    )
    if context:
        query += f"Relevant public community memory:\n{context}\n"
    query += f"Hermes operator prompt: {redact_discord_content(prompt)}"
    hermes_path = _resolve_hermes_executable()
    if hermes_path is None:
        return hosted_brain_missing_message()
    query = _sanitize_hermes_query(query)
    if not query:
        return hosted_brain_missing_message()
    try:
        result = subprocess.run(
            [hermes_path, "chat", "-Q", "-q", query],
            capture_output=True,
            env=_hermes_subprocess_env(hermes_path),
            text=True,
            timeout=90,
            check=True,
        )
    except FileNotFoundError:
        return hosted_brain_missing_message()
    answer = (result.stdout or "").strip()
    return answer or "Hermes returned no text."


async def ask_npc(*, prompt: str, persona: str, memory_context: list[str] | None = None) -> str:
    import aiohttp

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        if hermes_fallback_enabled():
            return ask_hermes_cli(prompt=prompt, persona=persona, memory_context=memory_context)
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
