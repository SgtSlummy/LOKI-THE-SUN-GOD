from __future__ import annotations

from pathlib import Path

import pytest

from loki_engine.permissions import (
    PermissionContext,
    assert_admin_action,
    can_create_activity_event,
    can_manage_activity,
)
from loki_memory.adapters import available_adapters
from loki_music.equalizer import EQ_PRESETS, bands_for_preset, validate_custom_bands
from loki_music.wavelink_backend import filters_for_bands
from loki_npc.memory import redact_discord_content
from loki_npc.openai_responses import build_responses_payload
from loki_research.discovery import build_candidate
from loki_research.diva_catalog import core_public_commands
from utils.command_catalog import parse_command_catalog


def test_equalizer_presets_are_lavalink_band_payloads_without_public_filter_modes():
    assert "Flat" in EQ_PRESETS
    assert "Bass Boost" in EQ_PRESETS
    assert "Nightcore" not in EQ_PRESETS
    assert "8D" not in EQ_PRESETS

    bass = bands_for_preset("Bass Boost")

    assert len(bass) == 15
    assert bass[0]["band"] == 0
    assert bass[0]["gain"] > bass[-1]["gain"]


def test_custom_equalizer_rejects_bad_band_count_and_gain_range():
    assert validate_custom_bands([0.0] * 15)[-1] == {"band": 14, "gain": 0.0}

    for invalid in ([0.0] * 14, [0.0] * 16, [2.0] + [0.0] * 14):
        try:
            validate_custom_bands(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid EQ bands should fail validation")


def test_wavelink_filters_accept_lavalink_equalizer_payloads():
    filters = filters_for_bands(bands_for_preset("Podcast"))

    assert filters.equalizer.payload[0]["band"] == 0
    assert filters.equalizer.payload[0]["gain"] < 0


def test_admin_actions_require_discord_admin_or_manage_guild_permission():
    normal_user = PermissionContext(user_id=1, guild_id=10, permissions=0)
    admin_user = PermissionContext(user_id=2, guild_id=10, permissions=0x8)
    manager_user = PermissionContext(user_id=3, guild_id=10, permissions=0x20)

    assert not normal_user.can_manage_guild
    assert admin_user.can_manage_guild
    assert manager_user.can_manage_guild
    assert assert_admin_action(admin_user, "update_npc_settings").allowed
    assert not assert_admin_action(normal_user, "update_npc_settings").allowed


def test_activity_management_accepts_manage_events_without_full_admin():
    create_events = PermissionContext(user_id=4, guild_id=10, permissions=0x8000000000)
    manage_events = PermissionContext(user_id=5, guild_id=10, permissions=0x2000000000)

    assert can_manage_activity(create_events).allowed
    assert can_manage_activity(manage_events).allowed
    assert can_create_activity_event(create_events).allowed
    assert not can_create_activity_event(manage_events).allowed


def test_npc_payload_uses_responses_api_storage_opt_out(monkeypatch):
    monkeypatch.setenv("LOKI_LLM_MODEL", "gpt-5.5")

    payload = build_responses_payload(
        user_prompt="what should the server play next?",
        persona="dry solar trickster",
        memory_context=["Members liked synthwave links this week."],
    )

    assert payload["model"] == "gpt-5.5"
    assert payload["store"] is False
    assert payload["reasoning"]["effort"] == "low"
    assert "dry solar trickster" in payload["input"][0]["content"]
    assert "synthwave" in payload["input"][0]["content"]


def test_discord_memory_redaction_removes_sensitive_values():
    raw = "email me at user@example.com with token abc.def.ghi and key sk-testsecret"

    redacted = redact_discord_content(raw)

    assert "user@example.com" not in redacted
    assert "abc.def.ghi" not in redacted
    assert "sk-testsecret" not in redacted
    assert "[email]" in redacted
    assert "[secret]" in redacted


def test_codex_agi_adapters_are_advisory_and_source_mapped():
    adapters = {adapter.key: adapter for adapter in available_adapters()}

    assert {"noophyte", "quantum_roots", "swarm_brain", "slime_god", "camelot"}.issubset(adapters)
    assert all(adapter.mode == "advisory" for adapter in adapters.values())
    assert adapters["slime_god"].source_path.endswith("micro_projects/slime_god")


def test_public_diva_catalog_keeps_clean_room_boundary_and_eq_extension():
    commands = {command.name: command for command in core_public_commands()}

    for expected in {"play", "stop", "queue", "skip", "pause", "resume", "volume", "lyrics", "webplayer"}:
        assert expected in commands

    assert "filter" not in commands
    assert commands["eq"].extension == "LOKI"
    assert commands["mixer"].extension == "LOKI"


def test_loki_command_catalog_exposes_music_npc_and_activity_surfaces():
    catalog = parse_command_catalog(Path(__file__).resolve().parents[1])
    names = {item["full_name"] for item in catalog}

    assert {"play", "eq", "mixer", "npc status", "activity status"}.issubset(names)


def test_web_discovery_candidates_require_source_confidence_and_safety():
    candidate = build_candidate(
        title="New synthwave game soundtrack",
        source_url="https://example.com/synthwave",
        summary="A soundtrack roundup for synthwave and indie game fans.",
        community_terms=["synthwave", "indie games"],
    )

    assert candidate.confidence == 1.0
    assert candidate.safety_status == "pending_review"
    assert "synthwave" in candidate.reason_for_fit

    blocked = build_candidate(
        title="token grabber",
        source_url="ftp://example.com/file",
        summary="malware",
        community_terms=["music"],
    )

    assert blocked.safety_status == "blocked"


def test_relay_sensitive_sources_cover_configured_and_ticket_channels(monkeypatch, tmp_path):
    pytest.importorskip("discord")
    from cogs.relay import Relay
    from utils import db

    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    relay = Relay.__new__(Relay)
    relay.sensitive_source_ids = {"55", "999"}

    class Guild:
        id = 10

    class Channel:
        id = 123
        parent_id = 55
        category_id = None
        parent = None
        category = None

    assert relay._is_sensitive_source(Channel(), Guild())

    db.sync_exec(
        """
        INSERT INTO tickets(guild_id, channel_id, opener_id, status, opened_at, reason)
        VALUES(?,?,?,?,?,?)
        """,
        (10, 456, 1, "open", 1, "private help"),
    )

    class TicketChannel:
        id = 456
        parent_id = None
        category_id = None
        parent = None
        category = None

    assert relay._is_sensitive_source(TicketChannel(), Guild())


def test_npc_channel_allowlist_and_private_channel_detection(monkeypatch):
    pytest.importorskip("discord")
    from cogs.loki_npc import LokiNpc

    class Permissions:
        def __init__(self, view_channel: bool):
            self.view_channel = view_channel

    class Guild:
        default_role = object()

    class Channel:
        id = 222
        parent_id = None
        category_id = 999
        parent = None
        category = None

        def __init__(self, view_channel: bool):
            self._view_channel = view_channel

        def permissions_for(self, role):
            return Permissions(self._view_channel)

    npc = LokiNpc.__new__(LokiNpc)
    monkeypatch.setenv("LOKI_NPC_ALLOWED_CHANNEL_IDS", "999")

    assert npc._channel_allowed(Channel(view_channel=True))
    assert not npc._is_private_channel(Channel(view_channel=True), Guild())
    assert npc._is_private_channel(Channel(view_channel=False), Guild())
