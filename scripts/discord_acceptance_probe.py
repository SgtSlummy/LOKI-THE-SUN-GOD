from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import runtime_paths  # noqa: E402

DISCORD_API = "https://discord.com/api/v10"
CORE_PERMISSION_BITS = {
    "ADMINISTRATOR": 1 << 3,
    "VIEW_CHANNEL": 1 << 10,
    "SEND_MESSAGES": 1 << 11,
    "MANAGE_MESSAGES": 1 << 13,
    "EMBED_LINKS": 1 << 14,
    "ATTACH_FILES": 1 << 15,
    "READ_MESSAGE_HISTORY": 1 << 16,
    "CONNECT": 1 << 20,
    "SPEAK": 1 << 21,
    "USE_APPLICATION_COMMANDS": 1 << 31,
}
TEXT_CHANNEL_TYPES = {0, 5, 10, 11, 12, 15, 16}
VOICE_CHANNEL_TYPES = {2, 13}


@dataclass(frozen=True)
class Capability:
    name: str
    mode: str
    reason: str
    automation_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": self.mode,
            "reason": self.reason,
            "automation_path": self.automation_path,
        }


class DiscordAPIError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail: str):
        super().__init__(f"{method} {path} failed with HTTP {status}: {detail}")
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail


class DiscordClient:
    def __init__(self, token: str, *, dry_run: bool = False):
        self.token = token.strip()
        self.dry_run = dry_run

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        url = DISCORD_API + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bot {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "LOKI acceptance probe",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise DiscordAPIError(method, path, exc.code, detail) from exc


def acceptance_capabilities() -> list[Capability]:
    return [
        Capability(
            name="bot_token_identity",
            mode="automated",
            reason="Discord bot tokens can verify the bot account through /users/@me.",
            automation_path="REST GET /users/@me.",
        ),
        Capability(
            name="guild_channel_permissions",
            mode="automated",
            reason="Bot-visible guild, role, channel, and overwrite state is available through REST.",
            automation_path="REST guild/member/channel probes plus local permission-bit evaluation.",
        ),
        Capability(
            name="slash_command_registration",
            mode="automated",
            reason="Registered application commands are readable through the application-command REST API.",
            automation_path="REST GET application global and guild command endpoints.",
        ),
        Capability(
            name="dashboard_health_and_link",
            mode="automated",
            reason="Dashboard URLs are normal HTTP surfaces and /dashboard command output is code-testable.",
            automation_path="HTTP health probes plus in-process command callback tests.",
        ),
        Capability(
            name="npc_message_reply",
            mode="automated_substitute",
            reason=(
                "Bots correctly ignore bot/webhook authors, so a bot token cannot produce "
                "a real non-bot user message."
            ),
            automation_path=(
                "Unit-test LokiNpc.on_message with fake non-bot messages; REST-check channel "
                "permissions; optionally post a bot-authored probe message only to verify send/delete."
            ),
        ),
        Capability(
            name="music_queue_fallback",
            mode="automated_substitute",
            reason=(
                "The command callback and Lavalink-unavailable fallback can be tested without "
                "a Discord voice client."
            ),
            automation_path="In-process command/cog tests and optional Lavalink/dashboard health probes.",
        ),
        Capability(
            name="real_user_slash_invocation",
            mode="human_or_test_client_required",
            reason="Discord bot tokens cannot create Discord user interactions or invoke their own slash commands.",
            automation_path=(
                "Use a separate Discord test client operated by a real user account, or accept "
                "callback-level tests plus REST registration probes as the safe automated substitute."
            ),
        ),
        Capability(
            name="audible_voice_playback",
            mode="human_or_test_client_required",
            reason=(
                "A bot can verify Connect/Speak permissions, but only a separate listener can "
                "confirm audio was actually heard."
            ),
            automation_path=(
                "Use a separate Discord test client/listener in a staging guild; otherwise verify "
                "voice-channel permissions and Lavalink readiness automatically."
            ),
        ),
    ]


def mask_token(token: str) -> str:
    token = token.strip()
    if len(token) <= 10:
        return "<set>"
    prefix = token[:4]
    suffix = token[-4:]
    return f"{prefix}...{suffix}"


def permission_names(value: int) -> list[str]:
    if value & CORE_PERMISSION_BITS["ADMINISTRATOR"]:
        return ["ADMINISTRATOR", *[name for name in CORE_PERMISSION_BITS if name != "ADMINISTRATOR"]]
    return [name for name, bit in CORE_PERMISSION_BITS.items() if value & bit]


def _snowflake(value: str | None, *, name: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise SystemExit(f"{name} must be a Discord snowflake integer, got {value!r}")
    return int(value)


def _role_map(guild: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(role["id"]): role for role in guild.get("roles", [])}


def member_base_permissions(guild: dict[str, Any], member: dict[str, Any]) -> int:
    guild_id = int(guild["id"])
    roles = _role_map(guild)
    everyone = roles.get(guild_id, {})
    permissions = int(everyone.get("permissions", "0"))
    for role_id_raw in member.get("roles", []):
        role = roles.get(int(role_id_raw))
        if role:
            permissions |= int(role.get("permissions", "0"))
    if permissions & CORE_PERMISSION_BITS["ADMINISTRATOR"]:
        return permissions
    return permissions


def channel_permissions(guild: dict[str, Any], member: dict[str, Any], channel: dict[str, Any]) -> int:
    permissions = member_base_permissions(guild, member)
    if permissions & CORE_PERMISSION_BITS["ADMINISTRATOR"]:
        return permissions
    guild_id = int(guild["id"])
    member_role_ids = {int(role_id) for role_id in member.get("roles", [])}
    overwrites = channel.get("permission_overwrites", [])

    everyone = next(
        (ow for ow in overwrites if int(ow.get("id", 0)) == guild_id and int(ow.get("type", -1)) == 0), None
    )
    if everyone:
        permissions &= ~int(everyone.get("deny", "0"))
        permissions |= int(everyone.get("allow", "0"))

    allow = 0
    deny = 0
    for ow in overwrites:
        if int(ow.get("type", -1)) == 0 and int(ow.get("id", 0)) in member_role_ids:
            deny |= int(ow.get("deny", "0"))
            allow |= int(ow.get("allow", "0"))
    permissions &= ~deny
    permissions |= allow

    member_overwrite = next(
        (ow for ow in overwrites if int(ow.get("type", -1)) == 1 and int(ow.get("id", 0)) == int(member["user"]["id"])),
        None,
    )
    if member_overwrite:
        permissions &= ~int(member_overwrite.get("deny", "0"))
        permissions |= int(member_overwrite.get("allow", "0"))
    return permissions


def command_names(commands: list[dict[str, Any]]) -> set[str]:
    return {str(command.get("name", "")) for command in commands if command.get("name")}


def http_probe(url: str) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "LOKI acceptance probe"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {
                "url": url,
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "ok": False,
            "status": exc.code,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def run_probe(args: argparse.Namespace) -> tuple[bool, dict[str, Any]]:
    runtime_paths.load_app_dotenv(override=True)
    token = (args.token or os.getenv("DISCORD_TOKEN") or "").strip()
    guild_id = _snowflake(
        args.guild_id or os.getenv("LOKI_ACCEPTANCE_GUILD_ID") or os.getenv("TEST_GUILD_ID"), name="guild id"
    )
    text_channel_id = _snowflake(
        args.text_channel_id or os.getenv("LOKI_ACCEPTANCE_CHANNEL_ID") or os.getenv("LOKI_JUKEBOX_CHANNEL_ID"),
        name="text channel id",
    )
    voice_channel_id = _snowflake(
        args.voice_channel_id or os.getenv("LOKI_ACCEPTANCE_VOICE_CHANNEL_ID"), name="voice channel id"
    )

    report: dict[str, Any] = {
        "ok": False,
        "token": "missing" if not token else mask_token(token),
        "guild_id": guild_id,
        "text_channel_id": text_channel_id,
        "voice_channel_id": voice_channel_id,
        "capabilities": [capability.to_dict() for capability in acceptance_capabilities()],
        "checks": [],
    }
    checks = report["checks"]

    def add(name: str, ok: bool, detail: str, **extra: Any) -> None:
        item = {"name": name, "ok": ok, "detail": detail}
        item.update(extra)
        checks.append(item)

    if not token:
        add("env.discord_token", False, "DISCORD_TOKEN is required for live Discord probes.")
        return False, report

    client = DiscordClient(token)
    try:
        me = client.request("GET", "/users/@me")
        app_id = int(me["id"])
        add("bot.identity", True, f"Authenticated as {me.get('username')}#{me.get('discriminator', '0')} ({app_id}).")
    except Exception as exc:
        add("bot.identity", False, str(exc))
        return False, report

    if guild_id is None:
        add("env.guild_id", False, "Set TEST_GUILD_ID or LOKI_ACCEPTANCE_GUILD_ID to run guild probes.")
        return False, report

    try:
        guild = client.request("GET", f"/guilds/{guild_id}", query={"with_counts": "true"})
        member = client.request("GET", f"/guilds/{guild_id}/members/{app_id}")
        channels = client.request("GET", f"/guilds/{guild_id}/channels")
        add("guild.reachable", True, f"Guild {guild.get('name')} is reachable with {len(channels)} channels.")
    except Exception as exc:
        add("guild.reachable", False, str(exc))
        return False, report

    base_permissions = member_base_permissions(guild, member)
    add(
        "guild.bot_permissions",
        bool(
            base_permissions & CORE_PERMISSION_BITS["VIEW_CHANNEL"]
            or base_permissions & CORE_PERMISSION_BITS["ADMINISTRATOR"]
        ),
        ", ".join(permission_names(base_permissions)) or "No core permissions decoded.",
        value=str(base_permissions),
    )

    by_id = {int(channel["id"]): channel for channel in channels}
    text_channels = [channel for channel in channels if int(channel.get("type", -1)) in TEXT_CHANNEL_TYPES]
    voice_channels = [channel for channel in channels if int(channel.get("type", -1)) in VOICE_CHANNEL_TYPES]
    add(
        "guild.channel_inventory",
        True,
        f"{len(text_channels)} text-ish channels, {len(voice_channels)} voice/stage channels.",
    )

    if text_channel_id is not None:
        channel = by_id.get(text_channel_id)
        if channel is None:
            add("text_channel.exists", False, f"Text channel {text_channel_id} is not visible to the bot.")
        else:
            perms = channel_permissions(guild, member, channel)
            required = [
                "VIEW_CHANNEL",
                "SEND_MESSAGES",
                "READ_MESSAGE_HISTORY",
                "USE_APPLICATION_COMMANDS",
                "EMBED_LINKS",
            ]
            missing = [name for name in required if not perms & CORE_PERMISSION_BITS[name]]
            add(
                "text_channel.permissions",
                not missing,
                f"#{channel.get('name')} permissions: {', '.join(permission_names(perms)) or 'none'}",
                missing=missing,
                value=str(perms),
            )
            if args.post_probe_message:
                try:
                    message = client.request(
                        "POST",
                        f"/channels/{text_channel_id}/messages",
                        data={
                            "content": (
                                f"LOKI automated acceptance probe {int(time.time())}; "
                                "deleting this message now."
                            ),
                            "allowed_mentions": {"parse": []},
                        },
                    )
                    client.request("DELETE", f"/channels/{text_channel_id}/messages/{message['id']}")
                    add("text_channel.send_delete", True, "Bot can send and delete an acceptance probe message.")
                except Exception as exc:
                    add("text_channel.send_delete", False, str(exc))
    else:
        add(
            "text_channel.configured",
            False,
            "Set LOKI_ACCEPTANCE_CHANNEL_ID or LOKI_JUKEBOX_CHANNEL_ID to test channel send/read permissions.",
        )

    if voice_channel_id is not None:
        channel = by_id.get(voice_channel_id)
        if channel is None:
            add("voice_channel.exists", False, f"Voice channel {voice_channel_id} is not visible to the bot.")
        else:
            perms = channel_permissions(guild, member, channel)
            required = ["VIEW_CHANNEL", "CONNECT", "SPEAK"]
            missing = [name for name in required if not perms & CORE_PERMISSION_BITS[name]]
            add(
                "voice_channel.permissions",
                not missing,
                f"{channel.get('name')} permissions: {', '.join(permission_names(perms)) or 'none'}",
                missing=missing,
                value=str(perms),
            )
    else:
        add(
            "voice_channel.configured",
            False,
            "Set LOKI_ACCEPTANCE_VOICE_CHANNEL_ID to test bot Connect/Speak permissions.",
        )

    try:
        guild_commands = client.request("GET", f"/applications/{app_id}/guilds/{guild_id}/commands")
        global_commands = client.request("GET", f"/applications/{app_id}/commands")
        names = command_names(guild_commands) | command_names(global_commands)
        required = {"ask", "npc", "play", "queue", "stop", "dashboard"}
        missing = sorted(required - names)
        add(
            "commands.registered",
            not missing,
            f"Found {len(names)} command names; required missing: {', '.join(missing) if missing else 'none'}.",
            missing=missing,
            names=sorted(names),
        )
    except Exception as exc:
        add("commands.registered", False, str(exc))

    urls = [url for url in (args.dashboard_url, args.activity_bridge_url) if url]
    for url in urls:
        result = http_probe(url.rstrip("/") + "/healthz")
        add(
            "http.healthz",
            bool(result.get("ok")),
            f"{result['url']} -> {result.get('status', result.get('error'))}",
            probe=result,
        )

    hard_blocks = [
        capability.to_dict()
        for capability in acceptance_capabilities()
        if capability.mode == "human_or_test_client_required"
    ]
    report["safe_automation_boundary"] = hard_blocks
    report["ok"] = all(item["ok"] for item in checks if not item["name"].endswith(".configured"))
    return bool(report["ok"]), report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run safe automated Discord acceptance probes for LOKI with a bot token."
    )
    parser.add_argument("--token", help="Discord bot token; defaults to DISCORD_TOKEN from .env/env.")
    parser.add_argument("--guild-id", help="Guild ID; defaults to LOKI_ACCEPTANCE_GUILD_ID or TEST_GUILD_ID.")
    parser.add_argument(
        "--text-channel-id",
        help="Text channel for permission probes; defaults to LOKI_ACCEPTANCE_CHANNEL_ID or LOKI_JUKEBOX_CHANNEL_ID.",
    )
    parser.add_argument(
        "--voice-channel-id",
        help="Voice channel for Connect/Speak permission probes; defaults to LOKI_ACCEPTANCE_VOICE_CHANNEL_ID.",
    )
    parser.add_argument(
        "--dashboard-url",
        default=os.getenv("DASHBOARD_PUBLIC_URL", ""),
        help="Optional dashboard base URL to probe at /healthz.",
    )
    parser.add_argument(
        "--activity-bridge-url",
        default=os.getenv("ACTIVITY_BRIDGE_PUBLIC_URL", ""),
        help="Optional Activity Bridge base URL to probe at /healthz.",
    )
    parser.add_argument(
        "--post-probe-message",
        action="store_true",
        help="Send and immediately delete a bot-authored text-channel probe message.",
    )
    parser.add_argument("--json", action="store_true", help="Emit full JSON report.")
    args = parser.parse_args()

    ok, report = run_probe(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("LOKI Discord automated acceptance probe")
        for check in report["checks"]:
            print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
        print("Safe automation boundary:")
        for item in report.get("safe_automation_boundary", []):
            print(f"- {item['name']}: {item['reason']} Automation path: {item['automation_path']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
