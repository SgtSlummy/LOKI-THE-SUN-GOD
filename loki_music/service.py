from __future__ import annotations

from dataclasses import dataclass, field

from loki_music.equalizer import bands_for_preset, validate_custom_bands


class QueueLimitExceeded(ValueError):
    """Raised when a guild music queue would exceed its configured limit."""


@dataclass(frozen=True)
class Track:
    title: str
    uri: str = ""
    requester_id: int | None = None
    provider: str = "unknown"
    provider_id: str = ""
    duration_ms: int | None = None

    def dedupe_key(self) -> tuple[str, str]:
        """Return a stable provider-aware key for queue/media de-duplication."""

        provider = (self.provider or "unknown").strip().lower() or "unknown"
        provider_id = (self.provider_id or self.uri or self.title).strip()
        return provider, provider_id


@dataclass
class MixerState:
    volume: int = 80
    eq_preset: str = "Flat"
    custom_eq: list[dict[str, float | int]] = field(default_factory=list)
    locked: bool = False

    def set_volume(self, value: int) -> None:
        if value < 0 or value > 150:
            raise ValueError("Volume must be between 0 and 150.")
        self.volume = value

    def set_preset(self, name: str) -> None:
        preset_bands = bands_for_preset(name)
        self.eq_preset = name
        if name == "Custom":
            self.custom_eq = preset_bands
        else:
            self.custom_eq = []

    def set_custom_eq(self, values: list[float]) -> None:
        self.eq_preset = "Custom"
        self.custom_eq = validate_custom_bands(values)

    def current_eq_payload(self) -> list[dict[str, float | int]]:
        if self.eq_preset == "Custom":
            return list(self.custom_eq)
        return bands_for_preset(self.eq_preset)


@dataclass
class MusicSession:
    guild_id: int
    queue: list[Track] = field(default_factory=list)
    current: Track | None = None
    mixer: MixerState = field(default_factory=MixerState)
    loop_mode: str = "off"
    settings_updated_at: int | None = None
    max_queue_size: int = 200

    def __post_init__(self) -> None:
        if not isinstance(self.max_queue_size, int) or isinstance(self.max_queue_size, bool) or self.max_queue_size < 1:
            raise ValueError("max_queue_size must be a positive integer.")

    def ensure_queue_capacity(self, additional_tracks: int = 1) -> None:
        """Raise if adding tracks would exceed the pending queue limit."""

        if additional_tracks < 0:
            raise ValueError("additional_tracks must not be negative.")
        if len(self.queue) + additional_tracks > self.max_queue_size:
            raise QueueLimitExceeded(f"Music queue is limited to {self.max_queue_size} pending tracks.")

    def enqueue(self, track: Track) -> None:
        self.ensure_queue_capacity()
        self.queue.append(track)

    def dequeue_next(self) -> Track | None:
        if not self.queue:
            return None
        self.current = self.queue.pop(0)
        return self.current

    def clear(self) -> None:
        self.queue.clear()
        self.current = None
        self.loop_mode = "off"
