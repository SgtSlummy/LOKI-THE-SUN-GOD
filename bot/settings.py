from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv


def _bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: str | int | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _csv_ints(value: str | None) -> set[int]:
    if not value:
        return set()
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return result


@dataclass(slots=True)
class Settings:
    discord_token: str | None = None
    discord_client_id: str | None = None
    discord_guild_id: int | None = None
    database_url: str = "sqlite:///loki-relay.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    bot_env: str = "development"
    log_level: str = "info"
    max_active_plugins: int = 8
    relay_config_json: str | None = None
    media_mode: str = "clean"
    media_link_buttons: bool = False
    webhook_relay_mode: bool = False
    health_port: int = 8080
    autocurator_enabled: bool = False
    autocurator_autopost: bool = False
    server_search_enabled: bool = False
    llm_chat_enabled: bool = False
    music_enabled: bool = False
    bot_admin_user_ids: set[int] = field(default_factory=set)
    allow_bot_relay: bool = False
    relay_error_threshold: int = 5
    relay_error_window_seconds: int = 60
    enabled_plugins_override: set[str] | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        client_id = os.getenv("DISCORD_CLIENT_ID") or os.getenv("DISCORD_APPLICATION_ID")
        guild_id_value = os.getenv("DISCORD_GUILD_ID")
        owner_ids = _csv_ints(os.getenv("BOT_ADMIN_USER_IDS"))
        owner_ids.update(_csv_ints(os.getenv("DISCORD_OWNER_USER_IDS")))
        enabled_plugins_raw = os.getenv("ENABLED_PLUGINS")
        enabled_override = None
        if enabled_plugins_raw:
            enabled_override = {
                item.strip()
                for item in enabled_plugins_raw.split(",")
                if item.strip()
            }

        return cls(
            discord_token=os.getenv("DISCORD_TOKEN"),
            discord_client_id=client_id,
            discord_guild_id=int(guild_id_value) if guild_id_value else None,
            database_url=os.getenv("DATABASE_URL") or "sqlite:///loki-relay.db",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            bot_env=os.getenv("BOT_ENV", os.getenv("NODE_ENV", "development")),
            log_level=os.getenv("LOG_LEVEL", "info"),
            max_active_plugins=_int(os.getenv("MAX_ACTIVE_PLUGINS"), 8),
            relay_config_json=os.getenv("RELAY_CONFIG_JSON"),
            media_mode=os.getenv("MEDIA_MODE", "clean"),
            media_link_buttons=_bool(os.getenv("MEDIA_LINK_BUTTONS"), False),
            webhook_relay_mode=_bool(os.getenv("WEBHOOK_RELAY_MODE"), False),
            health_port=_int(os.getenv("HEALTH_PORT") or os.getenv("PORT"), 8080),
            autocurator_enabled=_bool(os.getenv("AUTOCURATOR_ENABLED"), False),
            autocurator_autopost=_bool(os.getenv("AUTOCURATOR_AUTOPOST"), False),
            server_search_enabled=_bool(os.getenv("SERVER_SEARCH_ENABLED"), False),
            llm_chat_enabled=_bool(os.getenv("LLM_CHAT_ENABLED"), False),
            music_enabled=_bool(os.getenv("MUSIC_ENABLED"), False),
            bot_admin_user_ids=owner_ids,
            allow_bot_relay=_bool(os.getenv("ALLOW_BOT_RELAY"), False),
            relay_error_threshold=_int(os.getenv("RELAY_ERROR_THRESHOLD"), 5),
            relay_error_window_seconds=_int(os.getenv("RELAY_ERROR_WINDOW_SECONDS"), 60),
            enabled_plugins_override=enabled_override,
        )

    def validate_for_startup(self) -> None:
        if not self.discord_token:
            raise RuntimeError("DISCORD_TOKEN is required to start the Discord bot.")
        if self.media_mode not in {"clean", "button", "native_unfurl"}:
            raise RuntimeError("MEDIA_MODE must be clean, button, or native_unfurl.")

    @property
    def required_default_plugins(self) -> set[str]:
        return {"admin_config", "relay_core", "media_resolver", "moderation_audit"}

    @property
    def enabled_plugin_names(self) -> set[str] | None:
        if self.enabled_plugins_override is not None:
            return self.enabled_plugins_override
        names = set(self.required_default_plugins)
        if self.llm_chat_enabled:
            names.add("llm_chat")
        if self.server_search_enabled:
            names.add("server_search")
        if self.autocurator_enabled:
            names.add("autonomous_curator")
            names.add("server_search")
            names.add("llm_chat")
        if self.music_enabled:
            names.add("music")
        return names

    @property
    def relay_bootstrap_routes(self) -> list[dict[str, Any]]:
        if not self.relay_config_json:
            return []
        parsed = json.loads(self.relay_config_json)
        if isinstance(parsed, dict):
            routes = parsed.get("routes", [])
        else:
            routes = parsed
        if not isinstance(routes, list):
            raise RuntimeError("RELAY_CONFIG_JSON must be a list or an object with a routes list.")
        return routes

    def safe_log_dict(self) -> dict[str, Any]:
        return {
            "bot_env": self.bot_env,
            "log_level": self.log_level,
            "discord_client_id_present": bool(self.discord_client_id),
            "discord_guild_id": self.discord_guild_id,
            "database": "postgres" if self.database_url.startswith(("postgres://", "postgresql://")) else "sqlite",
            "openai_api_key_present": bool(self.openai_api_key),
            "openai_model": self.openai_model,
            "max_active_plugins": self.max_active_plugins,
            "media_mode": self.media_mode,
            "media_link_buttons": self.media_link_buttons,
            "webhook_relay_mode": self.webhook_relay_mode,
            "health_port": self.health_port,
            "future_plugins": {
                "llm_chat": self.llm_chat_enabled,
                "server_search": self.server_search_enabled,
                "autonomous_curator": self.autocurator_enabled,
                "music": self.music_enabled,
            },
        }
