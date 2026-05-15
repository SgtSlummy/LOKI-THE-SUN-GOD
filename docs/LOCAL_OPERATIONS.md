# Local Operations

## Start Everything

## Environment Setup

Use:

```powershell
.\scripts\setup_env.bat
```

This prompts for the required Discord and dashboard secrets, then writes the repo-local `.env` file.

If `.env` already exists, pressing Enter on a prompt keeps the current value.

By default, it also asks whether to open the Discord Developer Portal pages for the configured application so you can verify bot intents, OAuth2 settings, and installation settings right away.

## Start Everything

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

This will:

- run the shared release preflight
- launch the dashboard in the background if it is not already running
- launch the bot in the background if it is not already running
- launch the desktop app in the foreground

## Smoke Test

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_local.ps1
```

This verifies:

- shared release preflight checks
- local desktop control API on `http://127.0.0.1:7331`
- dashboard health on `http://127.0.0.1:5000/healthz`

## Clean Generated Files

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\clean_generated_artifacts.ps1
```

This removes local Python caches, test/build output, runtime logs, MCP smoke
fixtures, and PyInstaller artifacts without touching `.env`, `.venv`,
`data/bot.db`, MemPalace files, or deployment config.

To also remove the Activity Bridge dependency install, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\clean_generated_artifacts.ps1 -IncludeNodeModules
```

To remove ignored Mythos run artifacts as well, add `-IncludeMythos`.

## Mythos Bot Router

LOKI loads `cogs.mythos_router` at startup. The Discord command surface is
owner-only and exposes `/mythos status`, `/mythos ready`, `/mythos init`,
`/mythos add`, `/mythos compile`, and `/mythos gate`.

The router only calls `mythos-skill` with whitelisted argument lists. It never
passes Discord input to a shell. Run slugs are restricted to safe local names
under `.mythos`; set `LOKI_MYTHOS_RUN_SLUG` to change the default run from
`loki-diva-reprocess`.

Use `/mythos add` to record HTTPS GitHub repositories as Mythos source material
for a run. The add route records source metadata in `.mythos/<run>/sources.json`;
it does not clone repositories or execute downloaded code from Discord input.

Mythos readiness still depends on the local toolchain. On Windows, install
Visual Studio Build Tools with the C++ workload so `link.exe` is available
before expecting `/mythos ready` or `/mythos gate` to pass.

## MCP Smoke Test

Use:

```powershell
python .\scripts\mcp_smoke_test.py
```

This seeds a stable fixture database and docs shelf, launches `python -m loki_mcp`, and verifies the MCP tools, resources, and prompts over `stdio`.

## Activity Stream Bridge

The Discord Activity stream bridge is a separate TypeScript service:

```powershell
cd .\services\activity-bridge
npm install
npm run build
npm run start
```

Keep `ENABLE_BRIDGE_DISCORD_BOT=false`; LOKI Python owns Discord commands. Set
`ACTIVITY_BRIDGE_URL` and `ACTIVITY_BRIDGE_TOKEN` in the LOKI dashboard
environment before using the Activity Control bridge panel.

## Strict Release Check

Use:

```powershell
python .\scripts\release_check.py --strict-env
python .\scripts\db_smoke_test.py
```

This is the best pre-ship validation pass because it also fails on missing required environment values.

## Runtime Logs

- Desktop lifecycle log: `desktop_runtime.log`
- Service streaming logs: available in the desktop app's Services tab
- LOKI THE SUN GOD channel relay trace log: `data/relay.log`

## Outbound Duplicate Guard

LOKI THE SUN GOD installs an outbound post guard during bot startup before cogs load. Channel sends, command responses, interaction responses, followups, webhook sends, DMs, and ephemeral responses all pass through the same mechanical check:

- scan the latest 12 messages in the destination for the same LOKI THE SUN GOD/webhook post
- verify this process still owns the current `worker_leases` token
- claim a 10-minute destination-channel fingerprint in the shared `send_dedupe` table
- suppress the send if the worker fence, history check, process cache, or shared database claim says it is unsafe

The default fingerprint is based on the visible post body and scoped to the destination channel. Relay sends add an explicit source-message dedupe key, which lets a new source post relay to both configured target channels while still blocking the same source message from being posted twice into the same relay channel.

