# LOKI THE SUN GOD Railway Deployment

## Railway Compatibility Status

The repo includes Railway-compatible process, runtime, and environment
configuration. Production deployment was verified from this workspace on
2026-05-13.

Current production services:

| Service | Purpose | Status | Deployment |
| --- | --- | --- | --- |
| `dashboard` | Flask web dashboard | Online | `e15386b4-c08c-4abd-a6d9-7f8bac36a745` |
| `worker` | Discord bot worker | Online | `669aeb2f-2403-49b1-be88-295185ffb52b` |
| `Postgres` | Shared hosted database | Online | `64dbbb9a-8914-456c-8ee9-8e770c964748` |
| `lavalink` | Music playback backend | Online | `020cd7cf-1ea0-4c8c-aa15-0fbdcce5c0b5` |

Current hosted URLs:

```text
Dashboard: https://dashboard-production-9290.up.railway.app
Lavalink:  https://lavalink-production-17ea.up.railway.app
```

Manual acceptance gates still remaining after deploy are:

1. Complete browser Discord OAuth consent through the hosted dashboard.
2. Verify Discord `/dashboard` returns the hosted dashboard URL in the live server.
3. Send a real Friends-role relay message after restart between the actual target channels.

LOKI THE SUN GOD is split into two Railway services that share the same repo and the same Postgres database.

The optional Activity stream bridge adds a third Railway service rooted at
`services/activity-bridge`. Keep it separate from the Python web and worker
services so Discord command ownership remains with LOKI Python.

The Discord Activity client is a static Vite bundle produced from the same
workspace (`services/activity-bridge/client/dist`). Host it separately from the
bridge API/WS process, either as a Railway static service or another static
host. The bridge service does not serve the client bundle.

## Services

Bot worker:

```text
python -m bot
```

Web dashboard:

```text
gunicorn dashboard_app:app --bind 0.0.0.0:$PORT
```

Activity bridge:

```text
npm run start
```

Discord Activity client:

```text
npm run build
# publish services/activity-bridge/client/dist as the static site
```

The repo includes a `Procfile` with both process names for hosts that read Procfiles, but Railway should be configured as two services so the bot worker and dashboard can restart independently.

Do not paste `.env.example` directly into Railway. It is intentionally local-first: localhost URLs, `RELAY_ENABLED=false`, blank `DATABASE_URL`, and placeholder secrets. Use the shared/web/worker variable lists in this document instead.

Always pass the target service explicitly when deploying from the CLI:

```powershell
railway up --service dashboard --environment production --message <message>
railway up --service worker --environment production --message <message>
```

The local Railway link can point at another service such as `lavalink`, so do
not run bare `railway up` from the repo root.

## Shared Environment

Set these on both Railway services:

```text
DISCORD_TOKEN
DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET
DASHBOARD_SECRET_KEY
DATABASE_URL
RELAY_ENABLED=true
RELAY_GUILD_ID
RELAY_FRIENDS_ROLE_NAME=Friends
RELAY_TARGET_CHANNEL_IDS
RELAY_IGNORED_SOURCE_CHANNEL_IDS
RELAY_SENSITIVE_CHANNEL_IDS
```

Current production `worker` relay values:

```text
RELAY_ENABLED=true
RELAY_GUILD_ID=1463393482306486387
RELAY_FRIENDS_ROLE_NAME=Friends
RELAY_TARGET_CHANNEL_IDS=1471988991879549110,1495605587822514287
RELAY_IGNORED_SOURCE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
RELAY_SENSITIVE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
```

The May 13 Ralph/Bartman takeover redeploy verified the worker startup log:

```text
Relay ready guild=1463393482306486387 role=1463393482306486394 targets=The Vibez 101 FM (1471988991879549110) | pirate-radio-tower (1495605587822514287)
```

Set these on the web service:

```text
REDIRECT_URI=https://<railway-domain>/callback
DASHBOARD_PUBLIC_URL=https://<railway-domain>
DASHBOARD_HOST=0.0.0.0
DASHBOARD_DEBUG=false
```

Set `DASHBOARD_PUBLIC_URL=https://<railway-domain>` on the worker service too, so the Discord `/dashboard` command returns the hosted dashboard URL.

Set these for bridge-aware dashboard controls:

```text
ACTIVITY_BRIDGE_URL=https://<activity-bridge-domain>
ACTIVITY_BRIDGE_TOKEN=<shared secret>
ACTIVITY_CLIENT_PUBLIC_URL=https://<activity-client-domain>
ALLOW_ACTIVITY_SIDE_CONTROLS=false
ALLOW_STREAM_START_STOP=false
OBS_WEBSOCKET_URL
OBS_WEBSOCKET_PASSWORD
```

