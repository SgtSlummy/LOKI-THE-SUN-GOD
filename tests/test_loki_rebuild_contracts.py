from __future__ import annotations

import asyncio
import inspect
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
from loki_music.service import MusicSession, QueueLimitExceeded, Track
from loki_music.wavelink_backend import WavelinkBackend, filters_for_bands, music_runtime_status
from loki_npc.memory import (
    DEFAULT_MEMORY_TTL_SECONDS,
    purge_expired_public_memory,
    purge_user_memory,
    redact_discord_content,
)
from loki_npc.openai_responses import ask_npc, build_responses_payload
from loki_npc.persona import default_persona, persona_from_settings
from loki_research.discovery import build_candidate
from loki_research.diva_catalog import core_public_commands
from loki_research.experiments import (
    ExperimentConfig,
    MutationCandidate,
    append_experiment_audit,
    assert_safe_experiment_config,
    score_mutation_candidate,
)
from utils.command_catalog import parse_command_catalog


def test_music_tracks_provide_provider_aware_dedupe_keys():
    track = Track(
        title="Solar Hymn",
        uri="https://media.example/solar-hymn.ogg",
        provider="Internet_Archive",
        provider_id="Solar-Hymn",
        duration_ms=123000,
    )

    assert track.dedupe_key() == ("internet_archive", "Solar-Hymn")
    assert Track(title="Fallback", uri="HTTPS://EXAMPLE.COM/A.OGG").dedupe_key() == (
        "unknown",
        "HTTPS://EXAMPLE.COM/A.OGG",
    )


def test_music_session_enforces_guild_queue_limit():
    session = MusicSession(guild_id=10, max_queue_size=1)
    session.enqueue(Track(title="first"))

    with pytest.raises(QueueLimitExceeded):
        session.enqueue(Track(title="second"))

    with pytest.raises(ValueError):
        MusicSession(guild_id=10, max_queue_size=0)

    with pytest.raises(ValueError):
        MusicSession(guild_id=10, max_queue_size=True)


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


def test_music_runtime_status_reports_voice_and_lavalink_readiness(monkeypatch):
    monkeypatch.setenv("LAVALINK_URI", "https://lavalink.example.invalid")
    monkeypatch.setenv("LAVALINK_PASSWORD", "not-a-secret-in-test")

    status = music_runtime_status()

    assert status["wavelink_installed"] is True
    assert status["pynacl_installed"] is True
    assert status["davey_installed"] is True
    assert status["discord_voice_installed"] is True
    assert status["lavalink_configured"] is True
    assert status["ready"] is True
    assert status["missing"] == []


def test_loki_voice_connection_joins_deafened():
    source = inspect.getsource(WavelinkBackend.ensure_player)

    assert "self_deaf=True" in source
    assert "self_deaf=False" not in source


def test_loki_jukebox_embed_lists_current_track_and_queue():
    pytest.importorskip("discord")
    from cogs.loki_music import LokiMusic

    session = MusicSession(guild_id=123)
    session.current = Track(title="Sun God Intro")
    session.enqueue(Track(title="Golden Hour"))
    session.enqueue(Track(title="Temple Bass"))

    cog = LokiMusic.__new__(LokiMusic)
    embed = cog.jukebox_embed_for(session)

    assert embed.title == "LOKI Jukebox"
    fields = {field.name: field.value for field in embed.fields}
    assert fields["Now playing"] == "Sun God Intro"
    assert "1. Golden Hour" in fields["Song list"]
    assert "2. Temple Bass" in fields["Song list"]


def test_wavelink_play_queues_requested_track_before_fallbacks_when_already_playing():
    class FakePlayable:
        def __init__(self, title):
            self.title = title
            self.uri = f"https://example.invalid/{title}"

    class FakeQueue:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    class FakePlayer:
        playing = True
        paused = False

        def __init__(self):
            self.queue = FakeQueue()

    async def fake_ensure_node(_bot):
        return None

    async def fake_resolve_tracks(_query):
        return [FakePlayable("requested"), FakePlayable("fallback-1"), FakePlayable("fallback-2")]

    async def fake_ensure_player(_ctx):
        return player

    backend = WavelinkBackend()
    player = FakePlayer()
    backend.ensure_node = fake_ensure_node
    backend.resolve_tracks = fake_resolve_tracks
    backend.ensure_player = fake_ensure_player
    session = MusicSession(guild_id=123)
    ctx = type("Ctx", (), {"bot": object()})()

    result = asyncio.run(backend.play(ctx, session, "requested", requester_id=42))

    assert result.started is False
    assert [item.title for item in player.queue.items] == ["requested", "fallback-1", "fallback-2"]
    assert [track.title for track in session.queue] == ["requested", "fallback-1", "fallback-2"]


