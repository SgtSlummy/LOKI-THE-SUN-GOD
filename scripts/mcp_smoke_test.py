from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.mcp.seed_fixture import seed_fixture  # noqa: E402

FIXTURE_GUILD_ID = 123456789012345678


async def run_smoke_test() -> None:
    manifest = seed_fixture(ROOT / "tests" / "fixtures" / "mcp" / "generated")
    env = os.environ.copy()
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "LOKI_DB_PATH": manifest["db_path"],
            "LOKI_DOCS_PATH": manifest["docs_path"],
            "LOKI_CODEX_SETTINGS_PATH": manifest["codex_settings_path"],
            "LOKI_ENV_PATH": manifest["env_path"],
            "LOKI_RUNTIME_LOG_PATH": manifest["runtime_log_path"],
        }
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loki_mcp"],
        cwd=ROOT,
        env=env,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            required_tools = {
                "loki_list_guilds",
                "loki_get_guild_config",
                "loki_get_channel_clusters",
                "loki_search_commands",
                "loki_search_ai_docs",
                "loki_get_diagnostics",
                "loki_get_ollama_status",
            }
            missing_tools = sorted(required_tools - set(tool_names))
            if missing_tools:
                raise AssertionError(f"Missing required tools: {', '.join(missing_tools)}")
            if "loki_save_guild_config" in tool_names or "loki_delete_sticky" in tool_names:
                raise AssertionError("Write tools should not be exposed in read-only smoke tests.")

            resources_result = await session.list_resources()
            resource_uris = {str(resource.uri) for resource in resources_result.resources}
            for uri in {
                "loki://overview",
                "loki://diagnostics",
                "loki://commands",
                "loki://options",
                "loki://ai-docs",
                "loki://ollama-status",
            }:
                if uri not in resource_uris:
                    raise AssertionError(f"Missing required resource: {uri}")

            prompts_result = await session.list_prompts()
            prompt_names = {prompt.name for prompt in prompts_result.prompts}
            for prompt_name in {
                "loki_operator_brief",
                "loki_review_guild_config",
                "loki_explain_command",
            }:
                if prompt_name not in prompt_names:
                    raise AssertionError(f"Missing required prompt: {prompt_name}")

            overview = await session.read_resource("loki://overview")
            overview_text = overview.contents[0].text
            overview_data = json.loads(overview_text)
            if overview_data.get("guild_count") != 1:
                raise AssertionError(f"Unexpected overview guild count: {overview_data.get('guild_count')}")

            guilds = await session.call_tool("loki_list_guilds", {"args": {}})
            guilds_payload = guilds.structuredContent or {}
            if guilds_payload.get("total") != 1:
                raise AssertionError(f"Unexpected guild total: {guilds_payload.get('total')}")

            config = await session.call_tool(
                "loki_get_guild_config",
                {"args": {"guild_id": FIXTURE_GUILD_ID}},
            )
            config_payload = config.structuredContent or {}
            prefix = ((config_payload.get("snapshot") or {}).get("config") or {}).get("prefix")
            if prefix != "!":
                raise AssertionError(f"Unexpected prefix in guild config snapshot: {prefix}")

            command_search = await session.call_tool(
                "loki_search_commands",
                {"args": {"query": "welcome", "category": "", "slash_only": False}},
            )
            command_payload = command_search.structuredContent or {}
            if not command_payload.get("commands"):
                raise AssertionError("Command search returned no matches for 'welcome'.")

            ai_doc_search = await session.call_tool(
                "loki_search_ai_docs",
                {"args": {"query": "Ollama", "include_content": True}},
            )
            ai_doc_payload = ai_doc_search.structuredContent or {}
            if ai_doc_payload.get("total", 0) < 1:
                raise AssertionError("AI doc search returned no matches for 'Ollama'.")

            prompt = await session.get_prompt(
                "loki_operator_brief",
                {"guild_id": str(FIXTURE_GUILD_ID)},
            )
            if not prompt.messages:
                raise AssertionError("Operator brief prompt returned no messages.")


def main() -> int:
    asyncio.run(run_smoke_test())
    print("loki_mcp smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
