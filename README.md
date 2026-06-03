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
- `Start-Mythos-Loki-Chat.bat`: starts Mythos with the project-local `loki-relay` skill and provider keys loaded from `.env`.

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
