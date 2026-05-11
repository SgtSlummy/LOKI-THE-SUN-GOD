from __future__ import annotations

import requests

from loki_activity_bridge import ActivityBridgeClient, ActivityBridgeConfig, room_id_for


class FakeResponse:
    def __init__(self, payload: dict, ok: bool = True, status_code: int = 200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = "fake"

    def json(self):
        return self._payload


def test_room_id_for_uses_guild_channel_or_dashboard_fallback():
    assert room_id_for(123, 456) == "123:456"
    assert room_id_for("123") == "123:dashboard"


def test_bridge_client_disabled_without_url():
    client = ActivityBridgeClient(ActivityBridgeConfig())

    assert client.health()["configured"] is False
    assert client.list_rooms()["rooms"] == []
    assert client.control("1:dashboard", "play")["ok"] is False


def test_bridge_client_sends_bearer_token_and_control_payload(monkeypatch):
    calls = []

    def fake_request(method, url, headers, timeout, **kwargs):
        calls.append({"method": method, "url": url, "headers": headers, "timeout": timeout, "kwargs": kwargs})
        return FakeResponse({"ok": True, "message": "accepted"})

    monkeypatch.setattr("loki_activity_bridge.client.requests.request", fake_request)
    client = ActivityBridgeClient(
        ActivityBridgeConfig(url="http://bridge.local", token="secret-token", timeout_seconds=3)
    )

    result = client.control("123:dashboard", "set", url="https://example.com/video.mp4", title="Watch")

    assert result["ok"] is True
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "http://bridge.local/api/rooms/123:dashboard/control"
    assert calls[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert calls[0]["kwargs"]["json"] == {
        "action": "set",
        "url": "https://example.com/video.mp4",
        "title": "Watch",
    }


def test_bridge_client_returns_graceful_error_on_request_exception(monkeypatch):
    def fake_request(*args, **kwargs):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr("loki_activity_bridge.client.requests.request", fake_request)
    client = ActivityBridgeClient(ActivityBridgeConfig(url="http://bridge.local"))

    result = client.health()

    assert result["ok"] is False
    assert "connection refused" in result["message"]
