from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import runtime_paths  # noqa: E402
from utils.discord_migration import (  # noqa: E402
    bot_role_delta,
    identify_old_loki_bot,
    render_legacy_bot_report,
)

API = "https://discord.com/api/v10"


def _request(method: str, endpoint: str, *, token: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{API}{endpoint}",
        data=data,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "LOKI legacy bot migration",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def _safe_request(method: str, endpoint: str, *, token: str, payload: dict[str, Any] | None = None) -> tuple[bool, Any]:
    try:
        return True, _request(method, endpoint, token=token, payload=payload)
    except urllib.error.HTTPError as exc:
        return False, {"status": exc.code, "body": exc.read().decode("utf-8", errors="replace")[:500]}


def _fetch_recent_bot_messages(*, token: str, channels: list[dict[str, Any]], old_bot_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for channel in channels:
        if channel.get("type") not in {0, 5, 10, 11, 12, 15}:
            continue
        ok, data = _safe_request("GET", f"/channels/{channel['id']}/messages?limit=50", token=token)
        if not ok or not isinstance(data, list):
            continue
        for message in data:
            author = message.get("author") or {}
            if str(author.get("id")) == str(old_bot_id):
                messages.append(
                    {
                        "id": message.get("id"),
                        "channel_id": channel.get("id"),
                        "channel_name": channel.get("name"),
                        "timestamp": message.get("timestamp"),
                        "content": message.get("content") or "",
                    }
                )
    return messages


def run(*, execute: bool, output_path: Path | None = None) -> dict[str, Any]:
    runtime_paths.load_app_dotenv(override=False)
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    guild_id = (os.getenv("TEST_GUILD_ID") or os.getenv("RELAY_GUILD_ID") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")
    if not guild_id:
        raise RuntimeError("TEST_GUILD_ID or RELAY_GUILD_ID is required.")

    guild = _request("GET", f"/guilds/{guild_id}?with_counts=true", token=token)
    roles = _request("GET", f"/guilds/{guild_id}/roles", token=token)
    channels = _request("GET", f"/guilds/{guild_id}/channels", token=token)
    current_bot = _request("GET", "/users/@me", token=token)
    members = _request("GET", f"/guilds/{guild_id}/members?limit=1000", token=token)
    roles_by_id = {str(role["id"]): role for role in roles}
    current_member = next(
        member for member in members if str((member.get("user") or {}).get("id")) == str(current_bot["id"])
    )
    old_bot = identify_old_loki_bot(members, current_bot_id=str(current_bot["id"]))
    if old_bot is None:
        raise RuntimeError("Could not identify an old LOKI/Ralph/CarlClone bot in this guild.")

    old_bot_id = str((old_bot.get("user") or {}).get("id"))
    roles_to_assume = bot_role_delta(
        old_role_ids=[str(role_id) for role_id in old_bot.get("roles", [])],
        current_role_ids=[str(role_id) for role_id in current_member.get("roles", [])],
    )
    old_messages = _fetch_recent_bot_messages(token=token, channels=channels, old_bot_id=old_bot_id)
    actions: list[dict[str, Any]] = []
    if execute:
        for role_id in roles_to_assume:
            ok, data = _safe_request(
                "PUT",
                f"/guilds/{guild_id}/members/{current_bot['id']}/roles/{role_id}",
                token=token,
            )
            actions.append({"action": "assign_role", "role_id": role_id, "ok": ok, "response": data})
        ok, data = _safe_request("DELETE", f"/guilds/{guild_id}/members/{old_bot_id}", token=token)
        actions.append({"action": "remove_legacy_bot", "bot_id": old_bot_id, "ok": ok, "response": data})

    report = render_legacy_bot_report(
        guild_name=str(guild.get("name") or guild_id),
        old_bot=old_bot,
        current_bot=current_member,
        roles_by_id=roles_by_id,
        old_messages=old_messages,
        roles_to_assume=roles_to_assume,
        executed=execute,
    )
    if actions:
        lines = []
        for action in actions:
            target = action.get("role_id") or action.get("bot_id")
            status = "ok" if action["ok"] else "failed"
            lines.append(f"- {action['action']} {target}: {status} {action['response']}")
        report += "\n## Discord API Action Results\n" + "\n".join(lines) + "\n"
    output_path = output_path or runtime_paths.app_path("data", "legacy_bot_takeover_report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return {
        "output_path": str(output_path),
        "old_bot_id": old_bot_id,
        "roles_to_assume": roles_to_assume,
        "actions": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Research and optionally remove old LOKI Discord bot after role takeover."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Assign legacy roles to current LOKI and remove the legacy bot",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = run(execute=args.execute, output_path=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
