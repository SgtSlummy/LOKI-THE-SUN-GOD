from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from loki_activity_bridge import ActivityBridgeClient
from utils import db as shared_db
from utils import runtime_paths
from utils.command_catalog import parse_command_catalog as shared_parse_command_catalog

RESOURCE_ROOT = runtime_paths.bundle_root()
APP_ROOT = runtime_paths.app_root()
DOCS_PATH = runtime_paths.bundle_path("docs")
AI_DOCS_PATH = DOCS_PATH / "ai_library"
CODEX_SETTINGS_PATH = Path.home() / ".Codex" / "settings.json"
ENV_PATH = runtime_paths.app_path(".env")
RUNTIME_LOG_PATH = runtime_paths.app_path("desktop_runtime.log")
WINDOWS_HOME_PATH = Path(os.getenv("USERPROFILE", "")).expanduser() if os.getenv("USERPROFILE") else None
ROUTER_REPO_PATH = (
    WINDOWS_HOME_PATH / "OneDrive" / "Desktop" / "Codex" / "9router"
    if WINDOWS_HOME_PATH
    else Path.home() / "OneDrive" / "Desktop" / "Codex" / "9router"
)
ROUTER_ENV_PATH = ROUTER_REPO_PATH / ".env"
ROUTER_ENV_EXAMPLE_PATH = ROUTER_REPO_PATH / ".env.example"
OLLAMA_HOST_DEFAULT = "http://127.0.0.1:11434"
LOCAL_MODEL_PREFERENCES = ("qwen2.5-coder:7b", "llama3.1:8b", "llama3.2:3b")
LOCAL_MODEL_ALIAS = "local-default"
MEMPALACE_ROOT = Path.home() / ".mempalace"
MEMPALACE_CONFIG_PATH = MEMPALACE_ROOT / "config.json"
MEMPALACE_FALLBACK_MEMORY_PATH = (
    Path.home() / "OneDrive" / "Desktop" / "Codex" / "ai-research-database-pack" / "memory.md"
)


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value and name != "LOKI_ENV_PATH":
        value = read_env_file_at(ENV_PATH).get(name)
    return Path(value) if value else default


def db_path() -> Path:
    return _path_from_env("LOKI_DB_PATH", shared_db.current_db_path())


def docs_path() -> Path:
    return _path_from_env("LOKI_DOCS_PATH", DOCS_PATH)


def ai_docs_path() -> Path:
    override = os.getenv("LOKI_AI_DOCS_PATH")
    if override:
        return Path(override)
    return docs_path() / "ai_library"


def codex_settings_path() -> Path:
    return _path_from_env("LOKI_CODEX_SETTINGS_PATH", CODEX_SETTINGS_PATH)


def env_path() -> Path:
    return _path_from_env("LOKI_ENV_PATH", ENV_PATH)


def runtime_log_path() -> Path:
    return _path_from_env("LOKI_RUNTIME_LOG_PATH", RUNTIME_LOG_PATH)


def command_root() -> Path:
    return _path_from_env("LOKI_COMMAND_ROOT", RESOURCE_ROOT)


def router_repo_path() -> Path:
    return _path_from_env("LOKI_ROUTER_REPO_PATH", ROUTER_REPO_PATH)


def router_env_path() -> Path:
    return _path_from_env("LOKI_ROUTER_ENV_PATH", router_repo_path() / ".env")


def router_env_example_path() -> Path:
    return router_repo_path() / ".env.example"


def mempalace_root_path() -> Path:
    return _path_from_env("LOKI_MEMPALACE_ROOT", MEMPALACE_ROOT)


def mempalace_config_path() -> Path:
    return _path_from_env("LOKI_MEMPALACE_CONFIG_PATH", mempalace_root_path() / "config.json")


def mempalace_fallback_memory_path() -> Path:
    return _path_from_env("LOKI_MEMPALACE_FALLBACK_PATH", MEMPALACE_FALLBACK_MEMORY_PATH)


def db_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if not shared_db.using_postgres() and not db_path().exists():
        return []
    rows = shared_db.sync_all(sql, params)
    return [dict(row) for row in rows]


def db_exec(sql: str, params: tuple = ()) -> int:
    if not shared_db.using_postgres() and not db_path().exists():
        return 0
    return shared_db.sync_exec(sql, params)


def command_library(query: str = "", category: str = "", slash_only: bool = False) -> list[dict[str, Any]]:
    commands = shared_parse_command_catalog(command_root())
    normalized_query = query.strip().lower()
    normalized_category = category.strip().lower()
    if normalized_query:
        commands = [item for item in commands if normalized_query in item.get("search", "")]
    if normalized_category:
        commands = [item for item in commands if item.get("category", "").lower() == normalized_category]
    if slash_only:
        commands = [item for item in commands if item.get("slash_enabled")]
    return commands


