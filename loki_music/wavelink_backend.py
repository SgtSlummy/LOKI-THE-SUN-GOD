from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import re
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


class TrackResolutionFailed(RuntimeError):
    pass


class VoiceChannelRequired(RuntimeError):
    pass


log = logging.getLogger("loki.music.wavelink")


def music_runtime_status() -> dict[str, Any]:
    """Return a redacted readiness snapshot for live Discord music playback."""

    missing: list[str] = []
    wavelink_installed = wavelink is not None
    pynacl_installed = importlib.util.find_spec("nacl") is not None
    davey_installed = importlib.util.find_spec("davey") is not None
    discord_voice_installed = pynacl_installed and davey_installed
    lavalink_configured = bool((os.getenv("LAVALINK_URI") or "").strip()) and bool(
        (os.getenv("LAVALINK_PASSWORD") or "").strip()
    )

    if not wavelink_installed:
        missing.append("wavelink")
    if not pynacl_installed:
        missing.append("PyNaCl")
    if not davey_installed:
        missing.append("davey")
    if not lavalink_configured:
        missing.append("LAVALINK_URI/LAVALINK_PASSWORD")

    return {
        "wavelink_installed": wavelink_installed,
        "pynacl_installed": pynacl_installed,
        "davey_installed": davey_installed,
        "discord_voice_installed": discord_voice_installed,
        "lavalink_configured": lavalink_configured,
        "ready": not missing,
        "missing": missing,
    }


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
        if self._connected and self._connected_node_count() > 0:
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
        for _ in range(20):
            if self._connected_node_count() > 0:
                self._connected = True
                return
            await asyncio.sleep(0.25)
        self._connected = False
        raise MusicBackendUnavailable("Lavalink node did not reach CONNECTED state yet.")

    @staticmethod
    def _connected_node_count() -> int:
        if wavelink is None:
            return 0
        count = 0
        for node in getattr(wavelink.Pool, "nodes", {}).values():
            status = str(getattr(node, "status", "")).upper()
            if "CONNECTED" in status:
                count += 1
        return count

    @staticmethod
    def _looks_like_url(query: str) -> bool:
        return bool(re.match(r"^[a-z][a-z0-9+.-]*://", query.strip(), flags=re.IGNORECASE))

    @staticmethod
    def _is_spotify_url(query: str) -> bool:
        normalized = query.strip().lower()
        return normalized.startswith("spotify:") or bool(
            re.match(r"^https?://(?:open\.)?spotify\.(?:com|link)/", normalized, flags=re.IGNORECASE)
        )

    @staticmethod
    def _spotify_metadata_message() -> str:
        return (
            "Spotify links are metadata/search only for now; LOKI cannot stream directly from Spotify. "
            "Paste a song/artist search, YouTube URL, or SoundCloud URL instead."
        )

    async def resolve_tracks(self, query: str, *, limit: int = 5) -> list[Any]:
        if wavelink is None:
            raise MusicBackendUnavailable("wavelink is not installed.")
        sources: list[Any]
        if self._looks_like_url(query):
            sources = [None]
        else:
            sources = [wavelink.TrackSource.SoundCloud, wavelink.TrackSource.YouTubeMusic, wavelink.TrackSource.YouTube]

        for source in sources:
            try:
                results = await wavelink.Playable.search(query, source=source)
            except (
                wavelink.InvalidNodeException,
                wavelink.LavalinkException,
                wavelink.LavalinkLoadException,
            ) as exc:
                log.warning(
                    "Lavalink search failed for source=%s query=%r: %s",
                    source,
                    query,
                    exc,
                    exc_info=True,
                )
                continue
            if isinstance(results, list):
                tracks = results
            else:
                tracks = list(getattr(results, "tracks", None) or [])
            if tracks:
                return tracks[:limit]
        return []

    async def resolve_track(self, query: str) -> Any:
        tracks = await self.resolve_tracks(query, limit=1)
        return tracks[0] if tracks else None

    async def ensure_player(self, ctx: Any) -> Any:
        if wavelink is None:
            raise MusicBackendUnavailable("wavelink is not installed.")
        voice_state = getattr(getattr(ctx, "author", None), "voice", None)
        channel = getattr(voice_state, "channel", None)
        if channel is None:
            raise VoiceChannelRequired("Join a voice channel before using live LOKI playback.")

        player = getattr(ctx, "voice_client", None) or getattr(getattr(ctx, "guild", None), "voice_client", None)
        if isinstance(player, wavelink.Player):
            return player
        guild = getattr(ctx, "guild", None)
        for candidate in getattr(getattr(ctx, "bot", None), "voice_clients", []):
            if getattr(candidate, "guild", None) == guild and isinstance(candidate, wavelink.Player):
                return candidate
        try:
            return await channel.connect(cls=wavelink.Player, self_deaf=True)
        except discord.ClientException as exc:
            for candidate in getattr(getattr(ctx, "bot", None), "voice_clients", []):
                if getattr(candidate, "guild", None) == guild and isinstance(candidate, wavelink.Player):
                    return candidate
            raise MusicBackendUnavailable(str(exc)) from exc

    @staticmethod
    def _track_from_playable(playable: Any, query: str, requester_id: int | None) -> Track:
        return Track(
            title=str(getattr(playable, "title", query) or query),
            uri=str(getattr(playable, "uri", query) or query),
            requester_id=requester_id,
        )

    async def play(
        self,
        ctx: Any,
        session: MusicSession,
        query: str,
        requester_id: int | None,
        *,
        resolution_limit: int = 5,
    ) -> PlaybackResult:
        if self._is_spotify_url(query):
            raise TrackResolutionFailed(self._spotify_metadata_message())

        await self.ensure_node(ctx.bot)
        playables = await self.resolve_tracks(query, limit=resolution_limit)
        if not playables:
            raise TrackResolutionFailed(
                "No playable Lavalink result was found. Try a more specific song/artist search, YouTube URL, "
                "or SoundCloud URL."
            )
        player = await self.ensure_player(ctx)

        first, rest = playables[0], playables[1:]
        track = self._track_from_playable(first, query, requester_id)

        if getattr(player, "playing", False) or getattr(player, "paused", False):
            session.ensure_queue_capacity(len(playables))
            player.queue.put(first)
            session.enqueue(track)
            for fallback in rest:
                player.queue.put(fallback)
                session.enqueue(self._track_from_playable(fallback, query, requester_id))
            return PlaybackResult(track=track, started=False, backend="wavelink")

        session.ensure_queue_capacity(len(rest))
        for fallback in rest:
            player.queue.put(fallback)
            session.enqueue(self._track_from_playable(fallback, query, requester_id))
        session.current = track
        await player.play(
            first,
            volume=session.mixer.volume,
            filters=filters_for_bands(session.mixer.current_eq_payload()),
        )
        return PlaybackResult(track=track, started=True, backend="wavelink")

    @staticmethod
    def _player_for(ctx: Any) -> Any:
        return getattr(ctx, "voice_client", None) or getattr(getattr(ctx, "guild", None), "voice_client", None)

    async def apply_volume(self, ctx: Any, volume: int) -> bool:
        player = self._player_for(ctx)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.set_volume(volume)
        return True

    async def apply_eq(self, ctx: Any, session: MusicSession) -> bool:
        player = self._player_for(ctx)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.set_filters(filters_for_bands(session.mixer.current_eq_payload()))
        return True

    def filters_for_bands(self, bands: list[dict[str, float | int]]) -> Any:
        return filters_for_bands(bands)

    async def pause(self, ctx: Any, paused: bool) -> bool:
        player = self._player_for(ctx)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.pause(paused)
        return True

    async def skip(self, ctx: Any) -> bool:
        player = self._player_for(ctx)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        await player.skip(force=True)
        return True

    async def stop(self, ctx: Any) -> bool:
        player = self._player_for(ctx)
        if wavelink is None or not isinstance(player, wavelink.Player):
            return False
        player.queue.clear()
        await player.stop(force=True)
        return True