def test_wavelink_play_does_not_mutate_player_queue_when_session_limit_is_hit():
    class FakePlayable:
        def __init__(self, title):
            self.title = title
            self.uri = f"https://example.invalid/{title}"

    class FakeQueue:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    class FakePlayer:
        playing = True
        paused = False

        def __init__(self):
            self.queue = FakeQueue()

    async def fake_ensure_node(_bot):
        return None

    async def fake_resolve_tracks(_query):
        return [FakePlayable("requested"), FakePlayable("fallback")]

    async def fake_ensure_player(_ctx):
        return player

    backend = WavelinkBackend()
    player = FakePlayer()
    backend.ensure_node = fake_ensure_node
    backend.resolve_tracks = fake_resolve_tracks
    backend.ensure_player = fake_ensure_player
    session = MusicSession(guild_id=123, max_queue_size=1)
    ctx = type("Ctx", (), {"bot": object()})()

    with pytest.raises(QueueLimitExceeded):
        asyncio.run(backend.play(ctx, session, "requested", requester_id=42))

    assert player.queue.items == []
    assert session.queue == []


def test_loki_queue_loop_advances_without_transient_queue_limit_failure():
    pytest.importorskip("discord")
    from cogs.loki_music import LokiMusic

    class FakePlayable:
        title = "next"
        uri = "https://example.invalid/next"

    class FakePlayerQueue:
        def __init__(self):
            self.items = [FakePlayable()]

        @property
        def is_empty(self):
            return not self.items

        def get(self):
            return self.items.pop(0)

    class FakePlayer:
        def __init__(self):
            self.guild = type("Guild", (), {"id": 123})()
            self.queue = FakePlayerQueue()
            self.played = []

        async def play(self, playable, **_kwargs):
            self.played.append(playable)

    class FakeBackend:
        def filters_for_bands(self, _bands):
            return None

    session = MusicSession(guild_id=123, max_queue_size=1)
    session.current = Track(title="current")
    session.loop_mode = "queue"
    session.enqueue(Track(title="next"))

    cog = LokiMusic.__new__(LokiMusic)
    cog.backend = FakeBackend()
    cog.session_for = lambda _guild_id: session
    updates = []

    async def fake_update_jukebox(*_args, **kwargs):
        updates.append(kwargs.get("reason"))

    cog._update_jukebox = fake_update_jukebox
    player = FakePlayer()
    payload = type("Payload", (), {"player": player, "track": object()})()

    asyncio.run(cog._play_next_after_current(payload))

    assert player.played
    assert session.current.title == "next"
    assert [track.title for track in session.queue] == ["current"]
    assert updates == ["track advance"]


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


def test_npc_uses_hermes_cli_fallback_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LOKI_NPC_HERMES_FALLBACK", "true")
    hermes_path = str(Path("C:/tools/hermes.exe").resolve())
    monkeypatch.setattr("loki_npc.openai_responses.shutil.which", lambda command: hermes_path)

    def fake_run(command, *, capture_output, env, text, timeout, check):
        assert command[:4] == [hermes_path, "chat", "-Q", "-q"]
        assert "LOKI THE SUN GOD" in command[4]
        assert "\x00" not in command[4]
        assert env["PATH"].startswith(str(Path(hermes_path).parent))
        return type("Result", (), {"stdout": "LOKI via Hermes online.\n"})()

    monkeypatch.setattr("loki_npc.openai_responses.subprocess.run", fake_run)

    assert asyncio.run(ask_npc(prompt="status\x00", persona="warm", memory_context=[])) == "LOKI via Hermes online."


def test_npc_returns_operator_diagnostic_when_no_hosted_brain_is_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LOKI_NPC_HERMES_FALLBACK", "true")
    monkeypatch.setattr("loki_npc.openai_responses.shutil.which", lambda command: None)

    answer = asyncio.run(ask_npc(prompt="status", persona="warm", memory_context=[]))

    assert "hosted NPC brain is not configured" in answer
    assert "OPENAI_API_KEY" in answer