def option_library() -> dict[str, list[dict[str, str]]]:
    return {
        "general": [
            {
                "id": "prefix",
                "label": "Prefix",
                "type": "text",
                "effect": "Changes how message commands are invoked in the guild.",
                "example": "!help",
                "route": "",
            },
            {
                "id": "log_channel",
                "label": "Log channel",
                "type": "channel",
                "effect": "Routes moderation and audit events to a single review channel.",
                "route": "",
            },
            {
                "id": "welcome_channel",
                "label": "Welcome channel",
                "type": "channel",
                "effect": "Chooses where welcome flows and onboarding nudges should land.",
                "route": "",
            },
            {
                "id": "starboard_channel",
                "label": "Starboard channel",
                "type": "channel",
                "effect": "Sets the destination for highlighted community posts.",
                "route": "",
            },
            {
                "id": "star_threshold",
                "label": "Star threshold",
                "type": "number",
                "effect": "Controls how many star reactions a post needs before promotion.",
                "route": "",
            },
            {
                "id": "level_enabled",
                "label": "XP leveling",
                "type": "toggle",
                "effect": "Turns message-based progression and level surfacing on or off.",
                "route": "",
            },
        ],
        "automod": [
            {
                "id": "anti_invite",
                "label": "Invite blocking",
                "type": "toggle",
                "effect": "Removes unsolicited Discord invite links before they spread.",
                "route": "",
            },
            {
                "id": "anti_spam",
                "label": "Spam guard",
                "type": "toggle",
                "effect": "Catches flood posting and repeated messages from the same member.",
                "route": "",
            },
            {
                "id": "anti_caps",
                "label": "Caps guard",
                "type": "toggle",
                "effect": "Helps keep chat readable by acting on excessive all-caps posts.",
                "route": "",
            },
            {
                "id": "anti_mention",
                "label": "Mention guard",
                "type": "toggle",
                "effect": "Prevents ping storms and mass mention harassment.",
                "route": "",
            },
            {
                "id": "max_mentions",
                "label": "Max mentions",
                "type": "number",
                "effect": "Sets the mention count that triggers the protection.",
                "route": "",
            },
            {
                "id": "spam_threshold",
                "label": "Spam threshold",
                "type": "number",
                "effect": "Defines how many fast repeats count as spam.",
                "route": "",
            },
            {
                "id": "caps_percent",
                "label": "Caps percent",
                "type": "number",
                "effect": "Defines the uppercase ratio that trips caps protection.",
                "route": "",
            },
        ],
    }


