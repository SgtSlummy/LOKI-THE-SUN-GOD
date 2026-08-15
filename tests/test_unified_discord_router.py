from __future__ import annotations

import asyncio

import pytest

from utils.llm_client import configured_api_key, openai_base_url, tarot_router_enabled
from utils.unified_discord_router import (
    AutoDMGatewayClient,
    IntegrationConfigError,
    autodm_channel_ids,
    mythos_route,
)


class FakeAutoDMTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict | None]] = []

    async def request(self, method, path, *, actor_id, payload=None):
        self.calls.append((method, path, actor_id, payload))
        if path == "/bootstrap":
            return {
                "profile": {"id": "profile-1"},
                "characters": [{"id": "character-1", "template": "mecha-cannibal"}],
                "campaigns": [{"id": "campaign-1", "character_id": "character-1"}],
            }
        if path == "/campaigns/campaign-1" and method == "GET":
            return {"campaign": {"id": "campaign-1", "version": 7}}
        if path == "/campaigns/campaign-1/turns":
            return {"turn": {"narrative": "The Dawn Key answers your strike."}}
        raise AssertionError(f"unexpected AutoDM request: {method} {path}")


@pytest.fixture(autouse=True)
def clear_router_environment(monkeypatch):
    for name in (
        "AUTODM_DISCORD_CHANNEL_ID",
        "AUTODM_DISCORD_CHANNEL_IDS",
        "MYTHOS_ROUTER_ENABLED",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "TAROT_ROUTER_API_KEY",
        "TAROT_ROUTER_BASE_URL",
        "TAROT_ROUTER_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_mythos_router_matches_autodm_compatibility_routes(monkeypatch):
    monkeypatch.setenv("MYTHOS_ROUTER_ENABLED", "true")

    assert mythos_route("Fight the dragon").route == "combat"
    assert mythos_route("Explore the old ruin").route == "exploration"
    assert mythos_route("Find the lost artifact quest").route == "quest"
    assert mythos_route("Talk to the suspicious noble").route == "social"
    assert mythos_route("I wait for dawn").route == "default"


def test_autodm_channel_ids_supports_singular_and_plural_names(monkeypatch):
    monkeypatch.setenv("AUTODM_DISCORD_CHANNEL_ID", "123")
    assert autodm_channel_ids() == frozenset({123})

    monkeypatch.setenv("AUTODM_DISCORD_CHANNEL_IDS", "123, 456")
    assert autodm_channel_ids() == frozenset({123, 456})


def test_remote_autodm_requires_explicit_approval_and_backend_token():
    with pytest.raises(IntegrationConfigError, match="AUTODM_ALLOW_REMOTE"):
        AutoDMGatewayClient(base_url="https://autodm.example/v1/solo")
    with pytest.raises(IntegrationConfigError, match="BACKEND_TOKEN"):
        AutoDMGatewayClient(base_url="https://autodm.example/v1/solo", allow_remote=True)


def test_autodm_turn_is_actor_scoped_ordered_and_idempotent(monkeypatch):
    monkeypatch.setenv("MYTHOS_ROUTER_ENABLED", "true")
    transport = FakeAutoDMTransport()
    client = AutoDMGatewayClient(transport=transport)

    result = asyncio.run(
        client.process_message(
            channel_id=1521993941396750337,
            user_id=42,
            display_name="MythosPlayer",
            message_id=99,
            content="Fight the dragon at the bridge",
        )
    )

    assert result.campaign_id == "campaign-1"
    assert result.route == "combat"
    assert result.narrative == "The Dawn Key answers your strike."
    turn_call = transport.calls[-1]
    assert turn_call[2] == "discord:1521993941396750337:42"
    assert turn_call[3] == {
        "action": "Fight the dragon at the bridge",
        "ability": "strength",
        "expected_version": 7,
        "idempotency_key": "discord:1521993941396750337:99",
        "command_id": "discord:1521993941396750337:99",
    }


def test_tarot_router_is_an_explicit_openai_compatible_route(monkeypatch):
    monkeypatch.setenv("TAROT_ROUTER_ENABLED", "true")
    monkeypatch.setenv("TAROT_ROUTER_BASE_URL", "http://127.0.0.1:8642/v1/")

    assert tarot_router_enabled()
    assert openai_base_url() == "http://127.0.0.1:8642/v1"
    assert configured_api_key() == ""

    monkeypatch.setenv("TAROT_ROUTER_API_KEY", "configured-in-protected-environment")
    assert configured_api_key() == "configured-in-protected-environment"