Set `ACTIVITY_BRIDGE_TOKEN` on the Activity bridge service too. Do not put it
in `VITE_*` variables or client-side Activity bundles.

Set these on the Activity bridge service:

```text
ACTIVITY_BRIDGE_TOKEN=<shared secret>
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

Set these on the static Discord Activity client build environment. These are
safe public client values and must not include bot tokens, bridge tokens,
client secrets, Twitch tokens, or OBS passwords:

```text
VITE_DISCORD_CLIENT_ID=<discord application/client id>
VITE_SERVER_ORIGIN=https://<activity-bridge-domain>
VITE_WS_ORIGIN=wss://<activity-bridge-domain>
```

`DATABASE_URL` switches LOKI THE SUN GOD from local SQLite to Postgres. Without it, local/dev keeps using `data/bot.db`.

Relay is stricter than the rest of local/dev: when `RELAY_ENABLED=true`, `DATABASE_URL` is mandatory and must point every relay-capable worker at the same database. Keep `RELAY_ENABLED=false` for local dashboard-only runs or any local process that should not participate in live relay.

LOKI THE SUN GOD also installs an outbound duplicate guard before cogs load. Every bot/webhook send, including DMs and ephemeral responses, is checked against worker-lease ownership, recent channel history when available, and the shared `send_dedupe` table before Discord receives the post. The fingerprint is scoped to the destination channel, so the same source relay message can be delivered to both relay channels while duplicate workers are still blocked from posting it twice in either channel. Relay sends also pass an explicit source-message dedupe key, so the same source message cannot be reposted to the same destination while genuinely new messages with similar text can still relay. On Railway, this depends on both services using the same Postgres `DATABASE_URL`.

The bot worker also claims a hard singleton lease in the shared `worker_leases` table before cogs load. A new Railway worker takes over the lease atomically; stale workers are fenced out at send time and then hard-exit on heartbeat loss. Suppressed sends, lease steals, and fence events are written to `guard_audit`.

## Discord Developer Portal

OAuth2 redirect:

```text
https://<railway-domain>/callback
```

Required OAuth2 scopes:

```text
identify guilds
```

Bot invite scopes:

```text
bot applications.commands
```

Relay requires `Send Messages`, `Embed Links`, and `Attach Files` in the configured target channels.

Relay target channels must not be ticket channels, ticket categories, or any channel/category listed in `RELAY_SENSITIVE_CHANNEL_IDS`; those are skipped for both live relay and `/relay backfill`.

## Preflight

Run before deploying and again after Railway variables are set:

```powershell
py -3 scripts/release_check.py --strict-env
py -3 scripts/db_smoke_test.py --postgres-required
py -3 scripts/mcp_smoke_test.py
```

The 2026-05-13 deployment pass also ran:

```powershell
ruff check .
pytest
cd services\activity-bridge
npm install
npm run typecheck
npm run test:rooms
npm run build
```

## Deployment Process

1. Confirm local gates pass.
2. Confirm Railway authentication with `railway whoami`.
3. Check production service state with
   `railway service list --environment production`.
4. Confirm required variables exist on the target service with
   `railway variable list --service <service> --environment production`.
5. Deploy dashboard first:

```powershell
railway up --service dashboard --environment production --message codex-dashboard
```

6. Poll status and logs:

```powershell
railway service status --service dashboard --environment production --json
railway logs --service dashboard --environment production --latest --deployment --lines 200
```

7. Verify hosted health:

```powershell
curl https://dashboard-production-9290.up.railway.app/healthz
```

8. Deploy worker after dashboard is healthy:

```powershell
railway up --service worker --environment production --message codex-worker
railway service status --service worker --environment production --json
railway logs --service worker --environment production --latest --lines 120
```

9. Confirm worker logs show Discord login and cog load.

If the dashboard crashes at import with `DASHBOARD_SECRET_KEY is required for
hosted LOKI dashboard deployments`, set the dashboard service's server-side
secrets and redeploy. On 2026-05-13 the dashboard service had `DATABASE_URL`
but was missing `DISCORD_TOKEN`, Discord OAuth values, `DASHBOARD_SECRET_KEY`,
`DASHBOARD_PUBLIC_URL`, `DASHBOARD_HOST`, and `DASHBOARD_DEBUG`; those were
set without printing secret values, then redeployed successfully.

After deployment, verify:

- `GET /healthz` returns `ok: true`.
- Discord `/dashboard` returns the hosted dashboard URL.
- Discord `/relay status` shows the Friends-role relay loaded with both target channels.
- A Friends-role message in either target channel relays to the other target channel.
- No PM2/Millhouse relay process is active.

Hosted `/healthz`, Railway dashboard status, and Railway worker status were
verified on 2026-05-13. Browser OAuth consent, live `/dashboard`, and live
Friends-role relay checks remain manual because they require Discord user
interaction in the production server.
