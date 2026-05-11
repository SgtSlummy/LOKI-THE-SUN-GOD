# LOKI V1/V2/V3 Execution Map

This map is the release sequence mined from the current LOKI docs, MemPalace
wing `loki-the-sun-god`, fallback memory, and Mythos run history. Treat the
phases as maturity gates, not separate products.

## V1 — Local Stable Release Candidate

- Keep work on the committed `codex/activity-stream-bridge` branch until local
  gates and review artifacts are clean.
- Re-run local gates before each promotion attempt:
  `python -m ruff check .`, `python scripts/secret_scan.py`,
  `TMPDIR=/tmp PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`,
  `python scripts/dashboard_smoke_test.py`, and
  `python scripts/mcp_smoke_test.py`.
- Re-run Activity Bridge checks from `services/activity-bridge`:
  `npm install` or `npm ci`, `npm run typecheck`, and `npm run build`.
- Verify dashboard Activity Control with bridge offline, bridge online, room
  list, room create/control, token failure, missing-token fail-closed behavior,
  and disabled stream start/stop states.
- Re-mine MemPalace after accepted changes and mirror the concise next-action
  queue into the fallback memory file.

## V2 — Hosted Railway And Live Discord

- Create the GitHub remote, push the feature branch, and open a PR before public
  review.
- Authenticate CodeRabbit and resolve all critical or major findings before
  merge.
- Deploy Railway as separate services: LOKI web, LOKI worker, Activity Bridge,
  static Discord Activity client, and shared Postgres.
- Complete live acceptance gates: hosted `/healthz`, Discord OAuth callback,
  Discord `/dashboard`, `/relay status`, Friends-role relay message, Lavalink
  music check, Activity Bridge `/healthz`, and dashboard-to-bridge room/control
  smoke.
- Save deployment URLs, PR link, CodeRabbit result, Mythos run directory, and
  blockers into MemPalace plus fallback memory.

## V3 — Safe Research And Advanced Agents

- Enable self-research only in the local dry-run lab with
  `LOKI_RESEARCH_LAB_ENABLED=true`; production and Railway remain blocked.
- Keep experiment writes under `.loki_lab`, require rollback instructions, and
  promote only through reviewed patches or PRs.
- Add advanced agents after V2 is stable: NPC personality refinement,
  Transformers.js or Hugging Face scoring, Temporal OBS/Twitch retries,
  durable Activity room state, Activity-side host controls, voting, and
  moderation UI.
- Require Mythos gate plus local tests before promoting any V3 experiment.

## Evidence Sources

- `docs/QUALITY_GATES.md`
- `docs/RAILWAY_DEPLOYMENT.md`
- `docs/ACTIVITY_BRIDGE.md`
- `docs/LOKI_IMPLEMENTATION.md`
- `docs/SELF_RESEARCH_EXPERIMENTS.md`
- MemPalace wing `loki-the-sun-god`
- Mythos run `.mythos/loki-v123-execution-map`
