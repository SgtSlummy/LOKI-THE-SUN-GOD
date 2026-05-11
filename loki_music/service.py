from __future__ import annotations

from dataclasses import dataclass, field

from loki_music.equalizer import bands_for_preset, validate_custom_bands


@dataclass(frozen=True)
class Track:
    title: str
    uri: str = ""
    requester_id: int | None = None


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

    def enqueue(self, track: Track) -> None:
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
