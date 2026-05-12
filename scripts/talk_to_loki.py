from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loki_npc.memory import recent_public_memory  # noqa: E402
from loki_npc.openai_responses import ask_npc  # noqa: E402
from loki_npc.persona import persona_from_settings  # noqa: E402
from utils import db, runtime_paths  # noqa: E402
from utils.hermes_loki_bridge import (  # noqa: E402
    chunk_discord_text,
    normalize_hermes_prompt,
    should_post_transcript_to_discord,
    transcript_message,
)


def _discord_post(channel_id: str, content: str) -> None:
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "LOKI Hermes bridge",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status >= 300:
            raise RuntimeError(f"Discord post failed with HTTP {response.status}")


async def _ask(prompt: str, *, guild_id: int | None) -> str:
    await db.init()
    persona = persona_from_settings(guild_id or 0, "")
    memory = recent_public_memory(guild_id) if guild_id else []
    return await ask_npc(prompt=normalize_hermes_prompt(prompt), persona=persona.prompt_text(), memory_context=memory)


def main() -> int:
    runtime_paths.load_app_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Talk to LOKI directly from Hermes/terminal.")
    parser.add_argument("prompt", nargs="*", help="Message to send to LOKI")
    parser.add_argument(
        "--guild-id",
        type=int,
        default=int(os.getenv("TEST_GUILD_ID") or "0"),
        help="Guild context for memory/persona",
    )
    parser.add_argument(
        "--post-channel-id",
        default=os.getenv("LOKI_HERMES_DISCORD_CHANNEL_ID", ""),
        help="Optional Discord channel to post the transcript",
    )
    parser.add_argument("--post", action="store_true", help="Post Hermes/LOKI transcript to Discord")
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        prompt = input("Hermes to LOKI> ").strip()
    answer = asyncio.run(_ask(prompt, guild_id=args.guild_id or None))
    print(answer)
    if should_post_transcript_to_discord(channel_id=args.post_channel_id, post=args.post):
        for chunk in chunk_discord_text(transcript_message(prompt, answer)):
            _discord_post(args.post_channel_id, chunk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
