# LOKI: THE SUN GOD Complete Package Manifest

This manifest defines every package target needed to ship the Discord-first LOKI product while keeping live launch, deploy, and autonomous posting blocked until operator approval.

## Package State

- Product name: `LOKI: THE SUN GOD`.
- Completion state: `package_manifest_ready_local_only`.
- External jobs launched: `False`.
- Promotion policy: `operator_review_required_before_any_live_package_launch`.

## Packages

### discord-runtime

- Artifact: `bot.py + cogs + loki_* Python packages`.
- Purpose: Discord bot worker for LOKI natural-language communication.
- Build commands: `python -m compileall bot.py cogs loki_engine loki_npc loki_music loki_activity_bridge loki_mcp loki_research`, `python scripts/release_check.py`.

### discord-app

- Artifact: `Discord Developer Portal application plus slash-command catalog`.
- Purpose: Discord App identity, OAuth, intents, and slash command surface.
- Build commands: `python scripts/release_check.py --strict-env`.

### console-dashboard

- Artifact: `dashboard_app.py and dashboard_standalone.py`.
- Purpose: operator console dashboard with LLM input and sub-agent controls.
- Build commands: `python scripts/build_dashboard_raw.py`, `powershell -ExecutionPolicy Bypass -File ./scripts/build_dashboard_standalone.ps1`.

### desktop-controller

- Artifact: `dist/LOKI-THE-SUN-GOD-Dashboard.exe`.
- Purpose: Windows .exe controller for local operator control and hosted health checks.
- Build commands: `powershell -ExecutionPolicy Bypass -File ./scripts/build_standalone.ps1`.

### activity-bridge

- Artifact: `services/activity-bridge/client/dist`.
- Purpose: Discord Activity-style room state, shared queue, and media watch bridge.
- Build commands: `npm run typecheck`, `npm run build`.

### hermes-camelot-memory

- Artifact: `.loki_lab/hermes/*.json + Camelot memory adapter contract`.
- Purpose: Hermes orchestration, Camelot memory, member summaries, and upgrade evidence.
- Build commands: `python scripts/compile_v8_hermes.py`.

### media-and-crawler-workers

- Artifact: `media/search/crawler worker package contract`.
- Purpose: music/video/image/text/web/game processing, generation, crawling, and posting queues.
- Build commands: `python scripts/release_check.py`.

### local-gpu-workers

- Artifact: `optional local GPU model worker contract`.
- Purpose: optional local model execution routed through desktop/Hermes operator controls.
- Build commands: `python scripts/release_check.py`.

## Final Release Gates

- `python -m ruff check .`.
- `python scripts/secret_scan.py`.
- `python -m pytest -q`.
- `npm run test:rooms`.
- `npm run typecheck`.
- `npm run build`.
- `python scripts/release_check.py`.
- `python scripts/release_check.py --strict-env`.

## Manual Gates

- manual Windows PyInstaller smoke for desktop .exe.
- manual Discord Developer Portal app/intents/OAuth verification.
- manual hosted Railway/web/worker health verification.
- manual Camelot backup/restore verification before live memory promotion.

## Blocked Until Operator Approval

- `python bot.py`.
- `railway up`.
- `hermes gateway install`.
- `hermes cron create`.
- `publishing Discord app commands to a live guild`.
- `autonomous crawler posting to Discord`.
- `shipping desktop .exe without secret scan and release check evidence`.