If the shared dedupe claim cannot be written, the guarded post is suppressed instead of being sent. Suppressed sends and worker-fence events are written to `guard_audit`.

## Worker Singleton Guard

LOKI THE SUN GOD also enforces one active bot worker before cogs load:

- local startup terminates any other `python -m bot` or `bot.py` process from this same workspace before continuing
- Railway startup atomically takes over the shared `worker_leases` database row
- stale Railway workers are fenced out at send time before Discord receives a post
- a running worker heartbeats the lease every 15 seconds and exits hard if it loses ownership

This guard is only for the bot worker. Dashboard-only local runs should keep using `RELAY_ENABLED=false` and should not start `python -m bot`.

## LOKI THE SUN GOD Relay Troubleshooting

If LOKI THE SUN GOD is not relaying messages between channels, first restart the bot so it reloads `.env`, roles, and target channel IDs:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_all.ps1
```

For a bot-only restart, stop the running `python -m bot` process and start it again from `C:\LOKI THE SUN GOD`.

In Discord, use `/relay status` to inspect the relay and `/dashboard` to open the configured dashboard URL.

To reprocess existing Discord posts after changing relay formatting, use `/relay backfill`. By default it scans the latest 25 messages in each configured relay target channel and relays eligible Friends-role messages to the other configured target channel(s). Use `/relay backfill channel:#channel limit:50` to scan one configured source channel, up to a maximum of 100 messages per run. Backfill keeps the same duplicate guards as live relay, so rerunning it should skip messages that already have a relay source marker in the destination.

Relay requires:

- `RELAY_ENABLED=true`
- `DATABASE_URL` shared by every relay-capable worker; keep `RELAY_ENABLED=false` for local dashboard-only runs
- `ALLOW_LOCAL_SQLITE_RELAY=true` only when this machine should be the only live relay worker and you intentionally want local relay without `DATABASE_URL`
- `RELAY_GUILD_ID` or `TEST_GUILD_ID`
- `RELAY_FRIENDS_ROLE_NAME`
- `RELAY_TARGET_CHANNEL_IDS` or `RELAY_TARGET_CHANNEL_NAMES`
- `RELAY_SENSITIVE_CHANNEL_IDS` for ticket, staff, private, or do-not-relay channel/category IDs
- Discord Developer Portal `MESSAGE_CONTENT` and `GUILD_MEMBERS` intents
- the sender to have the configured Friends role
- LOKI THE SUN GOD to have Send Messages, Embed Links, and Attach Files permissions in relay targets

Relay link previews are rebuilt by LOKI THE SUN GOD instead of reposting raw link text. The bot strips visible URLs, fetches public Open Graph/Twitter metadata with short timeouts and private-network protections, and sends Discord embeds/files for the preview. Private pages, login-walled social posts, and providers that hide image metadata may relay as source context only until a provider-specific adapter is added.

Live relay and `/relay backfill` explicitly skip open ticket channels, the configured ticket category, and any channel or category ID in `RELAY_SENSITIVE_CHANNEL_IDS`. Keep staff, ticket, incident, moderator, and private archive areas on that list even if they are not target channels today.

If `RELAY_ENABLED=true` is set without `DATABASE_URL`, LOKI THE SUN GOD fails startup on purpose. This prevents a local SQLite worker and a hosted Postgres worker from both relaying the same live Discord event.

If you explicitly set `ALLOW_LOCAL_SQLITE_RELAY=true`, LOKI THE SUN GOD will allow local relay startup without `DATABASE_URL`. Use that only when the local machine is the single active relay worker.

## Notes

- Live Discord channel inspection requires `DISCORD_TOKEN`.
- Local-model status reads `OLLAMA_HOST` and defaults to `http://127.0.0.1:11434`.
- The dashboard prefers `qwen2.5-coder:7b`, then `llama3.1:8b`, then `llama3.2:3b`, then the first installed Ollama model.
- Save "Local-first model routing" from AI and Router Settings to write `local-default -> ollama-local/<model>` into 9router.
- Save `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `LOKI_LLM_MODEL` in AI and Router Settings to enable the admin-gated Discord `/ask` command.
- Use the Desktop Dashboards tab "Back up now" button for an immediate local SQLite backup under `data/backups/`.
- Discord OAuth sign-in requires `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `REDIRECT_URI`, and `DASHBOARD_SECRET_KEY`.
