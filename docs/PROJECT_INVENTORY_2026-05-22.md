# LOKI Project Inventory

Date: 2026-05-22

This inventory records what is in the repo at revival time and which pieces are
runtime-critical for the full-stack Railway rebuild.

## Root Runtime

- `bot.py`: Discord worker entrypoint. Loads `.env`, initializes the shared DB,
  claims the worker singleton lease, installs outbound post guards, loads cogs,
  and optionally syncs slash commands.
- `dashboard_app.py`: Flask dashboard entrypoint. Handles Discord OAuth,
  guild/admin pages, AI/router settings, research lab, Activity Control, and
  `/healthz`.
- `desktop_app.py`: local Windows operator control center with service controls,
  diagnostics, backups, and local dashboard cards.
- `utils/db.py`: shared SQLite/Postgres schema bootstrap and sync/async DB
  adapter used by bot, dashboard, desktop, and MCP.
- `requirements.txt`: Python runtime dependencies for Discord, Flask, Postgres,
  MCP, music, desktop packaging, and voice playback.
- `Procfile`, `railway.toml`, `nixpacks.toml`, `runtime.txt`: root hosted Python
  deployment configuration.

## Discord Cogs

The bot loads the manifest in `cogs/__init__.py`. Major surfaces include:

- AI: admin-gated `/ask` through `utils/llm_client.py`.
- NPC: public addressed replies, redacted public memory, permission routing, and
  OpenAI Responses API/Hermes fallback.
- Music: Wavelink/Lavalink playback, queue controls, jukebox panel, mixer, and
  EQ presets.
- Activity controls: Discord scheduled event and Activity Bridge dashboard
  integration.
- Relay/song mirror/Wreckingball cleanup: production channel automation with
  duplicate guards and opt-in channel IDs.
- Moderation/community features: automod, antiraid, tickets, forms, roles,
  reaction roles, reminders, polls, giveaways, starboard, tags, welcome,
  highlights, streams, and utility commands.

## AI And Memory

- `utils/llm_client.py`: OpenAI-compatible Chat Completions client for `/ask`.
- `loki_npc/openai_responses.py`: Responses API payload builder for NPC replies
  with `store=false`, low reasoning effort, redacted prompts, and optional Hermes
  CLI fallback.
- `loki_npc/memory.py`: redacts emails/secrets/tokens, stores public memory with
  a 90-day TTL, and supports per-user purge.
- `loki_engine`: permission decisions and natural-language routing for admin
  changes, search rights, and open questions.
- `loki_memory`: bounded external Codex AGI adapter registry.
- `loki_research`: public feature catalog, version packet pipeline, dry-run
  experiments, and Hermes/Mythos package material.

## Dashboard And Operator Surfaces

- `templates/`: Jinja pages for guild config, commands, forms, tickets, events,
  streams, mixer, NPC, Activity Control, developer settings, AI/router settings,
  and research lab.
- `utils/operator_surface.py`: shared read/write helpers for desktop, dashboard,
  and MCP operator views including command catalog, local AI routing, backups,
  diagnostics, MemPalace config, and 9router state.
- `loki_mcp`: local stdio MCP server exposing read-first tools/resources for
  guilds, command search, diagnostics, AI docs, Ollama status, and optional
  writes when explicitly enabled.

## Music And Media

- `loki_music/service.py`: queue and mixer state.
- `loki_music/equalizer.py`: Lavalink EQ presets and custom-band payloads.
- `loki_music/wavelink_backend.py`: Wavelink node connection, track resolution,
  playback, volume, pause, skip, stop, and EQ filter application.
- `lavalink/Dockerfile` and `lavalink/application.yml`: Lavalink v4 service with
  YouTube plugin and Railway `PORT` binding.
- `docs/LOKI_DCA_AUDIO_UPDATE_PACKAGE.md`: future DCA/FFmpeg package design,
  not required for the Railway revival.

## Activity Bridge

- `services/activity-bridge`: TypeScript workspace with `client`, `server`, and
  `shared` packages.
- Server exposes `GET /healthz`, room APIs, token route, and `WS /ws`.
- Client is a Vite Discord Activity using `@discord/embedded-app-sdk`.
- Dashboard talks to the bridge through `loki_activity_bridge/client.py`.
- `ENABLE_BRIDGE_DISCORD_BOT=false` keeps Discord command ownership in the
  Python bot.

## Safety And Deployment Guardrails

- `.env`, `.env.*`, SQLite DBs, logs, caches, generated executables, and
  MemPalace local files are ignored.
- `scripts/secret_scan.py` is a required pre-push/pre-deploy gate.
- Relay refuses `RELAY_ENABLED=true` without shared `DATABASE_URL` unless
  `ALLOW_LOCAL_SQLITE_RELAY=true` is explicitly set for single-machine local use.
- Worker singleton and outbound post guard prevent duplicate hosted/local
  workers from double-posting Discord messages.
- Self-research experiments are dry-run only, blocked in production/Railway, and
  sandboxed under `.loki_lab`.

## Audit Findings At Revival Start

- Branch before revival: `codex/activity-stream-bridge`, ahead 5 and behind 4.
- Revival branch: `codex/loki-full-stack-revival-20260522`.
- Working tree had existing modified files and untracked local helper scripts.
  Those should be preserved and reviewed before deploy.
- Local `.venv` referenced a missing Python install, so Python checks could not
  run until the environment is rebuilt.
- `railway`, `npm`, and `gh` were not on PATH.
- Activity Bridge dependency links did not resolve `@activity/shared` during
  direct TypeScript checks, so run `npm ci` before bridge validation.
