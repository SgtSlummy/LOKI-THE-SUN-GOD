# Discord Command and Event Ownership

Generated: 2026-05-14

This map is the Sector 1 control surface for LOKI's Discord runtime. It records which process owns Discord commands and gateway events, which files define the command catalog, and which checks must pass before command ownership changes.

## Current Ownership

- Production Discord command owner: the Python bot in `bot.py`.
- Cog manifest: `cogs/__init__.py` exports `COG_MODULES`; `bot.discover_cog_names()` uses that manifest before filesystem fallback.
- Command catalog source: `utils/command_catalog.py` statically parses `cogs/*.py` for prefix, hybrid, hybrid group, slash, and subcommand decorators.
- Operator surfaces: `utils/operator_surface.py`, dashboard API routes, and MCP resources consume the shared command catalog rather than owning Discord commands.
- Activity Bridge boundary: `services/activity-bridge` is a separate TypeScript service; it must not claim production Discord command ownership unless a future migration explicitly changes this document and the Activity Bridge docs.

## Catalog Snapshot

Static parser result from this run:

| Metric | Count |
|---|---:|
| Total catalog entries | 271 |
| Prefix commands | 61 |
| Hybrid commands | 55 |
| Hybrid groups | 23 |
| Slash-only commands | 1 |
| Subcommands | 131 |

Largest command categories in the current catalog are `Fun`, `Roles`, `Loki Music`, `Moderation`, `Automod Ext`, `Autoresponders`, `Config`, `Purge Ext`, `Suggestions`, `Events`, `Forms`, and `Utility`.

## Intent And Startup Contract

The bot currently requests default Discord intents, then enables `members` and `message_content` while disabling `typing`. `bot.log_intent_requirements()` logs the privileged intent names that must be enabled in the Discord Developer Portal.

Startup gates:

- `validate_startup_config()` blocks `RELAY_ENABLED=true` without `DATABASE_URL` unless `ALLOW_LOCAL_SQLITE_RELAY=true`.
- `worker_singleton.claim_worker_lease()` prevents duplicate local bot workers.
- `install_outbound_post_guard()` installs outbound safety controls before cogs load.
- `apply_descriptions_to_bot()` runs after extension loading so command descriptions stay centralized.
- Slash sync is controlled by `LOKI_ENABLE_SLASH_SYNC`; `TEST_GUILD_ID` limits sync to a test guild when set.

## Event Ownership

Gateway event listeners live in Python cogs. Current high-risk event-owner categories include:

- member lifecycle and welcome/goodbye: `cogs/welcome.py`
- moderation, anti-raid, and automod: `cogs/moderation.py`, `cogs/moderation_ext.py`, `cogs/antiraid.py`, `cogs/automod.py`, `cogs/automod_ext.py`
- relay and message propagation: `cogs/relay.py`
- voice activity tracking: `cogs/voice_tracker.py`
- stream, highlights, starboard, sticky, and scheduler automation: corresponding cogs under `cogs/`

Any future service that consumes Discord gateway events must document whether it is read-only, advisory, or an owner for side effects.

## Change Rules

- Do not move command ownership from Python to another service without a focused migration plan, rollback path, and test guild validation.
- Do not enable privileged intents without documenting the feature requiring them.
- Do not add live slash command sync changes without confirming `LOKI_ENABLE_SLASH_SYNC` and `TEST_GUILD_ID` behavior.
- Do not let Activity Bridge, dashboard, MCP, or background agents post Discord messages unless the outbound post guard and permission boundary are explicitly reviewed.
- Keep the command catalog parser as the source of truth for operator and documentation surfaces until a replacement registry is built and tested.

## Verification

Required checks for command/event ownership changes:

- `python -m compileall bot.py cogs utils scripts tests`
- `python scripts/secret_scan.py`
- `python scripts/check_foundation_contracts.py`
- targeted tests for the edited cog or command catalog behavior

Context7 documentation checked for `discord.py` 2.x confirms that extension loading and cog setup are async in 2.x, intents must be explicit, and command error handling should remain centralized for predictable Discord UX.