def test_default_persona_uses_safe_public_domain_loki_theme():
    persona = default_persona(10)
    prompt = persona.prompt_text().lower()

    assert "loki" in persona.name.lower()
    assert "roleplay" in prompt
    assert "public server context" in prompt
    assert "admin-only" in prompt
    assert "sentient" not in prompt
    assert "autonomous" not in prompt


def test_persona_from_settings_validates_json_and_rejects_unsafe_selfhood_claims():
    valid = persona_from_settings(
        10,
        """
        {
          "summary": "A threshold guardian with solar wit.",
          "backstory": "Uses public-domain Loki motifs as server roleplay.",
          "voice_rules": ["Keep decisions clear.", "Do not bypass admin gates."]
        }
        """,
    )
    unsafe = persona_from_settings(10, '{"summary": "I am sentient and can bypass admin permissions."}')
    invalid = persona_from_settings(10, "{not json")

    assert "threshold guardian" in valid.prompt_text()
    assert valid != default_persona(10)
    assert unsafe == default_persona(10)
    assert invalid == default_persona(10)


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
    activity = {item["full_name"]: item for item in catalog if item["full_name"].startswith("activity")}
    assert activity["activity create-event"]["permissions"] == ["create_events"]
    assert activity["activity end-event"]["permissions"] == ["manage_events"]


def test_appcmd_polish_covers_top_level_permission_gated_slash_commands():
    from cogs.appcmd_polish import PERM_GATED

    missing = []
    for command in parse_command_catalog(Path(__file__).resolve().parents[1]):
        if command["slash_enabled"] and command["permissions"] and not command["group"]:
            if command["command"] not in PERM_GATED:
                missing.append(command["full_name"])

    assert not missing


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

    for private_url in (
        "http://127.0.0.1:5000/healthz",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/internal",
        "http://service.internal/post",
    ):
        candidate = build_candidate(
            title="private",
            source_url=private_url,
            summary="private resource",
            community_terms=["private"],
        )
        assert candidate.safety_status == "blocked"


def test_self_research_experiment_config_rejects_production_and_unsafe_paths(monkeypatch, tmp_path):
    lab_root = tmp_path / "lab"
    safe = ExperimentConfig(enabled=True, lab_root=lab_root, sandbox_path=lab_root / "run-1")

    assert assert_safe_experiment_config(safe).ok

    outside = ExperimentConfig(enabled=True, lab_root=lab_root, sandbox_path=tmp_path / "outside")
    assert not assert_safe_experiment_config(outside).ok

    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert not assert_safe_experiment_config(safe).ok


def test_mutation_candidates_require_reviewable_safety_paths_and_rollback(tmp_path):
    config = ExperimentConfig(
        enabled=True,
        lab_root=tmp_path / "lab",
        sandbox_path=tmp_path / "lab" / "run-1",
        allowed_target_globs=("docs/**", "tests/**"),
    )
    accepted = MutationCandidate(
        candidate_id="cand-1",
        title="Improve docs",
        target_paths=("docs/SELF_RESEARCH_EXPERIMENTS.md",),
        patch_bytes=512,
        safety_status="pending_review",
        source_confidence=0.9,
        rollback_plan="reverse patch available",
        verification_commands=("python -m pytest tests/test_loki_rebuild_contracts.py",),
    )
    blocked = MutationCandidate(
        candidate_id="cand-2",
        title="Touch secrets",
        target_paths=(".env",),
        patch_bytes=128,
        safety_status="pending_review",
        source_confidence=0.9,
        rollback_plan="reverse patch available",
    )
    no_rollback = MutationCandidate(
        candidate_id="cand-3",
        title="No rollback",
        target_paths=("docs/PLAN.md",),
        patch_bytes=128,
        safety_status="pending_review",
        source_confidence=0.9,
        rollback_plan="",
    )

    assert score_mutation_candidate(config, accepted).accepted
    assert not score_mutation_candidate(config, blocked).accepted
    assert not score_mutation_candidate(config, no_rollback).accepted


