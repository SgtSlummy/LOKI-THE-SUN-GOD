from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import discord

from loki_music.service import MusicSession, Track

try:
    import wavelink
except ImportError:  # pragma: no cover - exercised only when optional runtime dep is absent
    wavelink = None


class MusicBackendUnavailable(RuntimeError):
    pass


class VoiceChannelRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaybackResult:
    track: Track
    started: bool
    backend: str


def filters_for_bands(bands: list[dict[str, float | int]]) -> Any:
    if wavelink is None:
        raise MusicBackendUnavailable("wavelink is not installed.")
    filters = wavelink.Filters()
    filters.equalizer.set(bands=bands)
    return filters


class WavelinkBackend:
    """Thin Lavalink/Wavelink runtime adapter for the LOKI command surface."""

    def __init__(self):
        self._connected = False

    @property
    def available(self) -> bool:
        return wavelink is not None

    async def ensure_node(self, bot: discord.Client) -> None:
        if wavelink is None:
            raise MusicBackendUnavailable("wavelink is not installed.")
        if self._connected and wavelink.Pool.nodes:
            return

        uri = (os.getenv("LAVALINK_URI") or "").strip()
        password = (os.getenv("LAVALINK_PASSWORD") or "").strip()
        if not uri or not password:
            raise MusicBackendUnavailable("LAVALINK_URI and LAVALINK_PASSWORD are required.")

        node = wavelink.Node(
            uri=uri,
            password=password,
            identifier=os.getenv("LAVALINK_NODE_ID", "LOKI-LAVALINK"),
        )
        await wavelink.Pool.connect(nodes=[node], client=bot)
        self._connected = True

    async def resolve_track(self, query: str) -> Any:
        if wavelink is None:
            raise MusicBackendUnavailable("wavelink is not installed.")
        results = await wavelink.Playable.search(query)
        if isinstance(results, list):
            return results[0] if results else None
        playlist_tracks = getattr(results, "tracks", None)
        if playlist_tracks:
            return playlist_tracks[0]
        return None

    async def ensure_player(self, ctx: Any) -> Any:
        if wavelink is None:
            raise MusicBackendUnavailable("wavelink is not installed.")
        voice_state = getattr(getattr(ctx, "author", None), "voice", None)
        channel = getattr(voice_state, "channel", None)
        if channel is None:
            raise VoiceChannelRequired("Join a voice channel before using live LOKI playback.")

        player = getattr(ctx, "voice_client", None)
        if isinstance(player, wavelink.Player):
            return player
        return await channel.connect(cls=wavelink.Player, self_deaf=True)

    async def play(self, ctx: Any, session: MusicSession, query: str, requester_id: int | None) -> PlaybackResult:
        await self.ensure_node(ctx.bot)
        playable = await self.resolve_track(query)
        if playable is None:
            raise MusicBackendUnavailable("No playable Lavalink result was found.")
        player = await self.ensure_player(ctx)

        track = Track(
            title=str(getattr(playable, "title", query) or query),
            uri=str(getattr(playable, "uri", query) or query),
            requester_id=requester_id,
        )

        if getattr(player, "playing", False) or getattr(player, "paused", False):
            player.queue.put(playable)
            session.enqueue(track)
            return PlaybackResult(track=track, started=False, backend="wavelink")

        session.current = track
        await player.play(
            playable,
            volume=session.mixer.volume,
            filters=filters_for_bands(session.mixer.current_eq_payload()),
        )
        return PlaybackResult(track=track, started=True, backend="wavelink")

    async def apply_volume(self, ctx: Any, volume: int) -> bool:
        player = getattr(ctx, "voice_client", None)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.set_volume(volume)
        return True

    async def apply_eq(self, ctx: Any, session: MusicSession) -> bool:
        player = getattr(ctx, "voice_client", None)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.set_filters(filters_for_bands(session.mixer.current_eq_payload()))
        return True

    def filters_for_bands(self, bands: list[dict[str, float | int]]) -> Any:
        return filters_for_bands(bands)

    async def pause(self, ctx: Any, paused: bool) -> bool:
        player = getattr(ctx, "voice_client", None)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.pause(paused)
        return True

    async def skip(self, ctx: Any) -> bool:
        player = getattr(ctx, "voice_client", None)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.skip(force=True)
        return True

    async def stop(self, ctx: Any) -> bool:
        player = getattr(ctx, "voice_client", None)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        player.queue.clear()
        await player.stop(force=True)
        return True
