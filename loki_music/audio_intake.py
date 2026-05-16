from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AudioInputKind(str, Enum):
    """Supported intake classes before LOKI routes audio toward Discord voice."""

    REMOTE_LAVALINK = "remote_lavalink"
    SPOTIFY_METADATA = "spotify_metadata"
    LOCAL_FILE = "local_file"
    DISCORD_ATTACHMENT = "discord_attachment"
    GENERATED_AUDIO = "generated_audio"
    DCA_ASSET = "dca_asset"
    VOICE_CAPTURE = "voice_capture"


@dataclass(frozen=True)
class HighQualityAudioProfile:
    """Discord-safe target for optional local/generated audio preparation."""

    sample_rate_hz: int = 48000
    channels: int = 2
    frame_ms: int = 20
    codec: str = "opus"
    nominal_bitrate_kbps: int = 128
    loudness_lufs: float = -16.0
    true_peak_db: float = -1.5
    preserve_original: bool = True


@dataclass(frozen=True)
class AudioIntakeDecision:
    """Policy decision for probing, transcoding, and routing an audio source."""

    kind: AudioInputKind
    source_label: str
    profile: HighQualityAudioProfile
    route: str
    requires_probe: bool
    requires_transcode: bool
    warnings: tuple[str, ...] = ()


_PROBE_AND_TRANSCODE_KINDS = {
    AudioInputKind.LOCAL_FILE,
    AudioInputKind.DISCORD_ATTACHMENT,
    AudioInputKind.GENERATED_AUDIO,
}


SPOTIFY_METADATA_WARNING = (
    "Spotify links provide metadata/search only; LOKI must not advertise "
    "lossless Spotify playback or direct Spotify stream capture."
)

DCA_ASSET_WARNING = "pre-encoded Discord Audio DCA assets must be validated before any local clip backend uses them."
VOICE_CAPTURE_WARNING = (
    "Voice capture requires explicit operator review, consent, retention policy, and redaction controls."
)


def decide_audio_intake(source: str, kind: AudioInputKind | str) -> AudioIntakeDecision:
    """Return the safe intake route for an audio source.

    Lavalink remains the primary production route for remote media. Local,
    attachment, and generated audio are only policy-classified here; this module
    does not invoke FFmpeg, download media, or touch Discord runtime state.
    """

    input_kind = AudioInputKind(kind)
    source_label = str(source).strip()
    profile = HighQualityAudioProfile()

    if input_kind == AudioInputKind.REMOTE_LAVALINK:
        return AudioIntakeDecision(input_kind, source_label, profile, "lavalink_direct", False, False)

    if input_kind == AudioInputKind.SPOTIFY_METADATA:
        return AudioIntakeDecision(
            input_kind,
            source_label,
            profile,
            "resolve_metadata_then_lavalink_search",
            False,
            False,
            (SPOTIFY_METADATA_WARNING,),
        )

    if input_kind in _PROBE_AND_TRANSCODE_KINDS:
        return AudioIntakeDecision(
            input_kind,
            source_label,
            profile,
            "ffprobe_then_discord_opus",
            True,
            True,
        )

    if input_kind == AudioInputKind.DCA_ASSET:
        return AudioIntakeDecision(
            input_kind,
            source_label,
            profile,
            "validate_discord_dca_then_clip_backend",
            True,
            False,
            (DCA_ASSET_WARNING,),
        )

    if input_kind == AudioInputKind.VOICE_CAPTURE:
        return AudioIntakeDecision(
            input_kind,
            source_label,
            profile,
            "operator_review_required",
            True,
            True,
            (VOICE_CAPTURE_WARNING,),
        )

    raise ValueError(f"Unsupported audio input kind: {input_kind.value}")
