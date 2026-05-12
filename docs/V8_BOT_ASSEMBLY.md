# LOKI V8 Hard-Coded Bot Assembly

This is the compiled V8 bot assembly contract for the checked-in LOKI runtime modules.
No runtime launch, gateway install, cron job, or Railway deploy is performed by this artifact.
Obliteratus, Mythos, and Hermes remain advisory until explicit operator approval is recorded.

## Assembly State

- Sequence: `V8-bot-assembly`.
- Assembly mode: `hard_coded_local_compile`.
- Runtime entrypoint: `bot.py`.
- External jobs launched: `False`.
- Pending tasks required: `complete`.
- Operator approval required: `True`.

## Required Inputs

- `.loki_lab/hermes/v8_hermes_manifest.json`.
- `docs/V8_HERMES_INTEGRATION.md`.
- `docs/V4_V7_EXECUTION_MAP.md`.
- `Mythos verifier packet`.
- `Obliteratus advisory context`.

## Core Runtime Modules

- `bot.py`.
- `loki_engine/core.py`.
- `loki_npc/persona.py`.
- `loki_music/service.py`.
- `loki_activity_bridge/client.py`.
- `loki_mcp/server.py`.

## Compile Commands

- `python -m compileall bot.py cogs loki_engine loki_npc loki_music loki_activity_bridge loki_mcp loki_research`.

## Verification Commands

- `python -m ruff check .`.
- `python scripts/secret_scan.py`.
- `python -m pytest -q`.
- `npm run test:rooms`.
- `npm run typecheck`.
- `npm run build`.
- `python scripts/release_check.py`.

## Required Runtime Secrets

- `DISCORD_TOKEN`.
- `DISCORD_CLIENT_ID`.
- `DISCORD_CLIENT_SECRET`.
- `DASHBOARD_SECRET_KEY`.

## Blocked Commands

- `hermes --yolo`.
- `hermes gateway install`.
- `hermes cron create`.
- `railway up`.
- `python bot.py`.
- `destructive Obliteratus rewrite`.
- `ungated Mythos promotion`.

## Assembly Steps

- confirm V4-V7 and V8 manifests are checked in.
- compile Python bot modules without starting the Discord client.
- run secret scan and local release gates.
- stage operator-reviewed patch only after Mythos gate passes.
- wait for explicit operator approval before runtime launch or deploy.
