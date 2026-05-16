from __future__ import annotations

DISCORD_VOICE_TARGET = {
    "codec": "opus",
    "sample_rate_hz": 48000,
    "channels": 2,
    "frame_ms": 20,
    "max_nominal_bitrate_kbps": 128,
}

CODEC_ALIASES = {
    "discord_dca": "Discord Audio DCA container / pre-encoded Opus frame stream for Discord voice clips.",
    "dts_dca": "DTS Coherent Acoustics codec; FFmpeg codec name dca under dts input handling.",
}

_DISCORD_DCA_TERMS = {"dca", "discord_audio", "discord_dca", "discord_audio_dca"}
_DTS_DCA_TERMS = {"dts", "dts_dca", "coherent_acoustics"}


def explain_codec(term: str) -> str:
    """Explain codec vocabulary without promising unsupported Discord playback."""

    normalized = str(term).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _DISCORD_DCA_TERMS:
        return CODEC_ALIASES["discord_dca"]
    if normalized in _DTS_DCA_TERMS:
        return CODEC_ALIASES["dts_dca"]
    return "Unknown or unsupported codec term."
