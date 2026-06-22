# Loki 2.0 Discord Relay Bot

Loki is a Railway-ready Python backend for a Discord relay bot. It relays messages between configured channels, keeps readable attribution, suppresses pings, strips visible raw URLs in clean mode, preserves Discord attachments where size limits allow, and exposes an eight-slot plugin system for future LLM chat, search, autonomous curation, and music work.

## What Ships In The MVP

- Discord gateway bot using `discord.py`.
- `aiohttp` health server at `GET /healthz`.
- SQLite local fallback and PostgreSQL support through `DATABASE_URL`.
- Slash-command admin surface:
  - `/bot status`
  - `/bot plugins`
  - `/bot reload_plugin plugin_name`
  - `/relay routes`
  - `/relay add source_channel destination_channel direction`
  - `/relay remove route_id`
  - `/relay test route_id`
  - `/agent council prompt` when `FAUST_AGI_ENABLED=true`
- LLM chat messaging when `FAUST_AGI_ENABLED=true`:
  - Mention Loki in a server channel: `@Loki your question`
  - DM Loki directly: `your question`
- One-way and bidirectional relay routes.
- Loop prevention through `relay_message_map`.
- Clean relay format:

```text
**Display Name** — from #source-channel
message text
```

- `allowed_mentions` disabled for relay output so users, roles, `@everyone`, and `@here` do not ping.
- Media resolver for Discord files, images, GIFs, stickers, YouTube cards, social fallback cards, direct image/GIF links, and generic metadata where available.

## Discord Setup

In the Discord Developer Portal:

1. Create or open the bot application.
2. Enable the Message Content privileged intent. Loki also enables `intents.message_content = True` in code, but Discord requires the portal switch too.
3. Invite the bot with permissions for slash commands, reading message history, sending messages, attaching files, embedding links, and managing webhooks if `WEBHOOK_RELAY_MODE=true`.
4. Use `DISCORD_GUILD_ID` during development so slash commands sync quickly to one guild.

Discord limitations to know:

- Bot-created embeds cannot manually set `provider` or `video` fields.
- Components V2 media galleries require Discord client/library support and the `IS_COMPONENTS_V2` message flag, which disables traditional content and embeds for that message. Loki detects support and otherwise falls back to embeds/files.
- The maximum message request size is limited by Discord. Loki skips re-uploading attachments that would exceed the configured request limit.
- In `native_unfurl` mode, original links are intentionally included so Discord can create native platform previews.

## Plugin Slots

There are exactly eight standardized slots:

1. `relay_core`
2. `media_resolver`
3. `llm_chat`
4. `server_search`
5. `autonomous_curator`
6. `music`
7. `moderation_audit`
8. `admin_config`

Enabled by default:

- `admin_config`
- `relay_core`
- `media_resolver`
- `moderation_audit`

Stubbed and disabled by default:

- `llm_chat`
- `server_search`
- `autonomous_curator`
- `music`

`MAX_ACTIVE_PLUGINS=8` is enforced. The registry also rejects slot conflicts and missing plugin dependencies.

## Environment

Copy `.env.example` to `.env` for local development. Do not commit real secrets.

Key variables:

- `DISCORD_TOKEN`: required.
- `DISCORD_CLIENT_ID`: application ID.
- `DISCORD_GUILD_ID`: development guild ID for fast command sync.
- `BOT_ADMIN_USER_IDS`: comma-separated Discord user IDs allowed to use admin commands.
- `DATABASE_URL`: PostgreSQL URL on Railway, or `sqlite:///loki-relay.db` locally.
- `OPENAI_API_KEY`: optional, reserved for future LLM plugins.
- `FAUST_AGI_ENABLED`: enables the existing `llm_chat` slot and registers `/agent council`.
- `FAUST_AGI_BASE_URL`: Faust AGI Butter Board Web API base URL, for example `http://localhost:8000`.
- `FAUST_AGI_API_KEY`: optional bearer token if the Faust API is protected by a gateway/proxy.
- `FAUST_AGI_TIMEOUT_SECONDS`: default `300` for slow local/provider runs.
- `FAUST_AGI_ROUTE_MODE`, `FAUST_AGI_PROVIDER`, `FAUST_AGI_EXECUTE`: forwarded to `POST /api/faust/run`.
- `FAUST_AGI_UNPROMPTED_CONTINUATIONS_ENABLED`: opt-in switch for Faust-requested follow-up turns after `/agent council`; default `false`.
- `FAUST_AGI_UNPROMPTED_MAX_TURNS`: hard cap for unprompted continuation turns; default `1`.
- `FAUST_AGI_UNPROMPTED_MAX_DELAY_SECONDS`: hard cap for Faust-requested delay before each continuation; default `30`. Continuations always post with safe mentions and send `execute=false` to Faust.
- `MEDIA_MODE`: `clean`, `button`, or `native_unfurl`.
- `MEDIA_LINK_BUTTONS`: adds an `Open media` button for clean cards when true.
- `WEBHOOK_RELAY_MODE`: sends relays through a per-channel webhook when possible.
- `RELAY_CONFIG_JSON`: optional bootstrap route list.

