# AI Operator Library

This library is intended for local AI agents and helper tools that need concise project context without navigating the full repo.

## Purpose

- Explain the desktop app's control surface.
- Document the guild configuration data that powers the `LOKI` tab.
- Capture the local-model workflow for Ollama and 9router.
- Provide a stable starting point for future operator automations.

## Current Operator Surfaces

- `desktop_app.py`: native desktop control panel and local HTTP API.
- `dashboard_app.py`: Flask dashboard for guild-facing administration.
- `bot.py`: Discord bot entry point that loads all cogs from `cogs/`.
- `utils/db.py`: SQLite schema and async DB helpers for the bot.

## LOKI tab Contract

The LOKI tab now expects these local HTTP endpoints:

- `/api/loki/guilds`
- `/api/loki/<guild_id>/config`
- `/api/loki/command-library`
- `/api/loki/<guild_id>/channels`
- `/api/loki/options`
- `/api/loki/ai-docs`
- `/api/loki/ollama`
- `/api/diagnostics`

## Command Library Notes

- Commands are discovered statically from `cogs/*.py`.
- The catalog includes prefix, hybrid, group, slash, and subcommand decorators.
- Descriptions fall back to function docstrings when decorator descriptions are missing.

## Channel Explorer Notes

- Live guild channels are fetched through the Discord REST API when `DISCORD_TOKEN` is available.
- Channels are grouped into these buckets:
  - `text`
  - `announcements`
  - `voice`
  - `side_chat`
  - `other`
- Side chat is a naming heuristic for lounge or off-topic style spaces.

## Local Model Notes

- Ollama health is inferred from configured `OLLAMA_HOST`, defaulting to `http://127.0.0.1:11434/api/tags`.
- 9router health is inferred from `http://127.0.0.1:20128/v1/models` for local runtime checks.
- The current hosted 9router Dolphin research dashboard is `https://9router-production-4a07.up.railway.app/dashboard/research`.
- Local-first routing prefers `dolphin3:8b`, `qwen2.5-coder:7b`, `llama3.1:8b`, `llama3.2:3b`, then the first installed Ollama model.
- 9router uses the alias `local-default -> ollama-local/<model>` when the local model route is saved.
- Codex routing state is read from `%USERPROFILE%\\.Codex\\settings.json`.
- LOKI THE SUN GOD's Discord `/ask` command uses `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `LOKI_LLM_MODEL` through a Chat Completions-compatible endpoint.

## Runtime Notes

- Desktop service lifecycle events are appended to `desktop_runtime.log`.
- Single-instance protection uses a localhost socket lock.
- Managed services avoid duplicate launches by attaching to matching existing processes when present.
