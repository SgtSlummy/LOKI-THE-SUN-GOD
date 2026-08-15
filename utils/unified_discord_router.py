from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import aiohttp

TRUTHY = {"1", "true", "yes", "on"}
DEFAULT_AUTODM_BASE_URL = "http://127.0.0.1:8000/v1/solo"

_ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "combat": ("attack", "battle", "defend", "duel", "fight", "monster", "strike"),
    "exploration": ("dungeon", "explore", "investigate", "map", "ruin", "scout", "search", "travel"),
    "quest": ("artifact", "mission", "quest", "rescue", "rumor", "treasure"),
    "social": ("ally", "ask", "bargain", "negotiate", "persuade", "talk"),
}
_ROUTE_ABILITIES = {
    "combat": "strength",
    "exploration": "wisdom",
    "quest": "charisma",
    "social": "charisma",
    "default": "wisdom",
}


class IntegrationConfigError(RuntimeError):
    pass


class AutoDMGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class MythosRouteDecision:
    route: str
    ability: str
    reason: str


@dataclass(frozen=True)
class AutoDMReply:
    campaign_id: str
    route: str
    narrative: str


class AutoDMTransport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        actor_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Any: ...


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in TRUTHY


def autodm_enabled() -> bool:
    return _enabled("AUTODM_DISCORD_ENABLED")


def mythos_router_enabled() -> bool:
    return _enabled("MYTHOS_ROUTER_ENABLED", "true")


def autodm_channel_ids() -> frozenset[int]:
    raw = os.getenv("AUTODM_DISCORD_CHANNEL_IDS") or os.getenv("AUTODM_DISCORD_CHANNEL_ID") or ""
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise IntegrationConfigError("AutoDM is enabled but no Discord channel ID is configured.")
    if any(not item.isdigit() or int(item) <= 0 for item in values):
        raise IntegrationConfigError("AutoDM Discord channel IDs must be positive integers.")
    return frozenset(int(item) for item in values)


def mythos_route(content: str) -> MythosRouteDecision:
    normalized = " ".join((content or "").casefold().split())
    if mythos_router_enabled():
        for route, keywords in _ROUTE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized:
                    return MythosRouteDecision(route, _ROUTE_ABILITIES[route], f"matched {keyword}")
    return MythosRouteDecision("default", _ROUTE_ABILITIES["default"], "no route keyword matched")


