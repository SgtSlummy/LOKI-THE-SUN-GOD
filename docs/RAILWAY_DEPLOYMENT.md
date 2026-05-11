# LOKI THE SUN GOD Railway Deployment

## Railway Compatibility Status

The repo includes Railway-compatible process, runtime, and environment configuration. No live Railway deployment was created or verified from this workspace during the rebuild.

Manual acceptance gates after deploying are:

1. Complete browser Discord OAuth consent through the hosted dashboard.
2. Verify Discord `/dashboard` returns the hosted dashboard URL in the live server.
3. Send a real Friends-role relay message after restart between the actual target channels.

LOKI THE SUN GOD is split into two Railway services that share the same repo and the same Postgres database.

## Services

Bot worker:

```text
python -m bot
```

Web dashboard:

```text
gunicorn dashboard_app:app --bind 0.0.0.0:$PORT
```

The repo includes a `Procfile` with both process names for hosts that read Procfiles, but Railway should be configured as two services so the bot worker and dashboard can restart independently.

Do not paste `.env.example` directly into Railway. It is intentionally local-first: localhost URLs, `RELAY_ENABLED=false`, blank `DATABASE_URL`, and placeholder secrets. Use the shared/web/worker variable lists in this document instead.

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

Set these on the web service:

```text
REDIRECT_URI=https://<railway-domain>/callback
DASHBOARD_PUBLIC_URL=https://<railway-domain>
DASHBOARD_HOST=0.0.0.0
DASHBOARD_DEBUG=false
```

Set `DASHBOARD_PUBLIC_URL=https://<railway-domain>` on the worker service too, so the Discord `/dashboard` command returns the hosted dashboard URL.

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

After deployment, verify:

- `GET /healthz` returns `ok: true`.
- Discord `/dashboard` returns the hosted dashboard URL.
- Discord `/relay status` shows the Friends-role relay loaded with both target channels.
- A Friends-role message in either target channel relays to the other target channel.
- No PM2/Millhouse relay process is active.

Live hosted evidence is intentionally not recorded here until this repo is deployed with real Railway services and Discord credentials. Browser OAuth consent, live `/dashboard`, and live Friends-role relay checks remain manual because they require Discord user interaction in the production server.