def read_env_file_at(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_env_file() -> dict[str, str]:
    return read_env_file_at(env_path())


def env_value(name: str) -> Optional[str]:
    return os.getenv(name) or read_env_file().get(name)


def _env_line(key: str, value: Any) -> str:
    text = "" if value is None else str(value)
    if any(char.isspace() for char in text) or any(char in text for char in '#"'):
        text = '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{key}={text}"


def write_env_values(path: Path, updates: dict[str, Any], template_path: Optional[Path] = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        base_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    elif template_path and template_path.exists():
        base_lines = template_path.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        base_lines = []

    remaining = dict(updates)
    output: list[str] = []
    for line in base_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output.append(_env_line(key, remaining.pop(key)))
        else:
            output.append(line)

    if remaining and output and output[-1].strip():
        output.append("")
    for key, value in remaining.items():
        output.append(_env_line(key, value))

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return path


def normalize_ollama_host(value: str | None = None) -> str:
    host = (value or env_value("OLLAMA_HOST") or OLLAMA_HOST_DEFAULT).strip().rstrip("/")
    return host or OLLAMA_HOST_DEFAULT


def ollama_openai_base_url(ollama_host: str | None = None) -> str:
    return f"{normalize_ollama_host(ollama_host)}/v1"


def preferred_local_model(models: list[str]) -> dict[str, Any]:
    clean_models = [model for model in models if isinstance(model, str) and model.strip()]
    for candidate in LOCAL_MODEL_PREFERENCES:
        if candidate in clean_models:
            return {
                "preferred_local_model": candidate,
                "local_model_source": "preferred",
                "local_model_ready": True,
            }
    if clean_models:
        return {
            "preferred_local_model": clean_models[0],
            "local_model_source": "installed",
            "local_model_ready": True,
        }
    return {
        "preferred_local_model": "",
        "local_model_source": "missing",
        "local_model_ready": False,
    }


def _default_9router_data_dir(router_env: Optional[dict[str, str]] = None) -> Path:
    env = router_env if router_env is not None else read_env_file_at(router_env_path())
    data_dir = (env.get("DATA_DIR") or os.getenv("DATA_DIR") or "").strip()
    if data_dir:
        return Path(data_dir)
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "9router"
    return Path.home() / ".9router"


def router_db_path(router_env: Optional[dict[str, str]] = None) -> Path:
    return _default_9router_data_dir(router_env) / "db.json"


def configure_9router_local_model(ollama_host: str, model: str) -> dict[str, str]:
    routed_model = f"ollama-local/{model}"
    db_path = router_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        try:
            data = json.loads(db_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    data.setdefault("providerConnections", [])
    data.setdefault("providerNodes", [])
    data.setdefault("proxyPools", [])
    data.setdefault("modelAliases", {})
    data.setdefault("customModels", [])
    data.setdefault("combos", [])
    data.setdefault("apiKeys", [])
    data.setdefault("settings", {})
    data.setdefault("pricing", {})

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    connection = next(
        (item for item in data["providerConnections"] if item.get("provider") == "ollama-local"),
        None,
    )
    connection_data = {
        "provider": "ollama-local",
        "authType": "apikey",
        "name": "Ollama Local",
        "apiKey": "ollama-local",
        "priority": 1,
        "isActive": True,
        "testStatus": "active",
        "providerSpecificData": {
            "baseUrl": normalize_ollama_host(ollama_host),
            "enabledModels": [model],
        },
        "updatedAt": now,
    }
    if connection is None:
        connection_data.update({"id": "loki-ollama-local", "createdAt": now})
        data["providerConnections"].insert(0, connection_data)
    else:
        connection.update(connection_data)

    data["modelAliases"][LOCAL_MODEL_ALIAS] = routed_model
    if not any(
        item.get("providerAlias") == "ollama-local" and item.get("id") == model and item.get("type", "llm") == "llm"
        for item in data["customModels"]
    ):
        data["customModels"].append({"providerAlias": "ollama-local", "id": model, "type": "llm", "name": model})

    db_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return {"db_path": str(db_path), "alias": LOCAL_MODEL_ALIAS, "routed_model": routed_model}


def read_codex_settings() -> dict[str, Any]:
    path = codex_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_codex_settings_env(updates: dict[str, Any]) -> Path:
    path = codex_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = read_codex_settings()
    env = dict(settings.get("env") or {})
    env.update(updates)
    settings["env"] = env
    path.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_mempalace_config() -> dict[str, Any]:
    path = mempalace_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalized_string_list(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def save_mempalace_config(values: dict[str, Any]) -> Path:
    path = mempalace_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = read_mempalace_config()

    palace_path = str(values.get("palace_path") or "").strip()
    collection_name = str(values.get("collection_name") or "").strip()
    topic_wings = _normalized_string_list(list(values.get("topic_wings") or []))

    if palace_path:
        config["palace_path"] = palace_path
    else:
        config.pop("palace_path", None)

    if collection_name:
        config["collection_name"] = collection_name
    else:
        config.pop("collection_name", None)

    if topic_wings:
        config["topic_wings"] = topic_wings
    else:
        config.pop("topic_wings", None)

    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _parse_mempalace_status(output: str) -> dict[str, Any]:
    wings: list[dict[str, Any]] = []
    total_drawers = 0
    current_wing: Optional[dict[str, Any]] = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "MemPalace Status" in line and "drawers" in line:
            tokens = line.replace("=", " ").split()
            for index, token in enumerate(tokens):
                if token == "drawers" and index:
                    try:
                        total_drawers = int(tokens[index - 1])
                    except ValueError:
                        total_drawers = 0
                    break
            continue
        if line.startswith("WING: "):
            current_wing = {"name": line.split(":", 1)[1].strip(), "rooms": []}
            wings.append(current_wing)
            continue
        if line.startswith("ROOM: "):
            room_payload = line.split(":", 1)[1].strip()
            room_name = room_payload
            drawer_count = 0
            tokens = room_payload.split()
            if len(tokens) >= 3 and tokens[-1] == "drawers":
                try:
                    drawer_count = int(tokens[-2])
                    room_name = " ".join(tokens[:-2]).strip() or room_payload
                except ValueError:
                    drawer_count = 0
            room = {"name": room_name, "drawers": drawer_count}
            if current_wing is None:
                current_wing = {"name": "default", "rooms": []}
                wings.append(current_wing)
            current_wing["rooms"].append(room)
    if not total_drawers:
        total_drawers = sum(room["drawers"] for wing in wings for room in wing["rooms"])
    room_count = sum(len(wing["rooms"]) for wing in wings)
    return {
        "ready": bool(total_drawers or wings),
        "total_drawers": total_drawers,
        "wing_count": len(wings),
        "room_count": room_count,
        "wings": wings,
        "raw_status": output.strip(),
    }


def mempalace_status_snapshot() -> dict[str, Any]:
    config = read_mempalace_config()
    palace_path = Path(config.get("palace_path") or (mempalace_root_path() / "palace"))
    cli_path = shutil.which("mempalace")
    fallback_path = mempalace_fallback_memory_path()
    status: dict[str, Any] = {
        "cli_available": bool(cli_path),
        "cli_path": cli_path or "",
        "config_path": str(mempalace_config_path()),
        "config_present": mempalace_config_path().exists(),
        "palace_path": str(palace_path),
        "palace_present": palace_path.exists(),
        "collection_name": config.get("collection_name", ""),
        "topic_wings": list(config.get("topic_wings") or []),
        "topic_wing_count": len(config.get("topic_wings") or []),
        "hall_keyword_group_count": len(config.get("hall_keywords") or {}),
        "fallback_memory_path": str(fallback_path),
        "fallback_memory_present": fallback_path.exists(),
        "ready": False,
        "total_drawers": 0,
        "wing_count": 0,
        "room_count": 0,
        "wings": [],
        "summary": "MemPalace is not configured yet.",
        "error": "",
    }
    if cli_path:
        try:
            result = subprocess.run(
                ["mempalace", "status"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if result.returncode == 0:
                parsed = _parse_mempalace_status(result.stdout)
                status.update(parsed)
                status["summary"] = (
                    f"{parsed['total_drawers']} drawers across {parsed['wing_count']} wings and "
                    f"{parsed['room_count']} rooms."
                )
            else:
                status["error"] = (result.stderr or result.stdout).strip()
        except Exception as exc:
            status["error"] = str(exc)
    else:
        status["error"] = "mempalace CLI was not found on PATH."
    if not status["ready"] and status["palace_present"]:
        status["summary"] = "Palace files exist, but the status command did not return counts."
    elif not status["ready"] and status["error"]:
        status["summary"] = "MemPalace is installed, but status could not be read."
    return status


def http_json(url: str, headers: Optional[dict[str, str]] = None, timeout: int = 4) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discord_headers() -> Optional[dict[str, str]]:
    token = env_value("DISCORD_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bot {token}", "User-Agent": "LOKIMCP/1.0"}


def fetch_discord_channels(guild_id: int) -> tuple[list[dict[str, Any]], Optional[str]]:
    headers = discord_headers()
    if not headers:
        return [], "DISCORD_TOKEN is not configured."
    try:
        data = http_json(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers=headers,
            timeout=8,
        )
        return data or [], None
    except urllib.error.HTTPError as exc:
        return [], friendly_discord_channel_error(exc)
    except Exception as exc:
        return [], friendly_discord_channel_error(exc)


def friendly_discord_channel_error(exc: object) -> str:
    text = str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return (
                "Discord channel lookup returned 404. Check that LOKI THE SUN GOD is still in this server "
                "and that the configured test guild ID is correct."
            )
        if exc.code == 401:
            return "Discord rejected the bot token. Update DISCORD_TOKEN before using live channel lookup."
        if exc.code == 403:
            return "Discord denied channel lookup. Give LOKI THE SUN GOD View Channels permission in this server."
        return f"Discord channel lookup failed with HTTP {exc.code}."
    if "HTTP Error 404" in text:
        return (
            "Discord channel lookup returned 404. Check that LOKI THE SUN GOD is still in this server "
            "and that the configured test guild ID is correct."
        )
    return f"Discord channel lookup failed: {text}"


def normalize_discord_channel_error(error: Optional[str]) -> Optional[str]:
    if not error:
        return None
    if "HTTP Error" in error or "<urlopen" in error:
        return friendly_discord_channel_error(error)
    return error


def channel_name_map(channels: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for channel in channels:
        channel_id = channel.get("id")
        if not channel_id:
            continue
        names[str(channel_id)] = channel.get("name") or f"Channel {channel_id}"
    return names


def classify_channel_bucket(channel: dict[str, Any]) -> str:
    channel_type = channel.get("type")
    name = (channel.get("name") or "").lower()
    if channel_type in {2, 13}:
        return "voice"
    if channel_type == 5:
        return "announcements"
    if any(token in name for token in ("side", "lounge", "hangout", "off-topic", "chat")):
        return "side_chat"
    if channel_type in {0, 11, 12, 15, 16}:
        return "text"
    return "other"


def channel_kind_label(channel_type: Optional[int]) -> str:
    return {
        0: "Text",
        2: "Voice",
        4: "Category",
        5: "Announcement",
        11: "Thread",
        12: "Private thread",
        13: "Stage",
        15: "Forum",
        16: "Media",
    }.get(channel_type, "Other")


def bucket_rank(bucket: str) -> int:
    order = {"text": 0, "announcements": 1, "voice": 2, "side_chat": 3, "other": 4}
    return order.get(bucket, 99)


def group_channels(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories = {ch["id"]: ch.get("name", "Category") for ch in channels if ch.get("type") == 4}
    clusters: dict[str, dict[str, Any]] = {}
    for channel in channels:
        if channel.get("type") == 4:
            continue
        bucket = classify_channel_bucket(channel)
        parent_id = channel.get("parent_id")
        cluster_id = str(parent_id or bucket)
        cluster = clusters.setdefault(
            cluster_id,
            {
                "id": cluster_id,
                "label": categories.get(parent_id) or bucket.replace("_", " ").title(),
                "bucket": bucket,
                "channels": [],
            },
        )
        cluster["channels"].append(
            {
                "id": channel.get("id"),
                "name": channel.get("name", "channel"),
                "kind": channel_kind_label(channel.get("type")),
                "topic": channel.get("topic") or "",
                "position": channel.get("position", 0),
                "nsfw": bool(channel.get("nsfw")),
            }
        )
    ordered: list[dict[str, Any]] = []
    for cluster in clusters.values():
        cluster["channels"] = sorted(
            cluster["channels"],
            key=lambda item: (item["kind"], item["position"], item["name"]),
        )
        ordered.append(cluster)
    return sorted(ordered, key=lambda item: (bucket_rank(item["bucket"]), item["label"].lower()))


def saved_channel_clusters(guild_id: int) -> list[dict[str, Any]]:
    cfg = (
        db_query(
            "SELECT log_channel, welcome_channel, starboard_channel FROM guild_config WHERE guild_id=?",
            (guild_id,),
        )
        or [{}]
    )[0]
    forms = db_query(
        "SELECT target_channel_id FROM forms WHERE guild_id=? AND target_channel_id IS NOT NULL",
        (guild_id,),
    )
    streams = db_query(
        "SELECT target_channel_id FROM stream_subs WHERE guild_id=? AND target_channel_id IS NOT NULL",
        (guild_id,),
    )
    stickies = db_query("SELECT channel_id FROM stickies WHERE guild_id=?", (guild_id,))
    buckets = [
        (
            "system",
            "Configured channels",
            [
                ("Log channel", cfg.get("log_channel")),
                ("Welcome channel", cfg.get("welcome_channel")),
                ("Starboard channel", cfg.get("starboard_channel")),
            ],
        ),
        (
            "forms",
            "Form delivery",
            [(f"Form target {index + 1}", row.get("target_channel_id")) for index, row in enumerate(forms)],
        ),
        (
            "streams",
            "Stream alerts",
            [(f"Stream target {index + 1}", row.get("target_channel_id")) for index, row in enumerate(streams)],
        ),
        (
            "text",
            "Sticky channels",
            [(f"Sticky {index + 1}", row.get("channel_id")) for index, row in enumerate(stickies)],
        ),
    ]
    clusters: list[dict[str, Any]] = []
    for bucket, label, items in buckets:
        channels = []
        seen: set[Any] = set()
        for name, channel_id in items:
            if not channel_id or channel_id in seen:
                continue
            seen.add(channel_id)
            channels.append(
                {
                    "id": channel_id,
                    "name": name,
                    "kind": "Saved ID",
                    "topic": (
                        "Stored in LOKI THE SUN GOD configuration. Add DISCORD_TOKEN for live channel "
                        "names and categories."
                    ),
                    "position": len(channels),
                    "nsfw": False,
                }
            )
        if channels:
            clusters.append({"id": f"saved-{bucket}", "label": label, "bucket": bucket, "channels": channels})
    return clusters


def saved_channel_name_map(guild_id: int) -> dict[str, str]:
    names: dict[str, str] = {}
    for cluster in saved_channel_clusters(guild_id):
        for channel in cluster.get("channels", []):
            channel_id = channel.get("id")
            if channel_id is None:
                continue
            names[str(channel_id)] = channel.get("name") or f"Channel {channel_id}"
    return names


def list_guilds() -> list[dict[str, Any]]:
    return db_query(
        "SELECT guild_id, prefix, log_channel, welcome_channel, starboard_channel, level_enabled "
        "FROM guild_config ORDER BY guild_id"
    )


def guild_config_snapshot(guild_id: int) -> dict[str, Any]:
    config = (db_query("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)) or [{}])[0]
    automod = (db_query("SELECT * FROM automod_rules WHERE guild_id=?", (guild_id,)) or [{}])[0]
    stickies = db_query("SELECT channel_id, content FROM stickies WHERE guild_id=?", (guild_id,))
    tags = db_query("SELECT name, uses FROM tags WHERE guild_id=? ORDER BY uses DESC LIMIT 50", (guild_id,))
    forms = db_query("SELECT name, title, target_channel_id FROM forms WHERE guild_id=?", (guild_id,))
    streams = db_query(
        "SELECT id, platform, channel_name, target_channel_id, last_status FROM stream_subs WHERE guild_id=?",
        (guild_id,),
    )
    live_channels, live_error = fetch_discord_channels(guild_id)
    names = channel_name_map(live_channels)
    if not names:
        names = saved_channel_name_map(guild_id)
    for sticky in stickies:
        sticky["channel_name"] = names.get(str(sticky.get("channel_id")))
    for form in forms:
        form["target_channel_name"] = names.get(str(form.get("target_channel_id")))
    for stream in streams:
        stream["target_channel_name"] = names.get(str(stream.get("target_channel_id")))
    channel_names = {
        "log_channel": names.get(str(config.get("log_channel"))) if config.get("log_channel") else None,
        "welcome_channel": names.get(str(config.get("welcome_channel"))) if config.get("welcome_channel") else None,
        "starboard_channel": names.get(str(config.get("starboard_channel")))
        if config.get("starboard_channel")
        else None,
    }
    return {
        "guild_id": guild_id,
        "config": config,
        "automod": automod,
        "stickies": stickies,
        "tags": tags,
        "forms": forms,
        "streams": streams,
        "channel_names": channel_names,
        "live_channel_lookup": bool(live_channels),
        "live_channel_error": live_error,
    }


def channel_cluster_snapshot(guild_id: int) -> dict[str, Any]:
    channels, error = fetch_discord_channels(guild_id)
    error = normalize_discord_channel_error(error)
    live_clusters = group_channels(channels) if channels else []
    fallback_clusters = saved_channel_clusters(guild_id)
    clusters = live_clusters or fallback_clusters
    message = error
    if error and fallback_clusters:
        message = f"{error} Showing saved LOKI THE SUN GOD channel IDs until live Discord access is configured."
    elif error and not fallback_clusters:
        message = f"{error} No saved LOKI THE SUN GOD channel IDs are available yet."
    return {
        "guild_id": guild_id,
        "clusters": clusters,
        "total": sum(len(cluster["channels"]) for cluster in clusters),
        "live": bool(live_clusters),
        "error": message,
    }


def ai_doc_library(include_content: bool = False) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen: set[Path] = set()
    paths: list[Path] = []
    current_docs_path = docs_path()
    current_ai_docs_path = ai_docs_path()
    if current_docs_path.exists():
        paths.extend(sorted(current_docs_path.glob("*.md")))
    if current_ai_docs_path.exists():
        paths.extend(sorted(current_ai_docs_path.glob("*.md")))
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            relative_file = str(path.relative_to(command_root()))
        except ValueError:
            relative_file = str(path)
        item = {
            "name": path.stem.replace("_", " "),
            "file": relative_file,
            "bytes": path.stat().st_size,
            "summary": next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), "Documentation"),
        }
        if include_content:
            item["content"] = text
        docs.append(item)
    return docs


def search_ai_docs(query: str, include_content: bool = False) -> list[dict[str, Any]]:
    normalized_query = query.strip().lower()
    docs = ai_doc_library(include_content=include_content)
    if not normalized_query:
        return docs
    matched: list[dict[str, Any]] = []
    for doc in docs:
        haystack = " ".join(
            filter(
                None,
                [
                    str(doc.get("name") or ""),
                    str(doc.get("summary") or ""),
                    str(doc.get("file") or ""),
                    str(doc.get("content") or ""),
                ],
            )
        ).lower()
        if normalized_query in haystack:
            matched.append(doc)
    return matched


def ollama_router_status(ollama_host: str | None = None) -> dict[str, Any]:
    normalized_ollama_host = normalize_ollama_host(ollama_host)
    status: dict[str, Any] = {
        "ollama_up": False,
        "router_up": False,
        "ollama_models": [],
        "router_models": [],
        "codex_settings": {},
        "ollama_base_url": normalized_ollama_host,
        "openai_compatible_base_url": ollama_openai_base_url(normalized_ollama_host),
        "preferred_local_model": "",
        "local_model_source": "missing",
        "local_model_ready": False,
        "local_model_route": "",
        "local_model_setup_hint": "Run `ollama pull qwen2.5-coder:7b` to install the recommended local model.",
    }
    try:
        tags = http_json(f"{normalized_ollama_host}/api/tags", timeout=3) or {}
        status["ollama_up"] = True
        status["ollama_models"] = [model.get("name") for model in tags.get("models", []) if model.get("name")]
    except Exception:
        pass
    status.update(preferred_local_model(status["ollama_models"]))
    if status["preferred_local_model"]:
        status["local_model_route"] = f"ollama-local/{status['preferred_local_model']}"
    try:
        models = http_json("http://127.0.0.1:20128/v1/models", timeout=3) or {}
        status["router_up"] = True
        status["router_models"] = [model.get("id") for model in models.get("data", []) if model.get("id")]
    except Exception:
        pass
    settings_path = codex_settings_path()
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            env = settings.get("env", {})
            status["codex_settings"] = {
                "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL"),
                "ANTHROPIC_AUTH_TOKEN": bool(env.get("ANTHROPIC_AUTH_TOKEN")),
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
                "ANTHROPIC_DEFAULT_SONNET_MODEL": env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
                "ANTHROPIC_DEFAULT_OPUS_MODEL": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
            }
        except Exception:
            pass
    return status


def ai_router_snapshot() -> dict[str, Any]:
    app_env = read_env_file()
    router_env = read_env_file_at(router_env_path())
    codex_settings = read_codex_settings()
    codex_env = dict(codex_settings.get("env") or {})
    status = ollama_router_status(app_env.get("OLLAMA_HOST"))
    memory = mempalace_status_snapshot()
    return {
        "app_env_path": str(env_path()),
        "router_env_path": str(router_env_path()),
        "router_repo_path": str(router_repo_path()),
        "codex_settings_path": str(codex_settings_path()),
        "mempalace_config_path": str(mempalace_config_path()),
        "preferred_local_model": status["preferred_local_model"],
        "local_model_source": status["local_model_source"],
        "ollama_base_url": status["ollama_base_url"],
        "local_model_ready": status["local_model_ready"],
        "local_model_route": status["local_model_route"],
        "local_model_alias": LOCAL_MODEL_ALIAS,
        "local_model_setup_hint": status["local_model_setup_hint"],
        "router_db_path": str(router_db_path(router_env)),
        "app_env": {
            "OPENAI_API_KEY_present": bool(app_env.get("OPENAI_API_KEY")),
            "OPENAI_BASE_URL": app_env.get("OPENAI_BASE_URL", ""),
            "OPENROUTER_API_KEY_present": bool(app_env.get("OPENROUTER_API_KEY")),
            "OPENROUTER_BASE_URL": app_env.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "ANTHROPIC_AUTH_TOKEN_present": bool(app_env.get("ANTHROPIC_AUTH_TOKEN")),
            "ANTHROPIC_BASE_URL": app_env.get("ANTHROPIC_BASE_URL", ""),
            "OLLAMA_HOST": app_env.get("OLLAMA_HOST", OLLAMA_HOST_DEFAULT),
            "LOKI_LLM_MODEL": app_env.get("LOKI_LLM_MODEL", "gpt-5.5"),
        },
        "codex_env": {
            "ANTHROPIC_BASE_URL": codex_env.get("ANTHROPIC_BASE_URL", ""),
            "ANTHROPIC_AUTH_TOKEN_present": bool(codex_env.get("ANTHROPIC_AUTH_TOKEN")),
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": codex_env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", ""),
            "ANTHROPIC_DEFAULT_SONNET_MODEL": codex_env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", ""),
            "ANTHROPIC_DEFAULT_OPUS_MODEL": codex_env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", ""),
            "OPENAI_BASE_URL": codex_env.get("OPENAI_BASE_URL", ""),
            "OPENAI_API_KEY_present": bool(codex_env.get("OPENAI_API_KEY")),
        },
        "router_env": {
            "PORT": router_env.get("PORT", "20128"),
            "BASE_URL": router_env.get("BASE_URL", "http://localhost:20128"),
            "CLOUD_URL": router_env.get("CLOUD_URL", "https://9router.com"),
            "NEXT_PUBLIC_BASE_URL": router_env.get("NEXT_PUBLIC_BASE_URL", "http://localhost:20128"),
            "NEXT_PUBLIC_CLOUD_URL": router_env.get("NEXT_PUBLIC_CLOUD_URL", "https://9router.com"),
            "DATA_DIR": router_env.get("DATA_DIR", ""),
            "JWT_SECRET_present": bool(router_env.get("JWT_SECRET")),
            "INITIAL_PASSWORD_present": bool(router_env.get("INITIAL_PASSWORD")),
            "API_KEY_SECRET_present": bool(router_env.get("API_KEY_SECRET")),
            "MACHINE_ID_SALT_present": bool(router_env.get("MACHINE_ID_SALT")),
            "ENABLE_REQUEST_LOGS": router_env.get("ENABLE_REQUEST_LOGS", "false").lower() == "true",
            "OBSERVABILITY_ENABLED": router_env.get("OBSERVABILITY_ENABLED", "true").lower() == "true",
            "AUTH_COOKIE_SECURE": router_env.get("AUTH_COOKIE_SECURE", "false").lower() == "true",
            "REQUIRE_API_KEY": router_env.get("REQUIRE_API_KEY", "false").lower() == "true",
        },
        "status": status,
        "memory": memory,
    }


def loki_music_snapshot(guild_id: int | None = None) -> dict[str, Any]:
    if guild_id:
        row = shared_db.sync_one("SELECT * FROM loki_music_settings WHERE guild_id=?", (guild_id,))
        settings = dict(row) if row else {}
    else:
        settings = {}
    return {
        "guild_id": guild_id,
        "settings": settings,
        "equalizer_presets": ["Flat", "Bass Boost", "Vocal Clarity", "Night Mode", "Podcast", "Treble", "Custom"],
        "public_audio_filters_exposed": False,
        "backend": "Wavelink/Lavalink v4 adapter scaffold",
    }


def loki_npc_snapshot(guild_id: int | None = None) -> dict[str, Any]:
    if guild_id:
        row = shared_db.sync_one("SELECT * FROM loki_npc_settings WHERE guild_id=?", (guild_id,))
        settings = dict(row) if row else {}
    else:
        settings = {}
    return {
        "guild_id": guild_id,
        "settings": settings,
        "learning_scope": "redacted public-channel memory only",
        "admin_only_mutations": True,
        "raw_training_allowed": False,
    }


def loki_activity_snapshot(guild_id: int | None = None) -> dict[str, Any]:
    if guild_id:
        rows = shared_db.sync_all(
            "SELECT * FROM loki_activity_controls WHERE guild_id=? ORDER BY created_at DESC LIMIT 25",
            (guild_id,),
        )
    else:
        rows = shared_db.sync_all("SELECT * FROM loki_activity_controls ORDER BY created_at DESC LIMIT 25")
    bridge = ActivityBridgeClient()
    bridge_health = bridge.health()
    bridge_rooms = bridge.list_rooms().get("rooms", []) if bridge.config.configured else []
    return {
        "guild_id": guild_id,
        "activities": [dict(row) for row in rows],
        "supported_layers": ["Discord scheduled events", "embedded activity launch handoff", "portal quests"],
        "permission_gate": "create-events, manage-events, manage-guild, or administrator depending on action",
        "bridge": {
            "configured": bridge.config.configured,
            "url": bridge.config.url,
            "client_public_url": bridge.config.client_public_url,
            "health": bridge_health,
            "rooms": bridge_rooms if isinstance(bridge_rooms, list) else [],
        },
    }


def loki_mythos_snapshot() -> dict[str, Any]:
    run_dir = APP_ROOT / ".mythos" / "loki-diva-reprocess"
    files = []
    if run_dir.exists():
        files = [str(path.relative_to(APP_ROOT)) for path in sorted(run_dir.glob("**/*")) if path.is_file()]
    return {
        "run_dir": str(run_dir),
        "exists": run_dir.exists(),
        "files": files,
        "prime_consumption_rule": "Read compiled packet only after ingest/compile/gate.",
    }


def save_app_ai_env(values: dict[str, Any]) -> Path:
    filtered = {key: value for key, value in values.items() if value is not None}
    return write_env_values(env_path(), filtered)


def save_router_runtime_env(values: dict[str, Any]) -> Path:
    filtered = {key: value for key, value in values.items() if value is not None}
    return write_env_values(router_env_path(), filtered, template_path=router_env_example_path())


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(APP_ROOT))
    except ValueError:
        return str(path)


def _file_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "display_path": _display_path(path),
        "bytes": stat.st_size,
        "modified_at": stat.st_mtime,
    }


def backup_status() -> dict[str, Any]:
    database = db_path()
    data_dir = database.parent
    patterns = [
        "bot-backup-*.sqlite",
        "*backup*.sqlite",
        "*backup*.json",
        "*.bak",
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in [data_dir, data_dir / "backups", APP_ROOT]:
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.glob(pattern):
                resolved = path.resolve()
                if resolved == database.resolve() or resolved in seen or not path.is_file():
                    continue
                seen.add(resolved)
                candidates.append(path)
    mirror_path = data_dir / "remote_mirror.sqlite"
    latest = max(candidates, key=lambda item: item.stat().st_mtime, default=None)
    has_backup = latest is not None
    age_seconds = None
    if latest is not None:
        age_seconds = max(0, int(time.time() - latest.stat().st_mtime))
    return {
        "database_present": database.exists(),
        "database": _file_metadata(database) if database.exists() else None,
        "has_backup": has_backup,
        "backup_count": len(candidates),
        "latest_backup": _file_metadata(latest) if latest else None,
        "backup_age_seconds": age_seconds,
        "mirror_present": mirror_path.exists(),
        "mirror": _file_metadata(mirror_path) if mirror_path.exists() else None,
        "state": "ready" if has_backup else ("watch" if database.exists() else "missing"),
        "summary": (
            f"Latest backup: {_display_path(latest)}"
            if latest
            else ("No backup artifact found yet." if database.exists() else "Primary database missing.")
        ),
    }


def create_manual_backup() -> dict[str, Any]:
    if shared_db.using_postgres():
        return {
            "ok": False,
            "error": "Manual dashboard backup supports local SQLite only. Use your Postgres provider backup tools.",
            "status": backup_status(),
        }

    database = db_path()
    if not database.exists():
        return {
            "ok": False,
            "error": f"Primary SQLite database was not found at {database}.",
            "status": backup_status(),
        }

    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    backup_path = backup_dir / f"bot-backup-{timestamp}.sqlite"
    with sqlite3.connect(database) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)

    return {
        "ok": True,
        "backup": _file_metadata(backup_path),
        "status": backup_status(),
    }


def local_ai_assistant_status() -> dict[str, Any]:
    ollama = ollama_router_status()
    codex_settings = ollama.get("codex_settings") or {}
    app_env = read_env_file()
    route_url = app_env.get("OPENAI_BASE_URL") or codex_settings.get("ANTHROPIC_BASE_URL") or ""
    token_present = bool(app_env.get("OPENAI_API_KEY") or codex_settings.get("ANTHROPIC_AUTH_TOKEN"))
    ollama_models = ollama.get("ollama_models") or []
    router_models = ollama.get("router_models") or []
    if app_env.get("OPENAI_API_KEY") and route_url:
        state = "ready"
        summary = "OpenAI-compatible API key is configured for LOKI THE SUN GOD Discord LLM commands."
        preferred_backend = "openai"
    elif ollama.get("router_up"):
        state = "ready"
        summary = "Local assistant routing is ready through 9router."
        preferred_backend = "9router"
    elif ollama.get("ollama_up"):
        state = "ready"
        summary = "Ollama is online for direct local model usage."
        preferred_backend = "ollama"
    elif route_url or token_present:
        state = "degraded"
        summary = "Assistant route is configured, but the local backend is offline."
        preferred_backend = "configured"
    else:
        state = "offline"
        summary = "No local AI route is configured yet."
        preferred_backend = "none"
    return {
        "state": state,
        "summary": summary,
        "preferred_backend": preferred_backend,
        "route_url": route_url or "Not set",
        "token_present": token_present,
        "ollama_online": bool(ollama.get("ollama_up")),
        "router_online": bool(ollama.get("router_up")),
        "ollama_model_count": len(ollama_models),
        "router_model_count": len(router_models),
        "models_available": len(router_models) if router_models else len(ollama_models),
    }


def dashboard_ops_status() -> dict[str, Any]:
    ai_status = local_ai_assistant_status()
    backup = backup_status()
    ollama = ollama_router_status()
    return {
        "ai_assistant": ai_status,
        "backup": backup,
        "router": {
            "up": bool(ollama.get("router_up")),
            "model_count": len(ollama.get("router_models") or []),
            "base_url": (ollama.get("codex_settings") or {}).get("ANTHROPIC_BASE_URL") or "http://127.0.0.1:20128/v1",
            "summary": (
                f"{len(ollama.get('router_models') or [])} router models exposed"
                if ollama.get("router_up")
                else "9router is offline or not responding."
            ),
        },
    }


def diagnostics_snapshot(
    service_statuses: Optional[list[dict[str, Any]]] = None,
    runtime_log_override: Optional[Path] = None,
) -> dict[str, Any]:
    env = read_env_file()
    log_path = runtime_log_override or runtime_log_path()
    commands = command_library()
    return {
        "database_present": db_path().exists(),
        "docs_present": docs_path().exists(),
        "runtime_log_present": log_path.exists(),
        "services": service_statuses or [],
        "env": {
            "DISCORD_TOKEN": bool(env.get("DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN")),
            "CLIENT_ID": bool(
                env.get("DISCORD_CLIENT_ID")
                or env.get("CLIENT_ID")
                or os.getenv("DISCORD_CLIENT_ID")
                or os.getenv("CLIENT_ID")
            ),
            "GUILD_ID": bool(env.get("GUILD_ID") or os.getenv("GUILD_ID")),
            "TEST_GUILD_ID": env.get("TEST_GUILD_ID") or os.getenv("TEST_GUILD_ID") or "",
        },
        "ollama": ollama_router_status(),
        "command_count": len(commands),
        "slash_command_count": len([item for item in commands if item.get("slash_enabled")]),
        "guild_count": len(list_guilds()),
        "doc_count": len(ai_doc_library(include_content=False)),
    }


def overview_snapshot(service_statuses: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    commands = command_library()
    guilds = list_guilds()
    return {
        "name": "loki_mcp",
        "database_present": db_path().exists(),
        "guild_count": len(guilds),
        "guild_ids": [guild.get("guild_id") for guild in guilds],
        "command_count": len(commands),
        "slash_command_count": len([item for item in commands if item.get("slash_enabled")]),
        "option_sections": list(option_library().keys()),
        "doc_count": len(ai_doc_library(include_content=False)),
        "ollama": ollama_router_status(),
        "services": service_statuses or [],
    }


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


def save_guild_config(guild_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    prefix = str(payload.get("prefix") or "!")[:10]
    shared_db.save_guild_config_sync(
        guild_id,
        {
            "prefix": prefix,
            "log_channel": _coerce_int(payload.get("log_channel")),
            "welcome_channel": _coerce_int(payload.get("welcome_channel")),
            "starboard_channel": _coerce_int(payload.get("starboard_channel")),
            "star_threshold": int(payload.get("star_threshold") or 3),
            "level_enabled": 1 if payload.get("level_enabled") else 0,
        },
    )
    automod = payload.get("automod") or {}
    shared_db.save_automod_rules_sync(
        guild_id,
        {
            "anti_invite": 1 if automod.get("anti_invite") else 0,
            "anti_spam": 1 if automod.get("anti_spam") else 0,
            "anti_caps": 1 if automod.get("anti_caps") else 0,
            "anti_mention": 1 if automod.get("anti_mention") else 0,
            "max_mentions": int(automod.get("max_mentions") or 5),
            "spam_threshold": int(automod.get("spam_threshold") or 5),
            "caps_percent": int(automod.get("caps_percent") or 70),
            "bad_words": str(automod.get("bad_words") or ""),
        },
    )
    return guild_config_snapshot(guild_id)


def delete_sticky(guild_id: int, channel_id: int) -> int:
    return db_exec("DELETE FROM stickies WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
