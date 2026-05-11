# Deployment Guide

## Current Deployment Status

The rebuilt repo is deployment-ready after local verification, but no live Railway project was created from this workspace during the rebuild.

Highest-priority remaining items:

1. Railway deployment.
2. Hosted Discord OAuth callback test.
3. Live Discord `/dashboard` plus post-restart relay message test in the actual channels.

The Vercel target is limited to the sanitized static operator preview in
[VERCEL_PREVIEW.md](/C:/LOKI%20THE%20SUN%20GOD/docs/VERCEL_PREVIEW.md). Do not
deploy the repo root to Vercel because local runtime data and logs can exist
outside Git tracking.

## What Ships

LOKI THE SUN GOD has three operator surfaces:

- Discord bot: [bot.py](/C:/LOKI%20THE%20SUN%20GOD/bot.py)
- Web dashboard: [dashboard_app.py](/C:/LOKI%20THE%20SUN%20GOD/dashboard_app.py)
- Desktop control center: [desktop_app.py](/C:/LOKI%20THE%20SUN%20GOD/desktop_app.py)

The shared database schema is bootstrapped from [utils/db.py](/C:/LOKI%20THE%20SUN%20GOD/utils/db.py), so deployments should always run the shared preflight before first launch.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy [.env.example](/C:/LOKI%20THE%20SUN%20GOD/.env.example) to `.env` and set:

- `DISCORD_TOKEN`
- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `REDIRECT_URI`
- `DASHBOARD_SECRET_KEY`
- `DASHBOARD_PUBLIC_URL`
- `DATABASE_URL` when using Railway/Postgres

Recommended:

- `TEST_GUILD_ID`
- `OWNER_ID`

Optional stream integrations:

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

## Discord Portal Checklist

Enable the bot's required privileged intents in the Discord Developer Portal before production use:

- `MESSAGE_CONTENT`
- `GUILD_MEMBERS`

## Release Preflight

Run:

```powershell
python .\scripts\release_check.py --strict-env
python .\scripts\db_smoke_test.py
```

This verifies:

- Python compilation across the repo
- shared database bootstrap and migrations
- SQLite smoke tests, and Postgres when `DATABASE_URL` is set
- command catalog generation
- relay configuration and readiness log presence when enabled
- dashboard health routes
- desktop operator API wiring
- required environment values

## Start Modes

### Local full stack

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

### Direct bot

```powershell
python bot.py
```

### Direct dashboard

```powershell
python dashboard_app.py
```

### Desktop release build

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_standalone.ps1
```

## Health Checks

- Dashboard: `GET /healthz`
- Desktop control center: `GET /api/status`

The dashboard health response includes whether OAuth is configured and whether the local LOKI THE SUN GOD bridge is available.

## Database Notes

SQLite lives at `data/bot.db`.

On Railway, `DATABASE_URL` switches the shared database adapter to Postgres while preserving the same bot and dashboard code paths. See [RAILWAY_DEPLOYMENT.md](/C:/LOKI%20THE%20SUN%20GOD/docs/RAILWAY_DEPLOYMENT.md) for the two-service setup.

Release-safe migrations currently cover:

- legacy ticket table migration to the current `status` and transcript-aware model
- `form_responses` decision columns used by the dashboard approval flow
- ticket configuration columns in `guild_config`
- `stream_subs` bootstrap for stream tracking

## Packaging Notes

The desktop packaging script builds a one-file PyInstaller executable. The bot and dashboard themselves still depend on correct runtime environment values and Discord access when launched from the packaged desktop.
