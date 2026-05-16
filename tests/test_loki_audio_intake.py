from __future__ import annotations

from loki_music.audio_intake import (
    AudioInputKind,
    HighQualityAudioProfile,
    decide_audio_intake,
)


def test_remote_lavalink_stays_on_primary_streaming_path():
    decision = decide_audio_intake("https://youtube.example/watch?v=abc", AudioInputKind.REMOTE_LAVALINK)

    assert decision.route == "lavalink_direct"
    assert not decision.requires_probe
    assert not decision.requires_transcode
    assert decision.profile == HighQualityAudioProfile()
    assert decision.warnings == ()


def test_spotify_is_metadata_search_only_not_lossless_playback():
    decision = decide_audio_intake("https://open.spotify.com/track/123", AudioInputKind.SPOTIFY_METADATA)

    assert decision.route == "resolve_metadata_then_lavalink_search"
    assert not decision.requires_probe
    assert not decision.requires_transcode
    assert any("metadata/search only" in warning for warning in decision.warnings)
    assert any("lossless Spotify" in warning for warning in decision.warnings)


def test_local_attachment_and_generated_audio_require_probe_and_transcode():
    for kind in (
        AudioInputKind.LOCAL_FILE,
        AudioInputKind.DISCORD_ATTACHMENT,
        AudioInputKind.GENERATED_AUDIO,
    ):
        decision = decide_audio_intake("clip.wav", kind)

        assert decision.route == "ffprobe_then_discord_opus"
        assert decision.requires_probe
        assert decision.requires_transcode
        assert decision.profile.codec == "opus"
        assert decision.profile.sample_rate_hz == 48000
        assert decision.profile.frame_ms == 20


def test_dca_assets_are_validated_without_retranscoding_by_default():
    decision = decide_audio_intake("intro.dca", AudioInputKind.DCA_ASSET)

    assert decision.route == "validate_discord_dca_then_clip_backend"
    assert decision.requires_probe
    assert not decision.requires_transcode
    assert any("pre-encoded Discord Audio" in warning for warning in decision.warnings)


def test_voice_capture_requires_operator_review_and_consent():
    decision = decide_audio_intake("voice-session", AudioInputKind.VOICE_CAPTURE)

    assert decision.route == "operator_review_required"
    assert decision.requires_probe
    assert decision.requires_transcode
    assert any("consent" in warning.lower() for warning in decision.warnings)


def test_all_audio_input_kinds_have_policy_decisions():
    observed = {decide_audio_intake(kind.value, kind).kind for kind in AudioInputKind}

    assert observed == set(AudioInputKind)
