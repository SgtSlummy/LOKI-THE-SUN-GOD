# LOKI THE SUN GOD

LOKI THE SUN GOD is a Discord bot with:

- a `discord.py` bot in [bot.py](/C:/LOKI%20THE%20SUN%20GOD/bot.py) with natural-language Discord UX by default
- a Flask admin dashboard in [dashboard_app.py](/C:/LOKI%20THE%20SUN%20GOD/dashboard_app.py)
- a local desktop control center in [desktop_app.py](/C:/LOKI%20THE%20SUN%20GOD/desktop_app.py)
- a local offline MCP server in [loki_mcp](/C:/LOKI%20THE%20SUN%20GOD/loki_mcp)

The repo is set up for local operation on Windows and includes release checks, packaging helpers, and shared schema bootstrap so the bot, dashboard, and desktop app all agree on the same database layout.

## Quick Start

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy [.env.example](/C:/LOKI%20THE%20SUN%20GOD/.env.example) to `.env` and fill in the required Discord values.

On Windows, you can generate or update `.env` interactively with:

```powershell
.\scripts\setup_env.bat
```

After the file is written, the script can also open the relevant Discord Developer Portal pages for your app.

Also enable the bot's required privileged intents in the Discord Developer Portal:

- `MESSAGE_CONTENT`
- `GUILD_MEMBERS`

3. Run the in-repo release preflight:

```powershell
python .\scripts\release_check.py
```

4. Start the local stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

## Discord UX Policy

LOKI is Discord-first and natural-language-first. By default, runtime slash-command sync stays enabled so members can talk to LOKI in normal language or use `/` commands. Operators can disable slash sync when they want a natural-language-only surface:

```powershell
$env:LOKI_NATURAL_LANGUAGE_ONLY="true"
$env:LOKI_ENABLE_SLASH_SYNC="false"
```

Anyone can ask questions. Admin-level changes remain protected by Discord/admin role checks and dashboard permission gates. Search may use local or online sources only according to the rights granted by admins; rights start with no extra privileges until an admin grants them.

## Required Environment

Required for the bot:

- `DISCORD_TOKEN`

Required for Discord OAuth dashboard sign-in:

- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `REDIRECT_URI`
- `DASHBOARD_SECRET_KEY`

Optional:

- `OWNER_ID`
- `TEST_GUILD_ID`
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

If OAuth is not configured, the dashboard still supports the local LOKI THE SUN GOD bridge on `http://127.0.0.1:5000/dev/connect-loki`.

## Main Scripts

- [scripts/release_check.py](/C:/LOKI%20THE%20SUN%20GOD/scripts/release_check.py): compile, schema, dashboard, desktop, and command-catalog preflight
- [scripts/run_local.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/run_local.ps1): release check plus local startup
- [scripts/smoke_test_local.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/smoke_test_local.ps1): release check plus live HTTP smoke test
- [scripts/build_standalone.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/build_standalone.ps1): release check plus PyInstaller one-file desktop build
- [scripts/build_dashboard_standalone.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/build_dashboard_standalone.ps1): release check plus PyInstaller one-file dashboard build
- [scripts/build_dashboard_raw.py](/C:/LOKI%20THE%20SUN%20GOD/scripts/build_dashboard_raw.py): generate a single-file raw Python dashboard runner at [dashboard_standalone.py](/C:/LOKI%20THE%20SUN%20GOD/dashboard_standalone.py)
- [scripts/run_loki_mcp.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/run_loki_mcp.ps1): launch the offline `stdio` MCP server
- [scripts/mcp_smoke_test.py](/C:/LOKI%20THE%20SUN%20GOD/scripts/mcp_smoke_test.py): seed fixture data and verify MCP tools/resources/prompts
- [scripts/setup_env.bat](/C:/LOKI%20THE%20SUN%20GOD/scripts/setup_env.bat): prompt for required secrets and write `.env`

## Health Surface

- Dashboard health: `http://127.0.0.1:5000/healthz`
- Desktop API: `http://127.0.0.1:7331/api/status`

## Architecture Notes

- SQLite lives at `data/bot.db`
- Shared schema bootstrap lives in [utils/db.py](/C:/LOKI%20THE%20SUN%20GOD/utils/db.py)
- Slash-command metadata is generated from source via [utils/command_catalog.py](/C:/LOKI%20THE%20SUN%20GOD/utils/command_catalog.py)
- Shared bot and dashboard descriptions live in [utils/command_descriptions.py](/C:/LOKI%20THE%20SUN%20GOD/utils/command_descriptions.py)
- Shared desktop and MCP operator reads live in [utils/operator_surface.py](/C:/LOKI%20THE%20SUN%20GOD/utils/operator_surface.py)

## MCP

For local MCP usage and registration details, see [docs/MCP.md](/C:/LOKI%20THE%20SUN%20GOD/docs/MCP.md).

## Release Workflow

For a deployable local validation pass:

```powershell
python .\scripts\release_check.py --strict-env
```

For a packaged desktop build:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_standalone.ps1
```

For a packaged standalone dashboard build:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_dashboard_standalone.ps1
```

For a single-file raw Python dashboard:

```powershell
python .\scripts\build_dashboard_raw.py
python .\dashboard_standalone.py
```
