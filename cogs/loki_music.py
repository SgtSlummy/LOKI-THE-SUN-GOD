from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from loki_music.equalizer import bands_for_preset, preset_names
from loki_music.service import MusicSession, Track
from loki_music.wavelink_backend import MusicBackendUnavailable, VoiceChannelRequired, WavelinkBackend
from utils import db


class LokiMusic(commands.Cog):
    """Clean-room Diva-style music command surface plus LOKI mixer/EQ controls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[int, MusicSession] = {}
        self.backend = WavelinkBackend()

    def session_for(self, guild_id: int) -> MusicSession:
        session = self.sessions.setdefault(guild_id, MusicSession(guild_id=guild_id))
        self._hydrate_session_settings(session)
        return session

    def _hydrate_session_settings(self, session: MusicSession) -> None:
        row = db.sync_one("SELECT * FROM loki_music_settings WHERE guild_id=?", (session.guild_id,))
        if not row:
            return
        row_updated_at = row["updated_at"]
        if session.settings_updated_at is not None and row_updated_at == session.settings_updated_at:
            return
        session.mixer.locked = bool(row["mixer_locked"])
        try:
            session.mixer.set_volume(int(row["volume"] if row["volume"] is not None else 80))
        except (TypeError, ValueError):
            session.mixer.set_volume(80)
        try:
            session.mixer.set_preset(row["eq_preset"] or "Flat")
        except ValueError:
            session.mixer.set_preset("Flat")
        session.settings_updated_at = row_updated_at

    def _can_control_mixer(self, ctx: commands.Context, session: MusicSession) -> bool:
        if not session.mixer.locked:
            return True
        permissions = getattr(getattr(ctx.author, "guild_permissions", None), "value", 0)
        if permissions & 0x8 or permissions & 0x20:
            return True
        row = db.sync_one("SELECT dj_role_id FROM loki_music_settings WHERE guild_id=?", (session.guild_id,))
        dj_role_id = int(row["dj_role_id"] or 0) if row else 0
        if not dj_role_id:
            return False
        return any(getattr(role, "id", None) == dj_role_id for role in getattr(ctx.author, "roles", []))

    @commands.hybrid_command(name="play", description="Play a song or add it to the LOKI queue")
    @app_commands.describe(query="Song name, URL, playlist, or search query")
    async def play(self, ctx: commands.Context, *, query: str):
        if not ctx.guild:
            return await ctx.send("Use music commands inside a server.")
        session = self.session_for(ctx.guild.id)
        try:
            result = await self.backend.play(ctx, session, query, requester_id=ctx.author.id)
        except VoiceChannelRequired as exc:
            return await ctx.send(str(exc))
        except MusicBackendUnavailable:
            session.enqueue(Track(title=query, uri=query, requester_id=ctx.author.id))
            title = discord.utils.escape_markdown(query)
            return await ctx.send(f"Queued for LOKI THE SUN GOD: **{title}** (Lavalink node pending)")

        title = discord.utils.escape_markdown(result.track.title)
        action = "Now playing" if result.started else "Queued"
        await ctx.send(f"{action} for LOKI THE SUN GOD: **{title}**")

    @commands.hybrid_command(name="stop", description="Stop playback and clear the LOKI queue")
    @commands.has_permissions(manage_guild=True)
    async def stop(self, ctx: commands.Context):
        if ctx.guild:
            self.session_for(ctx.guild.id).clear()
        await self.backend.stop(ctx)
        await ctx.send("LOKI music session stopped and queue cleared.")

    @commands.hybrid_command(name="queue", description="Show the current LOKI music queue")
    async def queue(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use queue inside a server.")
        session = self.session_for(ctx.guild.id)
        current = session.current.title if session.current else "Nothing playing"
        upcoming = (
            "\n".join(f"{i + 1}. {track.title}" for i, track in enumerate(session.queue[:10]))
            or "Queue is empty."
        )
        await ctx.send(f"Now: **{current}**\n{upcoming}")

    @commands.hybrid_command(name="skip", description="Skip to the next queued LOKI track")
    async def skip(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use skip inside a server.")
        if await self.backend.skip(ctx):
            return await ctx.send("Skipped the current Lavalink track.")
        next_track = self.session_for(ctx.guild.id).dequeue_next()
        await ctx.send(f"Skipped. Now playing **{next_track.title}**." if next_track else "Skipped. Queue is empty.")

    @commands.hybrid_command(name="pause", description="Pause LOKI playback")
    async def pause(self, ctx: commands.Context):
        if await self.backend.pause(ctx, True):
            return await ctx.send("LOKI playback paused.")
        await ctx.send("Pause requested. Lavalink playback control is enabled when the music node is connected.")

    @commands.hybrid_command(name="resume", description="Resume LOKI playback")
    async def resume(self, ctx: commands.Context):
        if await self.backend.pause(ctx, False):
            return await ctx.send("LOKI playback resumed.")
        await ctx.send("Resume requested. Lavalink playback control is enabled when the music node is connected.")

    @commands.hybrid_command(name="volume", description="Set or show the LOKI mixer output volume")
    @app_commands.describe(level="Volume from 0 to 150")
    async def volume(self, ctx: commands.Context, level: int | None = None):
        if not ctx.guild:
            return await ctx.send("Use volume inside a server.")
        mixer = self.session_for(ctx.guild.id).mixer
        if level is not None:
            if not self._can_control_mixer(ctx, self.session_for(ctx.guild.id)):
                return await ctx.send("LOKI mixer is locked to DJ/admin roles.")
            try:
                mixer.set_volume(level)
            except ValueError as exc:
                return await ctx.send(str(exc))
            await self.backend.apply_volume(ctx, mixer.volume)
        await ctx.send(f"LOKI mixer volume: **{mixer.volume}%**")

    @commands.hybrid_command(name="lyrics", description="Show lyrics lookup status for the current track")
    async def lyrics(self, ctx: commands.Context):
        await ctx.send("Lyrics lookup is queued for the external content provider adapter.")

    @commands.hybrid_command(name="grab", description="Save the current LOKI track link when available")
    async def grab(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use grab inside a server.")
        current = self.session_for(ctx.guild.id).current
        await ctx.send(current.uri if current and current.uri else "No current track link is available.")

    @commands.hybrid_command(name="loop", description="Set LOKI queue loop mode")
    @app_commands.describe(mode="off, track, or queue")
    async def loop(self, ctx: commands.Context, mode: str = "off"):
        if not ctx.guild:
            return await ctx.send("Use loop inside a server.")
        normalized = mode.lower()
        if normalized not in {"off", "track", "queue"}:
            return await ctx.send("Loop mode must be off, track, or queue.")
        self.session_for(ctx.guild.id).loop_mode = normalized
        await ctx.send(f"LOKI loop mode: **{normalized}**")

    @commands.hybrid_command(name="shuffle", description="Shuffle the LOKI queue")
    async def shuffle(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use shuffle inside a server.")
        import random

        random.shuffle(self.session_for(ctx.guild.id).queue)
        await ctx.send("LOKI queue shuffled.")

    @commands.hybrid_command(name="nowplaying", description="Show the current LOKI track")
    async def nowplaying(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use nowplaying inside a server.")
        current = self.session_for(ctx.guild.id).current
        await ctx.send(f"Now playing: **{current.title}**" if current else "Nothing is playing.")

    @commands.hybrid_command(name="webplayer", description="Open the LOKI music panel")
    async def webplayer(self, ctx: commands.Context):
        await ctx.send("Open the LOKI web portal mixer from the dashboard navigation.")

    @commands.hybrid_command(name="eq", description="Apply a LOKI equalizer preset")
    @app_commands.describe(preset="Flat, Bass Boost, Vocal Clarity, Night Mode, Podcast, Treble, or Custom")
    async def eq(self, ctx: commands.Context, preset: str = "Flat"):
        if not ctx.guild:
            return await ctx.send("Use eq inside a server.")
        try:
            bands_for_preset(preset)
        except ValueError:
            return await ctx.send("Available EQ presets: " + ", ".join(preset_names()))
        session = self.session_for(ctx.guild.id)
        if not self._can_control_mixer(ctx, session):
            return await ctx.send("LOKI mixer is locked to DJ/admin roles.")
        session.mixer.set_preset(preset)
        await self.backend.apply_eq(ctx, session)
        await ctx.send(f"LOKI EQ preset applied: **{preset}**")

    @commands.hybrid_command(name="mixer", description="Show the LOKI mixer state")
    async def mixer(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use mixer inside a server.")
        mixer = self.session_for(ctx.guild.id).mixer
        await ctx.send(f"LOKI mixer: volume **{mixer.volume}%**, EQ **{mixer.eq_preset}**.")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        player = getattr(payload, "player", None)
        guild = getattr(player, "guild", None)
        if player is None or guild is None:
            return
        session = self.session_for(guild.id)
        if session.loop_mode == "track" and getattr(payload, "track", None) is not None:
            await player.play(
                payload.track,
                volume=session.mixer.volume,
                filters=self.backend.filters_for_bands(session.mixer.current_eq_payload()),
            )
            return
        if session.loop_mode == "queue" and session.current is not None:
            session.enqueue(session.current)
        if getattr(player, "queue", None) is None or player.queue.is_empty:
            session.current = None
            return
        playable = player.queue.get()
        next_track = session.dequeue_next()
        if next_track is None:
            next_track = Track(
                title=str(getattr(playable, "title", "Unknown track") or "Unknown track"),
                uri=str(getattr(playable, "uri", "") or ""),
            )
            session.current = next_track
        await player.play(
            playable,
            volume=session.mixer.volume,
            filters=self.backend.filters_for_bands(session.mixer.current_eq_payload()),
        )


async def setup(bot):
    await bot.add_cog(LokiMusic(bot))