def _validate_autodm_url(base_url: str, *, allow_remote: bool, backend_token: str | None) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise IntegrationConfigError("AUTODM_BASE_URL must be an HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise IntegrationConfigError("AUTODM_BASE_URL cannot contain credentials.")
    loopback = parsed.hostname.casefold() in {"127.0.0.1", "localhost", "::1"}
    if not loopback and not allow_remote:
        raise IntegrationConfigError("Remote AutoDM routing requires AUTODM_ALLOW_REMOTE=true.")
    if not loopback and not backend_token:
        raise IntegrationConfigError("Remote AutoDM routing requires AUTODM_DISCORD_BACKEND_TOKEN.")
    return normalized


class AiohttpAutoDMTransport:
    def __init__(self, base_url: str, *, backend_token: str | None, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.backend_token = backend_token
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def request(
        self,
        method: str,
        path: str,
        *,
        actor_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"X-AutoDM-Actor": actor_id}
        if self.backend_token:
            headers["Authorization"] = f"Bearer {self.backend_token}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method,
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=headers,
                    json=payload,
                ) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise AutoDMGatewayError(f"AutoDM campaign service returned HTTP {response.status}.")
        except AutoDMGatewayError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AutoDMGatewayError("AutoDM campaign service is unavailable.") from exc
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AutoDMGatewayError("AutoDM campaign service returned invalid JSON.") from exc


class AutoDMGatewayClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_AUTODM_BASE_URL,
        backend_token: str | None = None,
        timeout_seconds: float = 20.0,
        allow_remote: bool = False,
        transport: AutoDMTransport | None = None,
        character_name: str = "Mecha Cannibal",
    ) -> None:
        self.base_url = _validate_autodm_url(
            base_url,
            allow_remote=allow_remote,
            backend_token=backend_token,
        )
        self.character_name = character_name.strip()[:80] or "Mecha Cannibal"
        self.transport = transport or AiohttpAutoDMTransport(
            self.base_url,
            backend_token=backend_token,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def from_env(cls) -> AutoDMGatewayClient:
        try:
            timeout_seconds = float(os.getenv("AUTODM_TIMEOUT_SECONDS", "20"))
        except ValueError as exc:
            raise IntegrationConfigError("AUTODM_TIMEOUT_SECONDS must be numeric.") from exc
        if not 1 <= timeout_seconds <= 120:
            raise IntegrationConfigError("AUTODM_TIMEOUT_SECONDS must be between 1 and 120.")
        return cls(
            base_url=os.getenv("AUTODM_BASE_URL", DEFAULT_AUTODM_BASE_URL),
            backend_token=(os.getenv("AUTODM_DISCORD_BACKEND_TOKEN") or "").strip() or None,
            timeout_seconds=timeout_seconds,
            allow_remote=_enabled("AUTODM_ALLOW_REMOTE"),
            character_name=os.getenv("AUTODM_CHARACTER_NAME", "Mecha Cannibal"),
        )

    async def process_message(
        self,
        *,
        channel_id: int,
        user_id: int,
        display_name: str,
        message_id: int,
        content: str,
    ) -> AutoDMReply:
        action = (content or "").strip()
        if not action:
            raise AutoDMGatewayError("AutoDM requires a non-empty action.")
        if len(action) > 4000:
            action = action[:4000]
        actor_id = f"discord:{channel_id}:{user_id}"
        decision = mythos_route(action)
        bootstrap = self._mapping(
            await self.transport.request("GET", "/bootstrap", actor_id=actor_id),
            "bootstrap",
        )
        profile = bootstrap.get("profile")
        if not isinstance(profile, dict):
            profile = self._mapping(
                await self.transport.request(
                    "PUT",
                    "/profile",
                    actor_id=actor_id,
                    payload={"display_name": (display_name or "Discord Player")[:80]},
                ),
                "profile",
            )

        characters = bootstrap.get("characters") or []
        character = next(
            (item for item in characters if isinstance(item, dict) and item.get("template") == "mecha-cannibal"),
            None,
        )
        if character is None:
            character = self._mapping(
                await self.transport.request(
                    "POST",
                    "/characters",
                    actor_id=actor_id,
                    payload={"template": "mecha-cannibal", "name": self.character_name},
                ),
                "character",
            )
        character_id = self._required_text(character, "id", "character")

        campaigns = bootstrap.get("campaigns") or []
        campaign = next(
            (item for item in campaigns if isinstance(item, dict) and str(item.get("character_id")) == character_id),
            None,
        )
        if campaign is None:
            view = self._mapping(
                await self.transport.request(
                    "POST",
                    "/campaigns",
                    actor_id=actor_id,
                    payload={
                        "title": f"{self.character_name}'s Dawn Key",
                        "seed": f"discord:{channel_id}:{user_id}",
                        "character_id": character_id,
                    },
                ),
                "campaign",
            )
            campaign = self._mapping(view.get("campaign"), "campaign")
        else:
            campaign_id = self._required_text(campaign, "id", "campaign")
            view = self._mapping(
                await self.transport.request(
                    "GET",
                    f"/campaigns/{campaign_id}",
                    actor_id=actor_id,
                ),
                "campaign view",
            )
            campaign = self._mapping(view.get("campaign"), "campaign")

        campaign_id = self._required_text(campaign, "id", "campaign")
        try:
            expected_version = int(campaign["version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AutoDMGatewayError("AutoDM campaign version is missing or invalid.") from exc
        idempotency_key = f"discord:{channel_id}:{message_id}"
        response = self._mapping(
            await self.transport.request(
                "POST",
                f"/campaigns/{campaign_id}/turns",
                actor_id=actor_id,
                payload={
                    "action": action,
                    "ability": decision.ability,
                    "expected_version": expected_version,
                    "idempotency_key": idempotency_key,
                    "command_id": idempotency_key,
                },
            ),
            "turn",
        )
        turn = self._mapping(response.get("turn"), "turn")
        narrative = self._required_text(turn, "narrative", "turn")
        return AutoDMReply(campaign_id=campaign_id, route=decision.route, narrative=narrative)

    @staticmethod
    def _mapping(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AutoDMGatewayError(f"AutoDM {label} response is invalid.")
        return value

    @staticmethod
    def _required_text(value: dict[str, Any], key: str, label: str) -> str:
        result = str(value.get(key) or "").strip()
        if not result:
            raise AutoDMGatewayError(f"AutoDM {label} response is missing {key}.")
        return result
