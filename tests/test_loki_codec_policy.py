from __future__ import annotations

from loki_music.codec_policy import DISCORD_VOICE_TARGET, explain_codec


def test_discord_voice_target_is_opus_and_discord_safe():
    assert DISCORD_VOICE_TARGET["codec"] == "opus"
    assert DISCORD_VOICE_TARGET["sample_rate_hz"] == 48000
    assert DISCORD_VOICE_TARGET["channels"] == 2
    assert DISCORD_VOICE_TARGET["frame_ms"] == 20
    assert DISCORD_VOICE_TARGET["max_nominal_bitrate_kbps"] <= 128


def test_explain_codec_distinguishes_discord_dca_from_dts_dca():
    discord_dca = explain_codec("dca")
    dts_dca = explain_codec("dts")

    assert "Discord Audio" in discord_dca
    assert "Opus" in discord_dca
    assert "DTS Coherent Acoustics" in dts_dca
    assert "FFmpeg codec name" in dts_dca
    assert discord_dca != dts_dca


def test_explain_codec_normalizes_common_aliases():
    assert explain_codec("discord-dca") == explain_codec("Discord Audio")
    assert explain_codec("coherent-acoustics") == explain_codec("dts_dca")
    assert explain_codec(" DTS ") == explain_codec("dts_dca")


def test_unknown_codec_explanation_is_safe_and_non_promotional():
    explanation = explain_codec("patched_lossless_discord")

    assert explanation == "Unknown or unsupported codec term."
    assert "lossless" not in explanation.lower()