def test_experiment_audit_redacts_sensitive_details(monkeypatch, tmp_path):
    from utils import db

    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()

    append_experiment_audit(
        run_id="run-1",
        candidate_id="cand-1",
        event_type="proposed",
        details="token abc.def.ghi and email user@example.com",
    )
    row = db.sync_one("SELECT details FROM loki_experiment_audit WHERE run_id=?", ("run-1",))

    assert "abc.def.ghi" not in row["details"]
    assert "user@example.com" not in row["details"]
    assert "[secret]" in row["details"]
    assert "[email]" in row["details"]


def test_public_memory_retention_and_user_purge(monkeypatch, tmp_path):
    from utils import db

    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()
    now = 2_000_000_000
    old = now - DEFAULT_MEMORY_TTL_SECONDS - 1
    recent = now - 60
    db.sync_exec(
        """
        INSERT INTO loki_memory_entries(guild_id, channel_id, user_id, redacted_content, confidence, created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (10, 20, 30, "old memory", 0.4, old),
    )
    db.sync_exec(
        """
        INSERT INTO loki_memory_entries(guild_id, channel_id, user_id, redacted_content, confidence, created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (10, 20, 31, "recent memory", 0.4, recent),
    )

    assert purge_expired_public_memory(guild_id=10, now=now) == 1
    assert [row["redacted_content"] for row in db.sync_all("SELECT redacted_content FROM loki_memory_entries")] == [
        "recent memory"
    ]
    assert purge_user_memory(guild_id=10, user_id=31) == 1
    assert not db.sync_all("SELECT redacted_content FROM loki_memory_entries")


def test_config_global_check_uses_shared_manage_guild_bypass(monkeypatch, tmp_path):
    from cogs.config import _global_check
    from utils import db

    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))
    db.init_sync()
    db.sync_exec("INSERT INTO disabled_commands(guild_id, command) VALUES(?,?)", (10, "play"))
    db.sync_exec("INSERT INTO ignored_channels(guild_id, channel_id) VALUES(?,?)", (10, 20))

    class Guild:
        id = 10

    class Channel:
        id = 20

    class Command:
        qualified_name = "play"

    class Permissions:
        def __init__(self, *, administrator=False, manage_guild=False):
            self.administrator = administrator
            self.manage_guild = manage_guild

    class Author:
        id = 30

        def __init__(self, permissions):
            self.guild_permissions = permissions

    class Ctx:
        guild = Guild()
        channel = Channel()
        command = Command()

        def __init__(self, permissions):
            self.author = Author(permissions)

    assert not asyncio.run(_global_check(Ctx(Permissions())))
    assert asyncio.run(_global_check(Ctx(Permissions(manage_guild=True))))
    assert asyncio.run(_global_check(Ctx(Permissions(administrator=True))))


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




def test_loki_npc_routes_mentioned_admin_changes_through_natural_language_policy():
    pytest.importorskip("discord")
    from cogs.loki_npc import LokiNpc

    class Permissions:
        value = 0

    class Author:
        id = 30
        guild_permissions = Permissions()

    class Guild:
        id = 10

    class Message:
        author = Author()
        guild = Guild()

    npc = LokiNpc.__new__(LokiNpc)

    route = npc._route_natural_language_prompt("change the welcome channel", Message())

    assert not route.allowed
    assert route.intent == "admin_change"
    assert "administrator or manage-guild" in route.reason.lower()


def test_loki_npc_accepts_natural_name_addressing_without_discord_mention():
    pytest.importorskip("discord")
    from cogs.loki_npc import LokiNpc

    class BotUser:
        id = 99
        display_name = "LOKI THE SUN GOD"
        name = "LOKI THE SUN GOD"

    class Bot:
        user = BotUser()

    class Message:
        clean_content = "hey loki, are you online?"
        mentions = []

    npc = LokiNpc(Bot())

    assert npc._is_addressed_to_loki(Message())
    assert npc._prompt_without_address(Message()) == "are you online?"


def test_loki_npc_routes_natural_play_requests_to_music_query():
    from cogs.loki_npc import LokiNpc

    assert LokiNpc._music_query_from_prompt("play lofi hip hop") == "lofi hip hop"
    assert LokiNpc._music_query_from_prompt("please queue music synthwave radio!") == "synthwave radio"
    assert LokiNpc._music_query_from_prompt("what is playing?") is None
    assert LokiNpc._music_query_from_prompt("play music") is None


def test_npc_channel_allowlist_and_private_channel_detection(monkeypatch):

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
