from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicDivaCommand:
    name: str
    purpose: str
    extension: str = "Diva-public-parity"


def core_public_commands() -> list[PublicDivaCommand]:
    """Clean-room public command target based on public Diva docs/search snippets."""

    return [
        PublicDivaCommand("play", "Play a song or add it to the queue."),
        PublicDivaCommand("stop", "Stop playback and clear/leave the active session."),
        PublicDivaCommand("queue", "Show the current music queue."),
        PublicDivaCommand("skip", "Skip or vote-skip the current track."),
        PublicDivaCommand("pause", "Pause current playback."),
        PublicDivaCommand("resume", "Resume paused playback."),
        PublicDivaCommand("volume", "Show or set playback volume."),
        PublicDivaCommand("lyrics", "Show lyrics for the current or requested song."),
        PublicDivaCommand("grab", "Save or DM the current track link when available."),
        PublicDivaCommand("loop", "Set queue loop mode."),
        PublicDivaCommand("shuffle", "Shuffle the queue."),
        PublicDivaCommand("nowplaying", "Show the current track."),
        PublicDivaCommand("webplayer", "Open the music panel or web player."),
        PublicDivaCommand("songrequest", "Configure or show the song request channel."),
        PublicDivaCommand("eq", "Apply a LOKI equalizer preset without exposing arbitrary filters.", "LOKI"),
        PublicDivaCommand("mixer", "Open the LOKI mixer interface.", "LOKI"),
    ]
