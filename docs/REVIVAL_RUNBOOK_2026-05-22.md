# LOKI Full-Stack Revival Runbook

Date: 2026-05-22

This runbook is the current operator path for reviving `LOKI THE SUN GOD` as a
clean Railway deployment. It supersedes the May 13 production service IDs in
older handoff docs. Treat the old services as reference evidence only.

## Recovery State

- Repo path: `D:\AI&Vibecode\LOKI THE SUN GOD\LOKI THE SUN GOD`.
- Recovery branch: `codex/loki-full-stack-revival-20260522`.
- Do not deploy from a dirty mixed worktree. Commit or intentionally stash the
  current revival changes before any Railway deploy.
- Local `.env` is ignored and may contain real credentials. Do not print it,
  paste it into docs, or use it as a Railway variable dump.
- Local Python was broken during the audit because `.venv` pointed at a missing
  Python install. Rebuild it from a real Python 3.12 runtime before running
  Python gates.
- `railway`, `npm`, and `gh` were not on PATH during the audit. Install or add
  them to PATH before deployment and GitHub/Railway automation.

## Target Railway Services

Create a fresh Railway project named `LOKI THE SUN GOD` or another explicit
operator-approved name. Use separate services so each runtime can restart
independently.

| Service | Root | Runtime | Start command |
| --- | --- | --- | --- |
| `dashboard` | repo root | Python/Nixpacks | `gunicorn dashboard_app:app --bind 0.0.0.0:${PORT:-8080}` |
| `worker` | repo root | Python/Nixpacks | `python -m bot` |
| `Postgres` | Railway plugin | Postgres | managed by Railway |
| `lavalink` | `lavalink/` | Dockerfile | image default |
| `activity-bridge` | `services/activity-bridge` | Node | `LOKI_ACTIVITY_SERVICE_ROLE=bridge` |
| `activity-client` | `services/activity-bridge` | Node static | `LOKI_ACTIVITY_SERVICE_ROLE=client` |

## Current Railway Deployment

As of May 22, 2026, the clean revival deployment is:

```text
Project: LOKI THE SUN GOD REVIVAL
Project ID: 5b5a664a-926e-4971-b90b-73bd6187127a
dashboard: https://dashboard-production-3d2a.up.railway.app
activity-bridge: https://activity-bridge-production.up.railway.app
activity-client: https://activity-client-production.up.railway.app
lavalink: https://lavalink-production-5b27.up.railway.app
```

The production services were verified `SUCCESS/RUNNING` with:

- Dashboard `GET /healthz`: `ok=true`, `database_backend=postgres`,
  `database_ok=true`, `oauth_ready=true`.
- Activity Bridge `GET /healthz`: `ok=true`, API auth configured, bridge-side
  controls disabled.
- Activity client `GET /healthz`: `ok=true`, serving `client/dist`; `/` returns
  the Discord Activity Stream Control page.
- Lavalink logs: version 4.2.2 ready on Railway `PORT`.
- Worker logs: logged in as `LOKI THE SUN GOD`, natural-language slash sync
  disabled, song mirror and Diva/Wreckingball cleanup disabled until live
  review.

Direct OpenAI is configured by base URL/model, but `OPENAI_API_KEY` is not set
in Railway yet. Set the real secret on both `dashboard` and `worker`, then
redeploy or restart those services before accepting `/ask`.

Use `LOKI_START_COMMAND` per Python service so the same root config can run both
the dashboard and worker:

```text
dashboard LOKI_START_COMMAND=gunicorn dashboard_app:app --bind 0.0.0.0:${PORT:-8080}
worker    LOKI_START_COMMAND=python -m bot
```

The root `nixpacks.toml` evaluates `LOKI_START_COMMAND` inside the startup
shell so Railway's `PORT` expands at runtime. Keep this variable restricted to
trusted operators.

## Production Variables

Set these on both `dashboard` and `worker`:

```text
DISCORD_TOKEN
DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET
DASHBOARD_SECRET_KEY
DATABASE_URL
OPENAI_API_KEY
OPENAI_BASE_URL=https://api.openai.com/v1
LOKI_LLM_MODEL=gpt-5.5
```

Set these on `dashboard`:

```text
REDIRECT_URI=https://<dashboard-domain>/callback
DASHBOARD_PUBLIC_URL=https://<dashboard-domain>
DASHBOARD_HOST=0.0.0.0
DASHBOARD_DEBUG=false
ACTIVITY_BRIDGE_URL=https://<activity-bridge-domain>
ACTIVITY_BRIDGE_TOKEN=<shared bridge secret>
ACTIVITY_CLIENT_PUBLIC_URL=https://<activity-client-domain>
ALLOW_ACTIVITY_SIDE_CONTROLS=false
ALLOW_STREAM_START_STOP=false
```

Set these on `worker`:

```text
DASHBOARD_PUBLIC_URL=https://<dashboard-domain>
LAVALINK_URI=https://<lavalink-domain>
LAVALINK_PASSWORD=<same value used by Lavalink service>
LOKI_NATURAL_LANGUAGE_ONLY=true
LOKI_ENABLE_SLASH_SYNC=false
LOKI_NPC_ENABLED=false
```

