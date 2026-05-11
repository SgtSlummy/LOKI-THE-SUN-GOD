from __future__ import annotations

from collections.abc import Iterable

LAVALINK_EQ_BANDS = 15
MIN_GAIN = -0.25
MAX_GAIN = 1.0

EQ_PRESETS: dict[str, tuple[float, ...]] = {
    "Flat": (0.0,) * LAVALINK_EQ_BANDS,
    "Bass Boost": (0.28, 0.24, 0.18, 0.10, 0.04, 0.0, 0.0, -0.02, -0.03, -0.04, -0.04, -0.03, -0.02, 0.0, 0.0),
    "Vocal Clarity": (-0.08, -0.06, -0.03, 0.0, 0.06, 0.10, 0.14, 0.12, 0.08, 0.05, 0.02, 0.0, 0.0, -0.02, -0.02),
    "Night Mode": (-0.12, -0.10, -0.08, -0.06, -0.03, 0.0, 0.02, 0.02, 0.0, -0.02, -0.04, -0.06, -0.08, -0.10, -0.12),
    "Podcast": (-0.10, -0.08, -0.04, 0.02, 0.08, 0.12, 0.10, 0.06, 0.02, 0.0, -0.02, -0.04, -0.04, -0.04, -0.04),
    "Treble": (-0.08, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.14, 0.12, 0.10),
    "Custom": (0.0,) * LAVALINK_EQ_BANDS,
}


def preset_names() -> list[str]:
    return list(EQ_PRESETS)


def _band_payload(values: Iterable[float]) -> list[dict[str, float | int]]:
    return [{"band": index, "gain": float(gain)} for index, gain in enumerate(values)]


def validate_custom_bands(values: Iterable[float]) -> list[dict[str, float | int]]:
    bands = [float(value) for value in values]
    if len(bands) != LAVALINK_EQ_BANDS:
        raise ValueError(f"Custom equalizer requires exactly {LAVALINK_EQ_BANDS} bands.")
    if any(gain < MIN_GAIN or gain > MAX_GAIN for gain in bands):
        raise ValueError(f"Equalizer gains must be between {MIN_GAIN} and {MAX_GAIN}.")
    return _band_payload(bands)


def bands_for_preset(name: str) -> list[dict[str, float | int]]:
    try:
        values = EQ_PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown equalizer preset: {name}") from exc
    return _band_payload(values)
