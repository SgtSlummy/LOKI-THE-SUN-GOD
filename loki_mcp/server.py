from __future__ import annotations

import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from loki_mcp.models import (
    ActivityStateResult,
    ChannelClusterResult,
    CommandSearchQuery,
    CommandSearchResult,
    DiagnosticsResult,
    DocSearchQuery,
    DocSearchResult,
    EmptyArgs,
    GuildConfigResult,
    GuildConfigWriteInput,
    GuildListResult,
    GuildQuery,
    LegacyLibrarySearchQuery,
    LegacyLibrarySearchResult,
    MusicStateResult,
    MutationResult,
    MythosSummaryResult,
    NpcSummaryResult,
    OllamaStatusResult,
    StickyDeleteInput,
)
from utils import operator_surface

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("loki_mcp")


def _json_text(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def writes_enabled() -> bool:
    return os.getenv("LOKI_MCP_ENABLE_WRITES", "").strip().lower() in {"1", "true", "yes", "on"}


def create_server() -> FastMCP:
    mcp = FastMCP("loki_mcp")

    @mcp.resource(
        "loki://overview",
        name="LOKI THE SUN GOD Overview",
        description="Compact local overview of LOKI THE SUN GOD's operator state.",
        mime_type="application/json",
    )
    def overview_resource() -> str:
        return _json_text(operator_surface.overview_snapshot())

    @mcp.resource(
        "loki://diagnostics",
        name="LOKI THE SUN GOD Diagnostics",
        description="Local diagnostics for the LOKI THE SUN GOD workspace.",
        mime_type="application/json",
    )
    def diagnostics_resource() -> str:
        return _json_text(operator_surface.diagnostics_snapshot())

    @mcp.resource(
        "loki://commands",
        name="LOKI THE SUN GOD Commands",
        description="Full command catalog discovered from LOKI THE SUN GOD's local cogs.",
        mime_type="application/json",
    )
    def commands_resource() -> str:
        return _json_text({"commands": operator_surface.command_library()})

    @mcp.resource(
        "loki://options",
        name="LOKI THE SUN GOD Options",
        description="Human-readable option library for LOKI THE SUN GOD's configurable settings.",
        mime_type="application/json",
    )
    def options_resource() -> str:
        return _json_text(operator_surface.option_library())

    @mcp.resource(
        "loki://ai-docs",
        name="LOKI THE SUN GOD AI Docs",
        description="Local operator and AI documentation library.",
        mime_type="application/json",
    )
    def ai_docs_resource() -> str:
        return _json_text({"docs": operator_surface.ai_doc_library(include_content=False)})

    @mcp.resource(
        "loki://external-legacy-libraries",
        name="LOKI THE SUN GOD External Legacy Libraries",
        description="Read-only extracted legacy libraries available to LOKI without being part of core LOKI code.",
        mime_type="application/json",
    )
    def external_legacy_libraries_resource() -> str:
        return _json_text({"libraries": operator_surface.external_legacy_libraries(include_content=False)})

    @mcp.resource(
        "loki://ollama-status",
        name="LOKI THE SUN GOD Ollama Status",
        description="Offline/local Ollama and 9router availability snapshot.",
        mime_type="application/json",
    )
    def ollama_status_resource() -> str:
        return _json_text(operator_surface.ollama_router_status())

    @mcp.resource(
        "loki://chatgpt/widget/v1",
        name="LOKI THE SUN GOD ChatGPT Widget",
        description="ChatGPT Apps widget shell for LOKI status, mixer, NPC, and activity state.",
        mime_type="text/html;profile=mcp-app",
    )
    def chatgpt_widget_resource() -> str:
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            "<style>\n"
            "body{font-family:Inter,system-ui,sans-serif;margin:0;background:#0c0d10;color:#e5e7eb}\n"
            "main{padding:16px;display:grid;gap:12px}\n"
            "section{border:1px solid #3f4147;border-radius:8px;padding:12px;background:#15171b}\n"
            "h1,h2{margin:0 0 8px} code{color:#f6c244}\n"
            "</style></head>\n"
            "<body><main>\n"
            "<h1>LOKI THE SUN GOD</h1>\n"
            "<section><h2>ChatGPT App</h2><p>"
            "Use read tools for guild status, commands, music, NPC, activities, and Mythos packet state. "
            "Mutations remain server-side permission gated.</p></section>\n"
            "<section><h2>Tools</h2><p>"
            "<code>loki_get_music_state</code>, <code>loki_get_npc_summary</code>, "
            "<code>loki_get_activity_state</code>, <code>loki_get_mythos_summary</code>"
            "</p></section>\n"
            "</main></body></html>\n"
        )

    @mcp.resource(
        "loki://guild/{guild_id}/config",
        name="LOKI THE SUN GOD Guild Config",
        description="Config snapshot for a local LOKI THE SUN GOD guild.",
        mime_type="application/json",
    )
    def guild_config_resource(guild_id: str) -> str:
        return _json_text(operator_surface.guild_config_snapshot(int(guild_id)))

    @mcp.resource(
        "loki://guild/{guild_id}/channels",
        name="LOKI THE SUN GOD Guild Channels",
        description="Live or saved channel clusters for a local LOKI THE SUN GOD guild.",
        mime_type="application/json",
    )
    def guild_channels_resource(guild_id: str) -> str:
        return _json_text(operator_surface.channel_cluster_snapshot(int(guild_id)))

    @mcp.tool(
        name="loki_list_guilds",
        description="List the guilds stored in LOKI THE SUN GOD's local database.",
        structured_output=True,
    )
    def loki_list_guilds(args: EmptyArgs) -> GuildListResult:
        guilds = operator_surface.list_guilds()
        return GuildListResult(guilds=guilds, total=len(guilds))

    @mcp.tool(
        name="loki_get_guild_config",
        description="Return a complete guild config snapshot from local LOKI THE SUN GOD data.",
        structured_output=True,
    )
    def loki_get_guild_config(args: GuildQuery) -> GuildConfigResult:
        return GuildConfigResult(guild_id=args.guild_id, snapshot=operator_surface.guild_config_snapshot(args.guild_id))

    @mcp.tool(
        name="loki_get_channel_clusters",
        description="Return live or fallback channel clusters for a guild.",
        structured_output=True,
    )
    def loki_get_channel_clusters(args: GuildQuery) -> ChannelClusterResult:
        snapshot = operator_surface.channel_cluster_snapshot(args.guild_id)
        return ChannelClusterResult(**snapshot)

    @mcp.tool(
        name="loki_search_commands",
        description="Search the local LOKI THE SUN GOD command catalog.",
        structured_output=True,
    )
    def loki_search_commands(args: CommandSearchQuery) -> CommandSearchResult:
        commands = operator_surface.command_library(
            query=args.query,
            category=args.category,
            slash_only=args.slash_only,
        )
        return CommandSearchResult(commands=commands, total=len(commands))

    @mcp.tool(
        name="loki_search_ai_docs",
        description="Search the local AI/operator documentation library.",
        structured_output=True,
    )
    def loki_search_ai_docs(args: DocSearchQuery) -> DocSearchResult:
        docs = operator_surface.search_ai_docs(args.query, include_content=args.include_content)
        return DocSearchResult(docs=docs, total=len(docs))

    @mcp.tool(
        name="loki_search_external_legacy_libraries",
        description="Search extracted external legacy libraries, including Ralph Wiggum/CarlClone behavior metadata.",
        structured_output=True,
    )
    def loki_search_external_legacy_libraries(args: LegacyLibrarySearchQuery) -> LegacyLibrarySearchResult:
        libraries = operator_surface.search_external_legacy_libraries(
            args.query,
            include_content=args.include_content,
        )
        return LegacyLibrarySearchResult(libraries=libraries, total=len(libraries))

    @mcp.tool(
        name="loki_get_diagnostics",
        description="Return local LOKI THE SUN GOD diagnostics without requiring live Discord connectivity.",
        structured_output=True,
    )
    def loki_get_diagnostics(args: EmptyArgs) -> DiagnosticsResult:
        return DiagnosticsResult(diagnostics=operator_surface.diagnostics_snapshot())

    @mcp.tool(
        name="loki_get_ollama_status",
        description="Return local Ollama and 9router status information.",
        structured_output=True,
    )
    def loki_get_ollama_status(args: EmptyArgs) -> OllamaStatusResult:
        return OllamaStatusResult(status=operator_surface.ollama_router_status())

    @mcp.tool(
        name="loki_get_music_state",
        description="Use this when you need the LOKI mixer, equalizer, and music-session configuration.",
        structured_output=True,
    )
    def loki_get_music_state(args: GuildQuery) -> MusicStateResult:
        return MusicStateResult(state=operator_surface.loki_music_snapshot(args.guild_id))

    @mcp.tool(
        name="loki_get_npc_summary",
        description="Use this when you need LOKI NPC status, learning scope, and admin-gate summary.",
        structured_output=True,
    )
    def loki_get_npc_summary(args: GuildQuery) -> NpcSummaryResult:
        return NpcSummaryResult(summary=operator_surface.loki_npc_snapshot(args.guild_id))

    @mcp.tool(
        name="loki_get_activity_state",
        description="Use this when you need LOKI activity and scheduled-event orchestration state.",
        structured_output=True,
    )
    def loki_get_activity_state(args: GuildQuery) -> ActivityStateResult:
        return ActivityStateResult(state=operator_surface.loki_activity_snapshot(args.guild_id))

    @mcp.tool(
        name="loki_get_mythos_summary",
        description="Use this when you need the Mythos run and packet status for the LOKI rebuild.",
        structured_output=True,
    )
    def loki_get_mythos_summary(args: EmptyArgs) -> MythosSummaryResult:
        return MythosSummaryResult(summary=operator_surface.loki_mythos_snapshot())

    if writes_enabled():

        @mcp.tool(
            name="loki_save_guild_config",
            description=(
                "Persist a safe subset of guild config and automod settings. "
                "Enabled only when LOKI_MCP_ENABLE_WRITES=true."
            ),
            structured_output=True,
        )
        def loki_save_guild_config(args: GuildConfigWriteInput) -> MutationResult:
            payload = args.model_dump()
            guild_id = payload.pop("guild_id")
            snapshot = operator_surface.save_guild_config(guild_id, payload)
            return MutationResult(ok=True, message="Guild config saved.", snapshot=snapshot)

        @mcp.tool(
            name="loki_delete_sticky",
            description="Delete a sticky entry by guild and channel. Enabled only when LOKI_MCP_ENABLE_WRITES=true.",
            structured_output=True,
        )
        def loki_delete_sticky(args: StickyDeleteInput) -> MutationResult:
            deleted = operator_surface.delete_sticky(args.guild_id, args.channel_id)
            return MutationResult(
                ok=True,
                message="Sticky deleted." if deleted else "No sticky matched the request.",
                deleted=deleted,
            )
    else:
        LOGGER.info("Starting in read-only mode. Set LOKI_MCP_ENABLE_WRITES=true to enable write tools.")

    @mcp.prompt(
        name="loki_operator_brief",
        description=(
            "Create a concise operator brief using current LOKI diagnostics, docs, and optional guild context."
        ),
    )
    def loki_operator_brief(guild_id: str = "") -> list[dict[str, str]]:
        guild_block = ""
        if guild_id.strip():
            try:
                guild_block = "\nGuild snapshot:\n" + _json_text(operator_surface.guild_config_snapshot(int(guild_id)))
            except Exception:
                guild_block = f"\nGuild snapshot lookup failed for guild_id={guild_id}."
        content = (
            "Prepare a short LOKI THE SUN GOD operator brief.\n\n"
            f"Overview:\n{_json_text(operator_surface.overview_snapshot())}\n\n"
            f"Diagnostics:\n{_json_text(operator_surface.diagnostics_snapshot())}"
            f"{guild_block}\n\n"
            "Highlight issues, offline gaps, and the next three concrete operator actions."
        )
        return [{"role": "user", "content": content}]

    @mcp.prompt(
        name="loki_review_guild_config",
        description="Review a guild config snapshot and suggest safe improvements.",
    )
    def loki_review_guild_config(guild_id: str) -> list[dict[str, str]]:
        snapshot = operator_surface.guild_config_snapshot(int(guild_id))
        content = (
            "Review this LOKI THE SUN GOD guild configuration for usability, moderation coverage, "
            "and missing operator setup.\n\n"
            f"{_json_text(snapshot)}\n\n"
            "Explain what each major setting currently implies, flag weak spots, and "
            "recommend safe changes without inventing data."
        )
        return [{"role": "user", "content": content}]

    @mcp.prompt(
        name="loki_explain_command",
        description="Explain a LOKI THE SUN GOD command with local command metadata and operator docs.",
    )
    def loki_explain_command(command_name: str) -> list[dict[str, str]]:
        commands = operator_surface.command_library(query=command_name)
        docs = operator_surface.search_ai_docs(command_name, include_content=False)[:5]
        content = (
            f"Explain the LOKI THE SUN GOD command `{command_name}` using only the local command catalog "
            "and operator docs.\n\n"
            f"Command matches:\n{_json_text(commands[:10])}\n\n"
            f"Relevant docs:\n{_json_text(docs)}\n\n"
            "Describe what the command does, its important options, common operator mistakes, and when to use it."
        )
        return [{"role": "user", "content": content}]

    return mcp


server = create_server()
