# LOKI THE SUN GOD MCP

LOKI THE SUN GOD now includes a repo-local offline MCP server named `loki_mcp`.

## What It Exposes

- transport: `stdio`
- default mode: read-only
- primary data sources:
  - local SQLite
  - command catalog
  - operator docs
  - Ollama and 9router status checks

## Start It

From the repo root:

```powershell
python -m loki_mcp
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_loki_mcp.ps1
```

## Available Resources

- `loki://overview`
- `loki://diagnostics`
- `loki://commands`
- `loki://options`
- `loki://ai-docs`
- `loki://ollama-status`
- `loki://guild/{guild_id}/config`
- `loki://guild/{guild_id}/channels`

## Available Tools

- `loki_list_guilds`
- `loki_get_guild_config`
- `loki_get_channel_clusters`
- `loki_search_commands`
- `loki_search_ai_docs`
- `loki_get_diagnostics`
- `loki_get_ollama_status`

Optional write tools are only registered when `LOKI_MCP_ENABLE_WRITES=true`:

- `loki_save_guild_config`
- `loki_delete_sticky`

## Prompts

- `loki_operator_brief`
- `loki_review_guild_config`
- `loki_explain_command`

## Local Registration

No Codex MCP registration directory was discovered in this workspace, so this repo does not write global MCP config automatically.

Use a local client registration that runs:

- command: `python`
- args: `-m loki_mcp`
- cwd: `C:\LOKI THE SUN GOD`

## Fixture Smoke Test

Run:

```powershell
python .\scripts\mcp_smoke_test.py
```

That test seeds a stable local fixture DB and docs shelf, launches `loki_mcp` over `stdio`, then verifies:

- tools are listed
- resources are listed
- `loki://overview` is readable
- `loki_list_guilds` works
- `loki_search_commands` works
- prompts are registered

## Fixture Overrides

The MCP server honors these optional local overrides:

- `LOKI_DB_PATH`
- `LOKI_DOCS_PATH`
- `LOKI_AI_DOCS_PATH`
- `LOKI_CODEX_SETTINGS_PATH`
- `LOKI_ENV_PATH`
- `LOKI_RUNTIME_LOG_PATH`
- `LOKI_COMMAND_ROOT`
