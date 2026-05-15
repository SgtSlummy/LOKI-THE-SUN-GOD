from __future__ import annotations

from scripts.discord_acceptance_probe import (
    Capability,
    acceptance_capabilities,
    mask_token,
    permission_names,
    required_command_names,
)


def test_acceptance_capabilities_separate_automated_substitutes_from_human_gates() -> None:
    capabilities = {capability.name: capability for capability in acceptance_capabilities()}

    assert capabilities["bot_token_identity"].mode == "automated"
    assert capabilities["slash_command_registration"].mode == "automated"
    assert capabilities["npc_message_reply"].mode == "automated_substitute"
    assert capabilities["real_user_slash_invocation"].mode == "human_or_test_client_required"
    assert capabilities["audible_voice_playback"].mode == "human_or_test_client_required"

    assert "bot tokens cannot create Discord user interactions" in capabilities["real_user_slash_invocation"].reason
    assert "separate Discord test client" in capabilities["audible_voice_playback"].automation_path


def test_mask_token_never_returns_raw_secret() -> None:
    token = "abc.defghijklmnop.qrstuvwxyz123456"

    masked = mask_token(token)

    assert token not in masked
    assert masked.startswith("abc.")
    assert masked.endswith("3456")
    assert "..." in masked


def test_permission_names_decode_core_discord_bits() -> None:
    names = permission_names((1 << 10) | (1 << 11) | (1 << 20) | (1 << 31))

    assert names == ["VIEW_CHANNEL", "SEND_MESSAGES", "CONNECT", "USE_APPLICATION_COMMANDS"]


def test_capability_schema_is_stable_for_json_report() -> None:
    capability = Capability(
        name="example",
        mode="automated",
        reason="reason",
        automation_path="path",
    )

    assert capability.to_dict() == {
        "name": "example",
        "mode": "automated",
        "reason": "reason",
        "automation_path": "path",
    }


def test_required_command_names_defaults_to_release_gate_surface() -> None:
    expected = {"ask", "dashboard", "npc", "play", "queue", "stop"}

    assert required_command_names([], None) == expected
    assert required_command_names([], "   ") == expected
    assert required_command_names([""], None) == expected


def test_required_command_names_accepts_repeated_and_delimited_overrides() -> None:
    assert required_command_names(["/ask,npc", "play queue"], "dashboard, stop") == {
        "ask",
        "dashboard",
        "npc",
        "play",
        "queue",
        "stop",
    }
