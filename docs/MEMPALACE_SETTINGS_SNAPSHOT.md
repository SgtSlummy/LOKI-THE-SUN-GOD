# MemPalace Settings Snapshot

## Project identity

- Workspace: `C:\LOKI THE SUN GOD`
- Bot entrypoint: `bot.py`
- Dashboard entrypoint: `dashboard_app.py`
- Desktop entrypoint: `desktop_app.py`

## Required environment

Bot runtime:

- `DISCORD_TOKEN`

Dashboard OAuth:

- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `REDIRECT_URI`
- `DASHBOARD_SECRET_KEY`

Optional:

- `PREFIX`
- `OWNER_ID`
- `TEST_GUILD_ID`
- `RELAY_ENABLED`
- `RELAY_GUILD_ID`
- `RELAY_FRIENDS_ROLE_NAME`
- `RELAY_TARGET_CHANNEL_IDS`
- `RELAY_TARGET_CHANNEL_NAMES`
- `RELAY_IGNORED_SOURCE_CHANNEL_IDS`
- `RELAY_WEBHOOK_NAME`
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

Reference source: `.env.example`

## Desktop settings

Source file: `desktop_config.json`

- Control API port: `7331`
- Single-instance lock port: `7332`
- Default test guild ID: `1463393482306486387`
- Auto-start services:
  - `loki` -> bot
  - `dash` -> dashboard
- Relay ownership:
  - LOKI THE SUN GOD owns Friends-role channel relay through `cogs/relay.py`
  - Millhouse PM2 relay is retired; if relay stops, restart the bot and inspect `data/relay.log`

Dashboard shortcuts:

- LOKI Dashboard -> `http://localhost:5000`
- 9router -> `http://localhost:20128`
- Discord Developer Portal -> `https://discord.com/developers/applications`

## Shared schema and migrations

Source file: `utils/db.py`

Shared DB path:

- `data/bot.db`

Current bootstrap responsibilities:

- initialize the core schema for bot, dashboard, and desktop
- migrate legacy `tickets` rows to the newer `status` model
- add `status`, `decided_by`, `decided_at`, and `decision_note` to `form_responses`
- ensure `tickets_category_id`, `tickets_log_channel`, and `tickets_staff_role` exist in `guild_config`
- ensure `stream_subs` exists for stream tracking

## Shared command metadata

Source files:

- `utils/command_catalog.py`
- `utils/command_descriptions.py`

Current release numbers:

- total commands indexed: `263`
- slash-capable commands indexed: `202`
- missing slash descriptions in release check: `0`

Latest command-surface refinements:

- AutoMod now supports direct threshold tuning for mentions, spam, caps, and blocked-word management from Discord
- suggestions, welcome, sticky, highlights, streams, tickets, and custom embeds gained clearer slash-safe admin flows
- reaction-role commands now use message links or current-channel message IDs instead of unsupported `discord.Message` slash parameters
- release preflight now checks both catalog coverage and hybrid/slash signature safety

## Health and release scripts

Release preflight:

- `python .\scripts\release_check.py`
- `python .\scripts\release_check.py --strict-env`

Local startup:

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1`

Local smoke test:

- `powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_local.ps1`

Restart helpers:

- `powershell -ExecutionPolicy Bypass -File .\scripts\restart_all.ps1`
- `powershell -ExecutionPolicy Bypass -File .\scripts\restart_dash.ps1`

Relay troubleshooting:

- if LOKI THE SUN GOD is not relaying messages between channels, restart the bot first so `.env`, role IDs, target channels, and webhooks refresh
- use `/relay status` in Discord to confirm resolved role and target channels
- inspect `data/relay.log` for skip reasons such as missing Friends role, ignored source channel, or missing target permissions

Desktop packaging:

- `powershell -ExecutionPolicy Bypass -File .\scripts\build_standalone.ps1`

Health endpoints:

- dashboard -> `http://127.0.0.1:5000/healthz`
- desktop -> `http://127.0.0.1:7331/api/status`

## Current ship state

Verified on `2026-05-11` from this rebuilt workspace:

- release preflight passes in non-strict mode
- strict mode is expected to fail until real Discord/OAuth/dashboard secrets are set
- command catalog reports `263` indexed commands and `202` slash-capable entries
- dashboard health, desktop API, MCP smoke test, secret scan, lint, compile, and unit tests pass locally
- Wavelink/Lavalink runtime wiring, LOKI EQ presets, mixer surfaces, NPC privacy gates, activity permission gates, and Codex AGI advisory adapters are implemented
- Windows executable packaging scripts/specs exist, but a new packaged `.exe` was not built in this Linux/WSL verification pass

## Remaining deployment blockers

- GitHub remote repository creation still has to happen with GitHub UI, `gh`, or another authenticated GitHub tool.
- Railway deployment and Discord OAuth authorization must happen outside the local repo.
- Hosted `REDIRECT_URI` must be changed to the deployed callback URL before online OAuth testing.
- `DATABASE_URL` is required for hosted Postgres; local/dev stays on SQLite.
- Live Discord and Lavalink checks require real bot credentials and a reachable Lavalink node.
