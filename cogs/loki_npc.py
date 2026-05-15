from __future__ import annotations

import json
import logging
import os
import re
import time
from types import SimpleNamespace

import discord
from discord.ext import commands

from loki_engine.natural_language import NaturalLanguageRights, route_natural_language_request
from loki_engine.permissions import PermissionContext, assert_admin_action
from loki_music.service import QueueLimitExceeded, Track
from loki_music.wavelink_backend import MusicBackendUnavailable, VoiceChannelRequired
from loki_npc.memory import (
    delete_user_memory_with_receipt,
    export_user_memory,
    member_memory_snapshot,
    public_memory_allowed,
    recent_public_memory,
    remember_public_message,
)
from loki_npc.openai_responses import ask_npc
from loki_npc.persona import persona_from_settings
from utils import db

log = logging.getLogger("loki.npc")


class LokiNpc(commands.Cog):
    """Public NPC responder with admin-only settings changes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns: dict[tuple[int, int], float] = {}

    def enabled(self) -> bool:
        return os.getenv("LOKI_NPC_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not self.enabled_for_guild(message.guild.id):
            return
        if not self._channel_allowed(message.channel, guild_id=message.guild.id):
            return
        author_opted_out = str(message.author.id) in self._csv_set("LOKI_NPC_MEMORY_OPT_OUT_USER_IDS")
        is_private_channel = self._is_private_channel(message.channel, message.guild)
        if public_memory_allowed(
            is_private_channel=is_private_channel,
            author_opted_out=author_opted_out,
            deleted=False,
        ):
            remember_public_message(
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                user_id=message.author.id,
                content=message.clean_content,
            )
        if not self._is_addressed_to_loki(message):
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self.cooldowns.get(key, 0) < 20:
            return
        self.cooldowns[key] = now
        persona = self.persona_for_guild(message.guild.id)
        prompt = self._prompt_without_address(message)
        music_query = self._music_query_from_prompt(prompt)
        if music_query:
            await self._handle_music_prompt(message, music_query)
            return
        route = self._route_natural_language_prompt(prompt, message)
        if not route.allowed:
            await message.reply(route.reason, mention_author=False)
            return
        try:
            answer = await ask_npc(
                prompt=prompt,
                persona=persona.prompt_text(),
                memory_context=recent_public_memory(message.guild.id),
            )
        except Exception:
            log.exception("LOKI NPC provider failed")
            answer = "NPC brain is not available yet. An operator can check the bot logs."
        await message.reply(answer[:1900], mention_author=False)

    def _route_natural_language_prompt(self, prompt: str, message: discord.Message):
        permissions = getattr(getattr(message.author, "guild_permissions", None), "value", 0)
        context = PermissionContext(
            user_id=message.author.id,
            guild_id=message.guild.id if message.guild else None,
            permissions=permissions,
        )
        return route_natural_language_request(prompt, context, rights=NaturalLanguageRights())

    def _is_addressed_to_loki(self, message: discord.Message) -> bool:
        if self.bot.user in getattr(message, "mentions", []):
            return True
        content = (getattr(message, "clean_content", "") or "").strip().lower()
        return bool(re.match(r"^(hey|hi|yo|ok|okay)?\s*loki\b", content))

    def _prompt_without_address(self, message: discord.Message) -> str:
        content = (getattr(message, "clean_content", "") or "").strip()
        bot_user = self.bot.user
        for name in {getattr(bot_user, "display_name", ""), getattr(bot_user, "name", "")}:
            if name:
                content = content.replace(f"@{name}", "")
        return re.sub(r"^(hey|hi|yo|ok|okay)?\s*loki\b[\s,;:!?.-]*", "", content, flags=re.IGNORECASE).strip()

    @staticmethod
    def _music_query_from_prompt(prompt: str) -> str | None:
        normalized = (prompt or "").strip()
        match = re.match(
            r"^(?:please\s+)?(?:play|queue|put\s+on|start)(?:\s+some|\s+the)?\s+(?:music\s+)?(.+)$",
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        query = match.group(1).strip(" \t\r\n'\".,!?")
        if not query or query.lower() in {"music", "song", "track", "something"}:
            return None
        return query

    async def _handle_music_prompt(self, message: discord.Message, query: str) -> None:
        music = self.bot.get_cog("LokiMusic")
        if music is None:
            await message.reply("LOKI music is not loaded yet.", mention_author=False)
            return
        session = music.session_for(message.guild.id)
        ctx = SimpleNamespace(
            bot=self.bot,
            guild=message.guild,
            author=message.author,
            voice_client=getattr(message.guild, "voice_client", None),
        )
        try:
            result = await music.backend.play(ctx, session, query, requester_id=message.author.id)
        except VoiceChannelRequired as exc:
            await message.reply(str(exc), mention_author=False)
            return
        except QueueLimitExceeded as exc:
            await message.reply(str(exc), mention_author=False)
            return
        except MusicBackendUnavailable:
            try:
                session.enqueue(Track(title=query, uri=query, requester_id=message.author.id))
            except QueueLimitExceeded as exc:
                await message.reply(str(exc), mention_author=False)
                return
            await music._update_jukebox(
                message.guild,
                fallback_channel=message.channel,
                reason="natural music fallback",
            )
            title = discord.utils.escape_markdown(query)
            await message.reply(
                f"Queued for LOKI THE SUN GOD: **{title}** (Lavalink node pending)",
                mention_author=False,
            )
            return

        await music._update_jukebox(
            message.guild,
            fallback_channel=message.channel,
            reason="natural music request",
        )
        action = "Now playing" if result.started else "Queued"
        await message.reply(
            f"{action} for LOKI THE SUN GOD: **{discord.utils.escape_markdown(result.track.title)}**",
            mention_author=False,
        )

    def _channel_allowed(self, channel: discord.abc.Messageable, *, guild_id: int | None = None) -> bool:
        allowed = self.allowed_channel_ids_for_guild(guild_id)
        if not allowed:
            return True
        channel_ids = self._channel_scope_ids(channel)
        return bool(channel_ids & allowed)

    @staticmethod
    def _is_private_channel(channel: discord.abc.Messageable, guild: discord.Guild) -> bool:
        target = channel.parent if isinstance(channel, discord.Thread) and channel.parent is not None else channel
        if not hasattr(target, "permissions_for"):
            return True
        permissions = target.permissions_for(guild.default_role)
        return not bool(getattr(permissions, "view_channel", False))

    @classmethod
    def _channel_scope_ids(cls, channel: discord.abc.Messageable) -> set[str]:
        ids: set[str] = set()
        for value in (
            getattr(channel, "id", None),
            getattr(channel, "parent_id", None),
            getattr(channel, "category_id", None),
        ):
            if value:
                ids.add(str(value))
        parent = getattr(channel, "parent", None) or getattr(channel, "category", None)
        parent_id = getattr(parent, "id", None)
        if parent_id:
            ids.add(str(parent_id))
        return ids

    @staticmethod
    def _csv_set(name: str) -> set[str]:
        return {part.strip() for part in (os.getenv(name) or "").split(",") if part.strip()}

    @classmethod
    def _parse_channel_allowlist(cls, value: str | None) -> set[str]:
        return {part.strip() for part in (value or "").split(",") if part.strip()}

    @staticmethod
    def _settings_for_guild(guild_id: int | None):
        if guild_id is None:
            return None
        return db.sync_one("SELECT * FROM loki_npc_settings WHERE guild_id=?", (guild_id,))

    def enabled_for_guild(self, guild_id: int | None) -> bool:
        row = self._settings_for_guild(guild_id)
        if row is not None:
            return bool(row["enabled"])
        return self.enabled()

    def allowed_channel_ids_for_guild(self, guild_id: int | None) -> set[str]:
        row = self._settings_for_guild(guild_id)
        if row is not None:
            return self._parse_channel_allowlist(row["channel_allowlist"])
        return self._csv_set("LOKI_NPC_ALLOWED_CHANNEL_IDS")

    @staticmethod
    def persona_for_guild(guild_id: int):
        row = db.sync_one("SELECT persona_json FROM loki_npc_settings WHERE guild_id=?", (guild_id,))
        return persona_from_settings(guild_id, row["persona_json"] if row else "")

    @commands.hybrid_group(name="npc", description="Manage the LOKI NPC")
    async def npc(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use a subcommand: status, reset, or personality.")

    @npc.command(name="status", description="Show LOKI NPC status")
    async def npc_status(self, ctx: commands.Context):
        state = "enabled" if self.enabled_for_guild(ctx.guild.id if ctx.guild else None) else "disabled"
        await ctx.send(f"LOKI NPC is **{state}**. Public replies require mentioning the bot.")

    @npc.command(name="reset", description="Reset LOKI NPC personality for this server")
    @commands.has_permissions(manage_guild=True)
    async def npc_reset(self, ctx: commands.Context):
        permissions = getattr(ctx.author.guild_permissions, "value", 0)
        decision = assert_admin_action(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            ),
            "reset_npc_personality",
        )
        if not decision.allowed:
            return await ctx.send(decision.reason)
        if not ctx.guild:
            return await ctx.send("Use this inside a server.")
        existing = self._settings_for_guild(ctx.guild.id)
        if existing is not None:
            db.sync_exec(
                """
                UPDATE loki_npc_settings
                SET persona_json=?, updated_at=?
                WHERE guild_id=?
                """,
                ("", int(time.time()), ctx.guild.id),
            )
        await ctx.send("LOKI NPC personality reset to the generated default for this server.")

    @npc.command(name="personality", description="Show the generated LOKI NPC personality")
    async def npc_personality(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Use this inside a server.")
        await ctx.send(self.persona_for_guild(ctx.guild.id).prompt_text())

    @staticmethod
    def _admin_decision(ctx: commands.Context, action: str):
        permissions = getattr(getattr(ctx.author, "guild_permissions", None), "value", 0)
        return assert_admin_action(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            ),
            action,
        )

    @staticmethod
    def _require_private_interaction(ctx: commands.Context) -> bool:
        return getattr(ctx, "interaction", None) is not None

    @npc.command(name="memory", description="Show redacted public memory for yourself or a managed member")
    async def npc_memory(self, ctx: commands.Context, member: discord.Member = None):
        if not ctx.guild:
            return await ctx.send("Use this inside a server.")
        if not self._require_private_interaction(ctx):
            return await ctx.send("Use /npc memory so LOKI can return this memory snapshot privately.")
        target = member or ctx.author
        if target.id != ctx.author.id:
            decision = self._admin_decision(ctx, "view_member_public_memory")
            if not decision.allowed:
                return await ctx.send(
                    "You can view your own memory. Viewing another member requires Manage Server.",
                    ephemeral=True,
                )
        snapshot = member_memory_snapshot(guild_id=ctx.guild.id, user_id=target.id, limit=5)
        await ctx.send(
            self._format_member_memory_snapshot(target, snapshot),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    @staticmethod
    def _memory_export_body_for_discord(payload: dict[str, object], *, max_chars: int = 1500) -> str:
        body = json.dumps(payload | {"truncated": False}, indent=2, sort_keys=True)
        if len(body) <= max_chars:
            return body
        preview = dict(payload)
        entries = list(payload.get("entries", []))
        preview["entries"] = []
        preview["truncated"] = True
        preview["export_note"] = (
            "Preview reduced to keep the Discord response valid JSON. "
            "Use DB/MCP export for all rows."
        )
        for entry in entries:
            candidate = dict(preview)
            candidate["entries"] = [*preview["entries"], entry]
            candidate_body = json.dumps(candidate, indent=2, sort_keys=True)
            if len(candidate_body) > max_chars:
                break
            preview = candidate
        return json.dumps(preview, indent=2, sort_keys=True)

    @npc.command(name="memory-export", description="Export redacted public memory for a managed member")
    @commands.has_permissions(manage_guild=True)
    async def npc_memory_export(self, ctx: commands.Context, member: discord.Member):
        if not ctx.guild:
            return await ctx.send("Use this inside a server.")
        if not self._require_private_interaction(ctx):
            return await ctx.send("Use /npc memory-export so LOKI can return this export privately.")
        decision = self._admin_decision(ctx, "export_member_public_memory")
        if not decision.allowed:
            return await ctx.send(decision.reason, ephemeral=True)
        payload = export_user_memory(guild_id=ctx.guild.id, user_id=member.id, actor_id=ctx.author.id, limit=20)
        raw_name = getattr(member, "display_name", None) or getattr(member, "name", "member")
        display_name = discord.utils.escape_markdown(raw_name)
        body = self._memory_export_body_for_discord(payload)
        await ctx.send(
            f"LOKI public memory export for **{display_name}**\n```json\n{body}\n```",
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    @npc.command(name="memory-delete", description="Delete stored public memory for a managed member")
    @commands.has_permissions(manage_guild=True)
    async def npc_memory_delete(self, ctx: commands.Context, member: discord.Member):
        if not ctx.guild:
            return await ctx.send("Use this inside a server.")
        if not self._require_private_interaction(ctx):
            return await ctx.send("Use /npc memory-delete so LOKI can return this receipt privately.")
        decision = self._admin_decision(ctx, "delete_member_public_memory")
        if not decision.allowed:
            return await ctx.send(decision.reason, ephemeral=True)
        deleted = delete_user_memory_with_receipt(guild_id=ctx.guild.id, user_id=member.id, actor_id=ctx.author.id)
        raw_name = getattr(member, "display_name", None) or getattr(member, "name", "member")
        display_name = discord.utils.escape_markdown(raw_name)
        await ctx.send(
            f"Deleted {deleted} public memory snippet(s) for **{display_name}**. Audit receipt recorded.",
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    @staticmethod
    def _format_member_memory_snapshot(member: discord.abc.User, snapshot: dict[str, object]) -> str:
        raw_name = getattr(member, "display_name", None) or getattr(member, "name", "member")
        display_name = discord.utils.escape_markdown(raw_name)
        count = int(snapshot.get("entry_count") or 0)
        noun = "snippet" if count == 1 else "snippets"
        lines = [
            f"LOKI public memory for **{display_name}**",
            f"{count} public memory {noun} stored from non-private channels.",
        ]
        recent = [str(item) for item in snapshot.get("recent", [])]
        if not recent:
            lines.append("No recent public memory snippets are stored for this member.")
            return "\n".join(lines)
        lines.append("Recent redacted snippets:")
        for index, snippet in enumerate(recent[:5], start=1):
            safe = discord.utils.escape_mentions(discord.utils.escape_markdown(snippet))
            lines.append(f"{index}. {safe[:280]}")
        return "\n".join(lines)


async def setup(bot):
    await bot.add_cog(LokiNpc(bot))