Example `RELAY_CONFIG_JSON`:

```json
{
  "routes": [
    {
      "guild_id": "123",
      "source_channel_id": "111",
      "destination_channel_id": "222",
      "direction": "bidirectional"
    }
  ]
}
```

## Local Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m bot.main
```

The bot fails fast if `DISCORD_TOKEN` is missing.

Windows helpers:

- `Setup-Loki-Env.bat`: prompts for Discord, bot, database, plugin, and Railway values.
- `Setup-Loki-Railway-Env.bat`: refreshes only Railway token/project/service values.
- `Start-Loki-Local.bat`: starts the bot locally with SQLite fallback, useful when Railway private Postgres is not reachable from Windows.
- `Start-Loki-Guardian.bat`: starts the watchdog/guardian process, which starts Loki with local SQLite fallback and restarts it if the process exits or the `/healthz` endpoint stays unhealthy.
- `Start-Mythos-Loki-Chat.bat`: starts Mythos with the project-local `loki-relay` skill and provider keys loaded from `.env`.

## 24/7 Guardian Watchdog

For a local always-on Windows run, prefer the guardian instead of launching `python -m bot.main` directly:

```powershell
python -m scripts.loki_guardian
```

or double-click `Start-Loki-Guardian.bat`.

The guardian is intentionally a process supervisor, not a second Discord client. Loki still uses `discord.py` for the Discord Gateway lifecycle, including heartbeats, reconnects, Resume/Identify behavior, and REST rate-limit handling. The guardian only restarts the child process when it exits or when Loki's own `GET /healthz` stays unhealthy beyond the configured threshold.

Discord compliance safeguards built into the guardian:

- Does not open a custom Gateway connection or send Discord REST requests, avoiding duplicate clients and manual rate-limit handling.
- Uses Loki's existing `discord.py` client, a community-listed Discord library with built-in Gateway and rate-limit support.
- Requires repeated health failures before restart, so normal transient Gateway disconnects are left for `discord.py` to resume.
- Uses exponential backoff and jitter between restarts to avoid tight reconnect loops.
- Caps restarts to `LOKI_GUARDIAN_MAX_RESTARTS_PER_24H` (default `20`), far below Discord's documented 1000 Identify/day limit.
- Terminates Loki gracefully before force-killing so the bot can close resources cleanly.
- Uses a lock file to avoid two guardian instances starting two bot processes with the same token.
- Redacts token-like command arguments in guardian logs.

Guardian environment variables:

- `LOKI_GUARDIAN_HEALTH_URL`: default `http://127.0.0.1:<HEALTH_PORT>/healthz` when `HEALTH_PORT`/`PORT` is set, otherwise `http://127.0.0.1:8080/healthz`.
- `LOKI_GUARDIAN_CHECK_INTERVAL`: seconds between checks, default `30`.
- `LOKI_GUARDIAN_STARTUP_GRACE`: startup seconds before health checks can trigger restarts, default `90`.
- `LOKI_GUARDIAN_FAILURE_THRESHOLD`: consecutive failed checks before restart, default `6`.
- `LOKI_GUARDIAN_MAX_RESTARTS_PER_24H`: restart cap, default `20`.
- `LOKI_GUARDIAN_BASE_RESTART_DELAY`: first restart delay in seconds, default `30`.
- `LOKI_GUARDIAN_MAX_RESTART_DELAY`: maximum exponential-backoff delay, default `900`.

Logs are written to `logs/loki-guardian.log`. The guardian can also run any explicit command after `--`, for example:

```powershell
python -m scripts.loki_guardian -- python -m bot.main
```

For production hosting, Railway should remain the primary process manager: use its deploy/runtime restart policy and health check (`GET /healthz`). The guardian is for local Windows or a simple VM-style run where there is no platform supervisor.

## Railway Deployment

Railway can use the included `Dockerfile` and `railway.json`.

Start command:

```text
python -m bot.main
```

Health check:

```text
GET /healthz
```

Expected shape:

```json
{
  "ok": true,
  "discord_connected": true,
  "db_connected": true,
  "active_plugins": ["relay_core", "media_resolver", "moderation_audit", "admin_config"]
}
```

Set secrets as Railway variables, not in the repo. If Railway provides `DATABASE_URL`, Loki uses PostgreSQL. Otherwise local development falls back to SQLite.

Windows Railway helpers:

- `Push-Loki-Railway-Variables.bat`: pushes the service variables from `.env` to the configured Railway service without printing secrets.
- `Deploy-Loki-Railway.bat`: submits a detached Railway deploy for the configured service.

## Tests

The test suite covers:

- URL stripping.
- Markdown hyperlink conversion.
- Mention neutralization.
- Disabled allowed mentions.
- Route lookup and bidirectional reversal.
- Loop prevention.
- Discord attachment normalization.
- GIF preservation path.
- YouTube clean-card generation.
- Social fallback-card generation.
- Plugin max-eight enforcement.
- Plugin slot conflict rejection.
- Admin permission checks.
