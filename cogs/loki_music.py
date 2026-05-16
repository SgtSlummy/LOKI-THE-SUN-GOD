from __future__ import annotations

import os
from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands

from loki_music.equalizer import bands_for_preset, preset_names
from loki_music.service import MusicSession, QueueLimitExceeded, Track
from loki_music.song_list import SongListImportError, parse_song_list
from loki_music.wavelink_backend import (
    MusicBackendUnavailable,
    TrackResolutionFailed,
    VoiceChannelRequired,
    WavelinkBackend,
)
from utils import db


class JukeboxControls(discord.ui.View):
    """Persistent-ish controls for the public LOKI jukebox panel."""

    def __init__(self, cog: "LokiMusic"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Play", style=discord.ButtonStyle.success, custom_id="loki:juke:play")
    async def play_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.guild is None:
            return await interaction.response.send_message("Use LOKI music controls inside a server.", ephemeral=True)
        ctx = self.cog._context_from_interaction(interaction)
        if await self.cog.backend.pause(ctx, False):
            await self.cog._update_jukebox(interaction.guild, reason="play button")
            return await interaction.response.send_message("LOKI playback resumed.", ephemeral=True)
        return await interaction.response.send_message(
            "Nothing is paused yet. Use `/play` or ask LOKI to play a song.",
            ephemeral=True,
        )

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="loki:juke:stop")
    async def stop_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.guild is None:
            return await interaction.response.send_message("Use LOKI music controls inside a server.", ephemeral=True)
        session = self.cog.session_for(interaction.guild.id)
        session.clear()
        await self.cog.backend.stop(self.cog._context_from_interaction(interaction))
        await self.cog._update_jukebox(interaction.guild, reason="stop button")
        await interaction.response.send_message("LOKI music stopped and queue cleared.", ephemeral=True)


