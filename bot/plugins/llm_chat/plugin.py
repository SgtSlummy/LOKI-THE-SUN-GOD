from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.models.plugin import ToolDefinition
from bot.plugins.base import BasePlugin, PluginSlot
from bot.plugins.relay_core.formatting import safe_allowed_mentions
from bot.services.faust_agi import FaustAGIError

DISCORD_MESSAGE_LIMIT = 2000
DEFAULT_CHUNK_LIMIT = 1900
DEFAULT_MAX_RESULT_CHUNKS = 4


def _safe_int(value: Any, *, default: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(0, parsed)
    if maximum is not None:
        parsed = min(parsed, max(0, maximum))
    return parsed


def chunk_discord_text(text: str, *, limit: int = DEFAULT_CHUNK_LIMIT) -> list[str]:
    if not text:
        return [""]
    return [text[index : index + limit] for index in range(0, len(text), limit)]


def _format_council_header(result: dict[str, Any]) -> str:
    details: list[str] = []
    if result.get("run_id"):
        details.append(f"run {result['run_id']}")
    if result.get("fallback_used"):
        details.append("fallback used")
    return f"Faust AGI council ({', '.join(details)}):" if details else "Faust AGI council:"


def _format_continuation_header(result: dict[str, Any]) -> str:
    details: list[str] = []
    if result.get("run_id"):
        details.append(f"run {result['run_id']}")
    if result.get("fallback_used"):
        details.append("fallback used")
    return f"Faust AGI continuation ({', '.join(details)}):" if details else "Faust AGI continuation:"


class LLMChatCog(commands.Cog):
    agent_group = app_commands.Group(name="agent", description="Agent commands")

    def __init__(self, bot: commands.Bot, *, services: dict[str, Any], logger: logging.Logger | None = None):
        self.bot = bot
        self.services = services
        self.logger = logger or logging.getLogger("loki.llm_chat")

    @agent_group.command(name="council", description="Ask Faust AGI council for help.")
    @app_commands.describe(prompt="Question or task for the Faust AGI council")
    async def council(self, interaction: discord.Interaction, prompt: str) -> None:
        await self.handle_council(interaction, prompt=prompt)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        prompt = self._prompt_from_message(message)
        if not prompt:
            return
        await self.handle_message_council(message, prompt=prompt)

    def _prompt_from_message(self, message: discord.Message) -> str | None:
        if getattr(getattr(message, "author", None), "bot", False):
            return None
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            return None

        bot_user = getattr(self.bot, "user", None)
        bot_id = getattr(bot_user, "id", None)
        if getattr(message, "guild", None) is not None:
            if bot_id is None or bot_id not in getattr(message, "raw_mentions", []):
                return None
            mention_tokens = [f"<@{bot_id}>", f"<@!{bot_id}>"]
            for token in mention_tokens:
                content = content.replace(token, "")
            content = content.strip()
        return content or None

    async def handle_message_council(self, message: discord.Message, *, prompt: str) -> None:
        faust_client = self.services.get("faust_agi_client")
        if faust_client is None or not getattr(faust_client, "available", False):
            await message.channel.send(
                "Faust AGI is not configured. Set FAUST_AGI_BASE_URL and enable FAUST_AGI_ENABLED=true.",
                allowed_mentions=safe_allowed_mentions(),
            )
            return

        try:
            result = await faust_client.run_council(
                prompt=prompt,
                user_id=getattr(message.author, "id", None),
                guild_id=getattr(message, "guild_id", None),
                channel_id=getattr(getattr(message, "channel", None), "id", None),
            )
        except FaustAGIError as exc:
            self.logger.warning("Faust AGI council failed from message: %s", exc)
            await message.channel.send(
                "Faust AGI council failed. Check the bot logs for details.",
                allowed_mentions=safe_allowed_mentions(),
            )
            return

        await self._send_channel_result_chunks(message.channel, _format_council_header(result), result)

    async def handle_council(self, interaction: discord.Interaction, *, prompt: str) -> None:
        await interaction.response.defer(thinking=True)
        faust_client = self.services.get("faust_agi_client")
        if faust_client is None or not getattr(faust_client, "available", False):
            await interaction.followup.send(
                "Faust AGI is not configured. Set FAUST_AGI_BASE_URL and enable FAUST_AGI_ENABLED=true.",
                allowed_mentions=safe_allowed_mentions(),
            )
            return

        try:
            result = await faust_client.run_council(
                prompt=prompt,
                user_id=getattr(interaction.user, "id", None),
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
            )
        except FaustAGIError as exc:
            self.logger.warning("Faust AGI council failed: %s", exc)
            await interaction.followup.send(
                "Faust AGI council failed. Check the bot logs for details.",
                allowed_mentions=safe_allowed_mentions(),
            )
            return

        if not await self._send_result_chunks(interaction, _format_council_header(result), result):
            return
        await self._run_unprompted_continuations(interaction, faust_client, result)

    async def _send_result_chunks(self, interaction: discord.Interaction, header: str, result: dict[str, Any]) -> bool:
        text = str(result.get("text") or "Faust AGI completed without text output.")
        chunks = chunk_discord_text(f"{header}\n{text}")
        if len(chunks) > DEFAULT_MAX_RESULT_CHUNKS:
            chunks = chunks[:DEFAULT_MAX_RESULT_CHUNKS]
            chunks[-1] = chunks[-1][: DEFAULT_CHUNK_LIMIT - 36] + "\n[truncated: output too long]"
        for chunk in chunks:
            try:
                await interaction.followup.send(chunk, allowed_mentions=safe_allowed_mentions())
            except discord.HTTPException as exc:
                self.logger.warning("Could not send Faust AGI followup: %s", exc)
                return False
        return True

    async def _send_channel_result_chunks(self, channel: Any, header: str, result: dict[str, Any]) -> bool:
        text = str(result.get("text") or "Faust AGI completed without text output.")
        chunks = chunk_discord_text(f"{header}\n{text}")
        if len(chunks) > DEFAULT_MAX_RESULT_CHUNKS:
            chunks = chunks[:DEFAULT_MAX_RESULT_CHUNKS]
            chunks[-1] = chunks[-1][: DEFAULT_CHUNK_LIMIT - 36] + "\n[truncated: output too long]"
        for chunk in chunks:
            try:
                await channel.send(chunk, allowed_mentions=safe_allowed_mentions())
            except discord.HTTPException as exc:
                self.logger.warning("Could not send Faust AGI channel message: %s", exc)
                return False
        return True

    async def _run_unprompted_continuations(
        self,
        interaction: discord.Interaction,
        faust_client: Any,
        initial_result: dict[str, Any],
    ) -> None:
        settings = self.services.get("settings")
        if not getattr(settings, "faust_agi_unprompted_continuations_enabled", False):
            return
        max_turns = _safe_int(getattr(settings, "faust_agi_unprompted_max_turns", 1), maximum=5)
        if max_turns <= 0:
            return
        max_delay_seconds = _safe_int(getattr(settings, "faust_agi_unprompted_max_delay_seconds", 30), maximum=300)

        previous_result = initial_result
        parent_run_id = initial_result.get("run_id")
        for _turn in range(max_turns):
            if not previous_result.get("continue_unprompted"):
                return
            continuation_prompt = str(previous_result.get("continuation_prompt") or "").strip()
            if not continuation_prompt:
                return
            delay_seconds = _safe_int(previous_result.get("continuation_delay_seconds"), maximum=max_delay_seconds)
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
            try:
                previous_result = await faust_client.run_continuation(
                    prompt=continuation_prompt,
                    parent_run_id=parent_run_id,
                    guild_id=interaction.guild_id,
                    channel_id=interaction.channel_id,
                )
            except FaustAGIError as exc:
                self.logger.warning("Faust AGI unprompted continuation failed: %s", exc)
                return
            parent_run_id = previous_result.get("run_id") or parent_run_id
            if not await self._send_result_chunks(interaction, _format_continuation_header(previous_result), previous_result):
                return


class LLMChatPlugin(BasePlugin):
    name = "llm_chat"
    slot = PluginSlot.LLM_CHAT
    version = "0.2.0"
    enabled_by_default = False
    dependencies: list[str] = []
    config_schema = {
        "commands": ["/agent council", "mention Loki in a server channel", "DM Loki", "/ask", "/talk", "/summarize"],
        "openai_responses_api": True,
        "faust_agi": True,
    }

    def __init__(self):
        self.cog: LLMChatCog | None = None

    async def setup(self, bot: commands.Bot, services: dict[str, Any]) -> None:
        settings = services.get("settings")
        if settings is not None and not getattr(settings, "faust_agi_enabled", False):
            self.cog = None
            return
        self.cog = LLMChatCog(bot, services=services)
        await bot.add_cog(self.cog)

    async def teardown(self) -> None:
        self.cog = None

    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="discord_server_lookup",
                description="Future controlled lookup over permitted Discord server content.",
                parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value, "commands": self.commands()}

    def commands(self) -> list[str]:
        return ["/agent council", "@Loki <message>", "DM Loki <message>"]
