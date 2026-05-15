# LOKI Process and Connections

This is the operator handoff for the 2026-05-13 review and Railway production
deployment pass.

## Current Production State

Railway project: `LOKI THE SUN GOD`

Environment: `production`

Production services:

| Service | Role | Current state |
| --- | --- | --- |
| `dashboard` | Flask dashboard at `https://dashboard-production-9290.up.railway.app` | Online, deployment `e15386b4-c08c-4abd-a6d9-7f8bac36a745` |
| `worker` | Discord bot worker running `python -m bot` | Online, deployment `669aeb2f-2403-49b1-be88-295185ffb52b` |
| `Postgres` | Shared hosted database | Online, deployment `64dbbb9a-8914-456c-8ee9-8e770c964748` |
| `lavalink` | Music playback backend | Online, deployment `020cd7cf-1ea0-4c8c-aa15-0fbdcce5c0b5` |

Dashboard health endpoint:

```text
https://dashboard-production-9290.up.railway.app/healthz
```

The verified health response had `ok: true`, `database_backend: postgres`,
`database_ok: true`, `oauth_ready: true`, and no missing OAuth keys.

## Connection Map

```text
Discord users and guilds
  -> LOKI Discord bot worker (`worker`)
  -> shared Postgres (`DATABASE_URL`)

Browser operators
  -> hosted Flask dashboard (`dashboard`)
  -> Discord OAuth callback (`/callback`)
  -> shared Postgres (`DATABASE_URL`)

LOKI music cog
  -> Railway Lavalink service (`lavalink`)

Dashboard Activity Control panel, optional
  -> Activity Bridge API/WS (`ACTIVITY_BRIDGE_URL`)
  -> static Discord Activity client (`ACTIVITY_CLIENT_PUBLIC_URL`)
  -> OBS/Twitch adapters only when explicitly configured

Local desktop app
  -> local dashboard or `LOKI_DASHBOARD_URL`
  -> local desktop API at `http://127.0.0.1:7331`
