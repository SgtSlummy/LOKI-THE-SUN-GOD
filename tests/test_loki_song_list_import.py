from __future__ import annotations

import asyncio
from types import SimpleNamespace

from loki_music.service import MusicSession
from loki_music.song_list import SongListImportError, parse_song_list


class FakeBackend:
    def __init__(self):
        self.queries: list[str] = []
        self.kwargs: list[dict] = []

    async def play(self, _ctx, _session, query: str, requester_id: int | None, **_kwargs):
        from loki_music.wavelink_backend import MusicBackendUnavailable

        self.queries.append(query)
        self.kwargs.append(_kwargs)
        raise MusicBackendUnavailable


class FakeCtx:
    def __init__(self):
        self.guild = SimpleNamespace(id=123)
        self.author = SimpleNamespace(id=42)
        self.channel = object()
        self.sent: list[tuple[str, dict]] = []

    async def send(self, content: str, **kwargs):
        self.sent.append((content, kwargs))


class FakeCog:
    def __init__(self, session: MusicSession, backend: FakeBackend):
        self._session = session
        self.backend = backend
        self.updates: list[str] = []

    def session_for(self, _guild_id: int) -> MusicSession:
        return self._session

    async def _update_jukebox(self, *_args, **kwargs):
        self.updates.append(kwargs.get("reason", ""))


def test_parse_song_list_accepts_pasted_diva_style_numbered_markdown_and_urls():
    payload = """
    1. [Blinding Lights - The Weeknd](https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b?si=abc)
    2) Kendrick Lamar - HUMBLE.
    - https://youtu.be/dQw4w9WgXcQ
    • SoundCloud Artist - Basement Set
    """

    entries = parse_song_list(payload)

    assert [entry.query for entry in entries] == [
        "Blinding Lights - The Weeknd",
        "Kendrick Lamar - HUMBLE.",
        "https://youtu.be/dQw4w9WgXcQ",
        "SoundCloud Artist - Basement Set",
    ]
    assert entries[0].source_url == "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
    assert entries[0].provider == "spotify"


def test_parse_song_list_rejects_spotify_playlist_expansion_without_claiming_streaming():
    payload = "https://open.spotify.com/playlist/abc123?si=example"

    try:
        parse_song_list(payload)
    except SongListImportError as exc:
        assert "Spotify playlist expansion" in str(exc)
    else:
        raise AssertionError("Spotify playlist URLs must not be silently imported as playable tracks")


def test_parse_song_list_dedupes_preserving_case_sensitive_urls():
    payload = """
    https://youtu.be/CaseSensitiveID
    https://youtu.be/casesensitiveid
    https://youtu.be/CaseSensitiveID
    """

    entries = parse_song_list(payload)

    assert [entry.query for entry in entries] == [
        "https://youtu.be/CaseSensitiveID",
        "https://youtu.be/casesensitiveid",
    ]


def test_parse_song_list_preserves_youtube_watch_query_while_stripping_spotify_tracking():
    payload = """
    https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc
    [Track - Artist](https://open.spotify.com/track/abc123?si=tracking)
    """

    entries = parse_song_list(payload)

    assert entries[0].query == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc"
    assert entries[0].source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc"
    assert entries[1].source_url == "https://open.spotify.com/track/abc123"


def test_import_song_list_fallback_queues_each_pasted_track_without_phantom_spotify_streaming():
    from cogs.loki_music import LokiMusic

    session = MusicSession(guild_id=123, max_queue_size=10)
    backend = FakeBackend()
    cog = FakeCog(session=session, backend=backend)
    ctx = FakeCtx()
    payload = """
    [Blinding Lights - The Weeknd](https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b?si=abc)
    Kendrick Lamar - HUMBLE.
    """

    asyncio.run(LokiMusic._import_song_list(cog, ctx, payload))

    content, kwargs = ctx.sent[-1]
    assert "Imported 2 song(s)" in content
    assert "Spotify metadata converted to search text" in content
    assert backend.queries == ["Blinding Lights - The Weeknd", "Kendrick Lamar - HUMBLE."]
    assert backend.kwargs == [{"resolution_limit": 1}, {"resolution_limit": 1}]
    assert [track.title for track in session.queue] == ["Blinding Lights - The Weeknd", "Kendrick Lamar - HUMBLE."]
    assert session.queue[0].provider == "spotify"
    assert session.queue[0].uri == "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
    assert kwargs["allowed_mentions"].everyone is False
    assert cog.updates == ["song list import"]


def test_import_song_list_checks_queue_capacity_before_mutating():
    from cogs.loki_music import LokiMusic

    session = MusicSession(guild_id=123, max_queue_size=1)
    session.enqueue(SimpleNamespace(title="existing"))
    backend = FakeBackend()
    cog = FakeCog(session=session, backend=backend)
    ctx = FakeCtx()

    asyncio.run(LokiMusic._import_song_list(cog, ctx, "one\ntwo"))

    content, _kwargs = ctx.sent[-1]
    assert "Music queue is limited" in content
    assert len(session.queue) == 1
    assert backend.queries == []