class LokiMusic(commands.Cog):
    """Clean-room Diva-style music command surface plus LOKI mixer/EQ controls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[int, MusicSession] = {}
        self.backend = WavelinkBackend()
        self.jukebox_messages: dict[int, discord.Message] = {}
        self.bot.add_view(JukeboxControls(self))

    def _configured_jukebox_channel_id(self) -> int | None:
        raw = (os.getenv("LOKI_JUKEBOX_CHANNEL_ID") or os.getenv("JUKEBOX_CHANNEL_ID") or "").strip()
        return int(raw) if raw.isdigit() else None

    def _configured_jukebox_message_id(self) -> int | None:
        raw = (os.getenv("LOKI_JUKEBOX_MESSAGE_ID") or "").strip()
        return int(raw) if raw.isdigit() else None

    def _context_from_interaction(self, interaction: discord.Interaction) -> SimpleNamespace:
        return SimpleNamespace(
            bot=self.bot,
            guild=interaction.guild,
            author=interaction.user,
            voice_client=getattr(interaction.guild, "voice_client", None) if interaction.guild else None,
        )

    def jukebox_embed_for(self, session: MusicSession) -> discord.Embed:
        embed = discord.Embed(
            title="LOKI Jukebox",
            description="Use `/play`, talk to LOKI, or press the controls below.",
            color=discord.Color.gold(),
        )
        current = session.current.title if session.current else "Nothing playing"
        embed.add_field(name="Now playing", value=current[:1024], inline=False)
        upcoming = (
            "\n".join(f"{i + 1}. {track.title}" for i, track in enumerate(session.queue[:10]))
            or "Queue is empty."
        )
        embed.add_field(name="Song list", value=upcoming[:1024], inline=False)
        embed.set_footer(
            text=f"Volume {session.mixer.volume}% • EQ {session.mixer.eq_preset} • Loop {session.loop_mode}"
        )
        return embed

    async def _jukebox_channel_for(self, guild: discord.Guild, fallback: discord.abc.Messageable | None = None):
        channel_id = self._configured_jukebox_channel_id()
        if channel_id:
            channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                    channel = None
            if channel is not None and hasattr(channel, "send"):
                return channel
        return fallback if fallback is not None else getattr(guild, "system_channel", None)

    async def _update_jukebox(
        self,
        guild: discord.Guild,
        *,
        fallback_channel: discord.abc.Messageable | None = None,
        reason: str = "music update",
    ) -> discord.Message | None:
        channel = await self._jukebox_channel_for(guild, fallback_channel)
        if channel is None:
            return None
        session = self.session_for(guild.id)
        embed = self.jukebox_embed_for(session)
        view = JukeboxControls(self)
        existing = self.jukebox_messages.get(guild.id)
        if existing is None and self._configured_jukebox_message_id() is not None:
            try:
                fetched = await channel.fetch_message(self._configured_jukebox_message_id())
            except (discord.HTTPException, discord.NotFound, discord.Forbidden, AttributeError):
                fetched = None
            if fetched is not None:
                existing = fetched
                self.jukebox_messages[guild.id] = fetched
        if existing is not None:
            try:
                await existing.edit(embed=embed, view=view)
                return existing
            except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                self.jukebox_messages.pop(guild.id, None)
        try:
            message = await channel.send(embed=embed, view=view)
        except (discord.HTTPException, discord.Forbidden):
            return None
        self.jukebox_messages[guild.id] = message
        return message

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

    async def _import_song_list(self, ctx: commands.Context, payload: str) -> None:
        if not ctx.guild:
            return await ctx.send(
                "Use song-list imports inside a server.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        defer = getattr(ctx, "defer", None)
        if callable(defer):
            try:
                await defer(ephemeral=True)
            except (discord.HTTPException, RuntimeError, AttributeError):
                pass
        try:
            entries = parse_song_list(payload)
        except SongListImportError as exc:
            return await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())

        session = self.session_for(ctx.guild.id)
        try:
            session.ensure_queue_capacity(len(entries))
        except QueueLimitExceeded as exc:
            return await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())

        imported = 0
        metadata_converted = 0
        skipped = 0
        for entry in entries:
            try:
                await self.backend.play(ctx, session, entry.query, requester_id=ctx.author.id, resolution_limit=1)
                imported += 1
                if entry.used_spotify_metadata:
                    metadata_converted += 1
                continue
            except (MusicBackendUnavailable, VoiceChannelRequired):
                pass
            except (TrackResolutionFailed, QueueLimitExceeded):
                skipped += 1
                continue
            try:
                session.enqueue(
                    Track(
                        title=entry.query,
                        uri=entry.source_url or entry.query,
                        requester_id=ctx.author.id,
                        provider=entry.provider,
                        provider_id=entry.source_url or entry.query,
                    )
                )
            except QueueLimitExceeded as exc:
                return await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())
            imported += 1
            if entry.used_spotify_metadata:
                metadata_converted += 1

        await self._update_jukebox(ctx.guild, fallback_channel=ctx.channel, reason="song list import")
        detail = f"Imported {imported} song(s) into the LOKI queue."
        if metadata_converted:
            detail += f" Spotify metadata converted to search text for {metadata_converted} item(s)."
        if skipped:
            detail += f" Skipped {skipped} unplayable item(s)."
        await ctx.send(detail, view=JukeboxControls(self), allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="songlist", description="Paste a Diva-style song list into the LOKI queue")
    @app_commands.describe(
        payload="One song per line: titles, markdown links, Spotify track labels, YouTube, or SoundCloud"
    )
    async def songlist(self, ctx: commands.Context, *, payload: str):
        await self._import_song_list(ctx, payload)

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
        except TrackResolutionFailed as exc:
            return await ctx.send(str(exc))
        except QueueLimitExceeded as exc:
            return await ctx.send(str(exc))
        except MusicBackendUnavailable:
            try:
                session.enqueue(Track(title=query, uri=query, requester_id=ctx.author.id))
            except QueueLimitExceeded as exc:
                return await ctx.send(str(exc))
            await self._update_jukebox(ctx.guild, fallback_channel=ctx.channel, reason="backend unavailable")
            title = discord.utils.escape_markdown(query)
            return await ctx.send(
                f"Queued for LOKI THE SUN GOD: **{title}** (Lavalink node pending)",
                view=JukeboxControls(self),
            )

        title = discord.utils.escape_markdown(result.track.title)
        action = "Now playing" if result.started else "Queued"
        await self._update_jukebox(ctx.guild, fallback_channel=ctx.channel, reason="play command")
        await ctx.send(f"{action} for LOKI THE SUN GOD: **{title}**", view=JukeboxControls(self))

    @commands.hybrid_command(name="stop", description="Stop playback and clear the LOKI queue")
    @commands.has_permissions(manage_guild=True)
    async def stop(self, ctx: commands.Context):
        if ctx.guild:
            self.session_for(ctx.guild.id).clear()
        await self.backend.stop(ctx)
        if ctx.guild:
            await self._update_jukebox(ctx.guild, fallback_channel=ctx.channel, reason="stop command")
        await ctx.send("LOKI music session stopped and queue cleared.", view=JukeboxControls(self))

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
        await self._update_jukebox(ctx.guild, fallback_channel=ctx.channel, reason="queue command")
        await ctx.send(f"Now: **{current}**\n{upcoming}", view=JukeboxControls(self))

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
        await self._play_next_after_current(payload)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload):
        await self._play_next_after_current(payload)

    async def _play_next_after_current(self, payload):
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
        loop_current = session.current if session.loop_mode == "queue" else None
        if getattr(player, "queue", None) is None or player.queue.is_empty:
            session.current = None
            await self._update_jukebox(guild, reason="track end")
            return
        playable = player.queue.get()
        next_track = session.dequeue_next()
        if loop_current is not None:
            session.enqueue(loop_current)
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
        await self._update_jukebox(guild, reason="track advance")


async def setup(bot):
    await bot.add_cog(LokiMusic(bot))