Enable `LOKI_NPC_ENABLED`, relay, song mirror, jukebox, and Diva/Wreckingball
cleanup only after live Discord channel IDs and permissions have been verified.

Set these on `lavalink`:

```text
LAVALINK_SERVER_PASSWORD=<shared Lavalink password>
```

Set these on `activity-bridge`:

```text
LOKI_ACTIVITY_SERVICE_ROLE=bridge
ACTIVITY_BRIDGE_TOKEN=<same shared bridge secret>
DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET
PUBLIC_SERVER_ORIGIN=https://<activity-bridge-domain>
PUBLIC_CLIENT_ORIGIN=https://<activity-client-domain>
ENABLE_BRIDGE_DISCORD_BOT=false
ALLOW_ACTIVITY_SIDE_CONTROLS=false
ALLOW_STREAM_START_STOP=false
OBS_WEBSOCKET_URL
OBS_WEBSOCKET_PASSWORD
TWITCH_CLIENT_ID
TWITCH_CLIENT_SECRET
TWITCH_BROADCASTER_ID
TWITCH_ACCESS_TOKEN
```

Set only public build-time values on `activity-client`:

```text
LOKI_ACTIVITY_SERVICE_ROLE=client
VITE_DISCORD_CLIENT_ID=<discord application/client id>
VITE_SERVER_ORIGIN=https://<activity-bridge-domain>
VITE_WS_ORIGIN=wss://<activity-bridge-domain>
```

Never put bot tokens, bridge tokens, client secrets, Twitch tokens, OBS
passwords, or OpenAI keys into `VITE_*` variables.

## Hybrid AI Policy

Production uses OpenAI directly:

```text
OPENAI_BASE_URL=https://api.openai.com/v1
LOKI_LLM_MODEL=gpt-5.5
```

Local fallback can keep 9router/Ollama:

```text
OPENAI_BASE_URL=http://127.0.0.1:20128/v1
LOKI_LLM_MODEL=local-default
```

The Discord `/ask` command remains Manage Server gated. NPC Responses API calls
continue to send `store=false`.

## Discord Developer Portal

Before live acceptance:

1. Enable privileged intents: `MESSAGE_CONTENT` and `GUILD_MEMBERS`.
2. Add `https://<dashboard-domain>/callback` as an OAuth2 redirect.
3. Confirm bot invite scopes: `bot` and `applications.commands`.
4. Confirm OAuth scopes for dashboard login: `identify` and `guilds`.
5. Add Activity URL mappings after `activity-client` and `activity-bridge`
   domains exist.

## Local Repair Gates

Run from the repo root after rebuilding `.venv` and reinstalling Node
dependencies:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe scripts\release_check.py --local-db
.\.venv\Scripts\python.exe -m pytest -q
```

`--local-db` sets `LOKI_IGNORE_ENV_DATABASE_URL=true` for the preflight process
so dashboard and desktop imports do not reload a hosted `DATABASE_URL` from the
ignored local `.env`.

For supervised Windows background starts where the wrapper command line itself
contains `-m bot`, set `LOKI_SKIP_LOCAL_DUPLICATE_WORKER_STOP=true` for the
worker process only. This prevents the local duplicate-process cleaner from
terminating the launcher wrapper while preserving the shared worker lease and
outbound post guard.

Run from `services/activity-bridge`:

```powershell
npm ci
npm run test:rooms
npm run typecheck
npm run build
```

If `npm` is unavailable on PATH, install Node/npm or use a Node distribution
that includes npm. The Codex-bundled `node.exe` alone is not enough for `npm ci`.

## Deployment Checks

After each deploy:

- Dashboard `GET /healthz` returns `ok: true`, `database_backend: postgres`,
  `database_ok: true`, and `oauth_ready: true`.
- Worker logs show Discord login, cog loads, singleton lease acquisition, and no
  fatal OpenAI/Lavalink configuration errors.
- Lavalink logs show the server bound to Railway `PORT` and using the configured
  password.
- Activity Bridge `GET /healthz` passes.
- Activity Bridge room APIs reject missing `Authorization: Bearer` tokens.

## Live Discord Acceptance

Run these manually in the production Discord server:

1. `/dashboard` returns the new hosted dashboard URL.
2. Dashboard OAuth login completes.
3. `/ask` works with direct OpenAI and remains Manage Server gated.
4. NPC replies only when enabled and addressed.
5. NPC memory respects channel allowlist and opt-out settings.
6. Music queues and plays through Lavalink from a voice channel.
7. Dashboard Activity Control can reach Activity Bridge and update a room.
8. Relay, song mirror, and Diva/Wreckingball cleanup are enabled only after
   channel IDs and bot permissions are verified.

## Rollback

Keep these before deploying:

- Git commit SHA used by each service.
- Railway variable name inventory for each service, without secret values.
- Dashboard domain and OAuth redirect currently configured in Discord.
- Database backup or Railway Postgres restore point before schema-affecting
  changes.
- Previous Activity Bridge build commit and client static artifact source.