```

The Python dashboard and worker must share the same `DATABASE_URL` so relay
dedupe, worker lease ownership, guard audit rows, tickets, forms, and guild
configuration all use the same source of truth.

## Review And Verification Process

Run these before deployment:

```powershell
ruff check .
pytest
python .\scripts\release_check.py
```

For the Activity Bridge workspace:

```powershell
cd .\services\activity-bridge
npm install
npm run typecheck
npm run test:rooms
npm run build
```

The 2026-05-13 pass verified:

- Python lint: passed
- Python tests: `141 passed`
- Release preflight: passed
- Activity Bridge typecheck, room tests, and production build: passed
- Dashboard hosted health: passed
- Railway dashboard and worker status: `SUCCESS`

CodeRabbit CLI was installed, but agent authentication timed out before review
could run. Rerun `coderabbit auth login --agent`, then
`coderabbit review --agent` if CodeRabbit review evidence is required.

## Railway Deployment Process

Check auth and project state:

```powershell
railway whoami
railway service list --environment production
```

Always pass the service explicitly. The local Railway link can point at
`lavalink`, so bare `railway up` from the repo root can deploy the wrong
service.

Deploy dashboard:

```powershell
railway up --service dashboard --environment production --message <message>
railway service status --service dashboard --environment production --json
railway logs --service dashboard --environment production --latest --deployment --lines 200
curl https://dashboard-production-9290.up.railway.app/healthz
```

Deploy worker:

```powershell
railway up --service worker --environment production --message <message>
railway service status --service worker --environment production --json
railway logs --service worker --environment production --latest --lines 120
```

The dashboard should be deployed first because the worker's `/dashboard`
command depends on `DASHBOARD_PUBLIC_URL` pointing at the hosted dashboard.

## Required Railway Variables

Set on both `dashboard` and `worker`:

```text
DISCORD_TOKEN
DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET
DASHBOARD_SECRET_KEY
DATABASE_URL
```

Set on `dashboard`:

```text
REDIRECT_URI=https://dashboard-production-9290.up.railway.app/callback
DASHBOARD_PUBLIC_URL=https://dashboard-production-9290.up.railway.app
DASHBOARD_HOST=0.0.0.0
DASHBOARD_DEBUG=false
```

Set on `worker`:

```text
DASHBOARD_PUBLIC_URL=https://dashboard-production-9290.up.railway.app
LOKI_START_COMMAND=python -m bot
```

Keep relay variables on every relay-capable worker that should participate in
live relay. Keep `RELAY_ENABLED=false` for local dashboard-only runs.

Current production relay takeover values on `worker`:

```text
RELAY_ENABLED=true
RELAY_GUILD_ID=1463393482306486387
RELAY_FRIENDS_ROLE_NAME=Friends
RELAY_TARGET_CHANNEL_IDS=1471988991879549110,1495605587822514287
RELAY_IGNORED_SOURCE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
RELAY_SENSITIVE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
```

The May 13 redeploy verified the worker log line:

```text
Relay ready guild=1463393482306486387 role=1463393482306486394 targets=The Vibez 101 FM (1471988991879549110) | pirate-radio-tower (1495605587822514287)
```

Do not print, paste into docs, or commit secret values. Use Railway variable
commands with stdin for secrets when possible.

## Legacy Ralph/Bartman Takeover

Legacy bot user ID: `1497752932345708584`.

Current LOKI user ID: `1503830186087415908`.

The former Ralph/Bartman relay process is no longer active locally, and the
Ralph workspace Railway link reports its project as deleted. LOKI now owns the
Friends-role relay on the Railway `worker` service.

The current LOKI member already has the shared `SUN GOD` administrator role and
`Robots`. The legacy member still has `SUN GOD`, `Robots`, and the managed
application role `Ralph Wiggum`.

`scripts/migrate_legacy_discord_bot.py --execute` was rerun after the relay
takeover. Discord returned `403 Missing Permissions` for both:

- assigning the managed `Ralph Wiggum` role to LOKI
- removing legacy bot `1497752932345708584` from the guild

This is expected while the old bot has an equal top role (`SUN GOD`) and the
`Ralph Wiggum` role is managed by the old Discord application. A server owner
must first remove `SUN GOD` from the legacy bot, move LOKI above the legacy bot
in the role hierarchy, or manually remove the old bot from the server. After
that, rerun `scripts/migrate_legacy_discord_bot.py --execute` to confirm the
old member is gone.

## Known Runtime Warnings

The successful worker deployment still logged these Discord-side warnings:

- Slash sync failed with `403 Forbidden: Missing Access`.
- The Wreckingball cleanup channel fetch returned `403 Forbidden: Missing Access`.

These are permission/configuration issues in Discord, not Railway build or boot
failures.

## Remaining Manual Acceptance

1. Complete browser Discord OAuth consent through the hosted dashboard.
2. Verify live Discord `/dashboard` returns the hosted dashboard URL.
3. Run `/relay status` in Discord and confirm relay readiness.
4. Send a real Friends-role message in one relay target channel and confirm it
   relays to the other configured target channel.
5. Remove legacy bot `1497752932345708584` after the Discord role hierarchy
   blocker is cleared.

## Memory And Mythos Notes

MemPalace CLI is available through the Windows Python installation, but the
default palace currently reports a Chroma HNSW index load failure. This
handoff was mirrored to the human-readable fallback memory log and mined into a
fresh compact store at
`C:\Users\carme\.mempalace\palace-loki-deploy-summary`.

Verified compact store state:

```text
Wing: loki_the_sun_god
Room: general
Drawers: 186
```

Mythos readiness now passes when invoked through the project runtime
(`utils/mythos_router.run_mythos_action("ready")`), which injects a usable
Node runtime path before launching the npm shim. Do not claim a full Mythos
packet gate from this note alone; `init`/`compile`/`gate` still require the
normal evidence and synthesis flow for the specific run directory.
