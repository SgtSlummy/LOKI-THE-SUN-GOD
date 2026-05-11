from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 4


def room_id_for(guild_id: int | str, channel_id: int | str | None = None) -> str:
    if channel_id:
        return f"{guild_id}:{channel_id}"
    return f"{guild_id}:dashboard"


@dataclass(frozen=True)
class ActivityBridgeConfig:
    url: str = ""
    token: str = ""
    client_public_url: str = ""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "ActivityBridgeConfig":
        timeout_raw = os.getenv("ACTIVITY_BRIDGE_TIMEOUT_SECONDS", "")
        try:
            timeout = int(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            url=os.getenv("ACTIVITY_BRIDGE_URL", "").strip().rstrip("/"),
            token=os.getenv("ACTIVITY_BRIDGE_TOKEN", "").strip(),
            client_public_url=os.getenv("ACTIVITY_CLIENT_PUBLIC_URL", "").strip().rstrip("/"),
            timeout_seconds=max(1, min(timeout, 20)),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url)


class ActivityBridgeClient:
    def __init__(self, config: ActivityBridgeConfig | None = None) -> None:
        self.config = config or ActivityBridgeConfig.from_env()

    def health(self) -> dict[str, Any]:
        if not self.config.configured:
            return {"ok": False, "configured": False, "message": "Activity bridge is not configured."}
        return self._request("GET", "/healthz")

    def list_rooms(self) -> dict[str, Any]:
        if not self.config.configured:
            return {"ok": False, "rooms": [], "message": "Activity bridge is not configured."}
        payload = self._request("GET", "/api/rooms")
        payload.setdefault("rooms", [])
        return payload

    def get_room(self, room_id: str) -> dict[str, Any]:
        if not self.config.configured:
            return {"ok": False, "room": None, "message": "Activity bridge is not configured."}
        return self._request("GET", f"/api/rooms/{room_id}")

    def control(self, room_id: str, action: str, **payload: Any) -> dict[str, Any]:
        if not self.config.configured:
            return {"ok": False, "message": "Activity bridge is not configured."}
        body = {"action": action, **{key: value for key, value in payload.items() if value is not None}}
        return self._request("POST", f"/api/rooms/{room_id}/control", json=body)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.config.url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=self.config.timeout_seconds,
                **kwargs,
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {"message": response.text[:500]}
            if isinstance(payload, dict):
                payload.setdefault("ok", response.ok)
                payload.setdefault("status_code", response.status_code)
                return payload
            return {"ok": response.ok, "status_code": response.status_code, "data": payload}
        except requests.RequestException as exc:
            return {"ok": False, "message": f"Activity bridge request failed: {exc}"}
