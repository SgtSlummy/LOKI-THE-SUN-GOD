# LOKI THE SUN GOD 50-Gate Release Checklist

## Highest Priority Release Gap

The rebuilt source tree passes local automated gates. Railway production web,
worker, Postgres, and Lavalink services are deployed and online. Hosted
production validation still needs Discord user acceptance for OAuth,
`/dashboard`, and real Friends-role relay behavior.

Manual release items should be handled in this order:

1. Complete browser Discord OAuth consent through the deployed `/callback` URL.
2. Verify live Discord `/dashboard` returns the hosted dashboard URL.
3. Send a real Friends-role post-restart relay message in the actual channels.
4. Resolve Discord `403 Missing Access` warnings for slash sync and the
   configured Wreckingball cleanup channel if those features are required.

Local automated checks cover compile, command catalog generation, dashboard routes, MCP tools, secret scanning, and unit tests. Live Discord behavior remains the post-deploy acceptance gate.

Status meanings:

- `Automated`: covered by `scripts/release_check.py`, `scripts/db_smoke_test.py`, `scripts/mcp_smoke_test.py`, or packaged dashboard verification.
- `Implemented`: code, docs, or config now exists in the repo.
- `Manual`: requires Discord, Railway, or Windows UI interaction.

| Gate | Status | Evidence |
| ---: | --- | --- |
| 1 | Implemented | Repo inventory scoped to `C:\LOKI THE SUN GOD`. |
| 2 | Automated | DB bootstrap/counts covered by release and smoke checks. |
| 3 | Manual | MemPalace health checked with the local CLI before and after mining. |
| 4 | Implemented | `.env` stays local-only; `.env.example` contains placeholders. |
| 5 | Manual | Bot process inspected during restart checks. |
| 6 | Manual | Relay readiness is written to `data/relay.log`. |
| 7 | Automated | OAuth required fields checked by strict env preflight. |
| 8 | Automated | Dashboard route tests cover `/healthz`, `/callback`, `/guilds`, guild pages, mixer/NPC/activity/developer pages, and JSON/CSV exports. |
| 9 | Implemented | PyInstaller build script targets `LOKI-THE-SUN-GOD-Dashboard.exe`. |
| 10 | Implemented | Baseline captured in MemPalace notes and fallback memory. |
| 11 | Automated | Cog compile, catalog, slash signature, and relay checks. |
| 12 | Automated | Dashboard imports and route smoke tests. |
| 13 | Automated | DB layer smoke tests for SQLite and optional Postgres. |
| 14 | Automated | MCP smoke test. |
| 15 | Implemented | Desktop `/api/status` covered by release check. |
| 16 | Implemented | WinUI shell hosts dashboard through WebView2. |
| 17 | Implemented | Build scripts updated for LOKI THE SUN GOD package. |
| 18 | Implemented | Deployment and Railway docs updated. |
| 19 | Implemented | Millhouse relay removed from active desktop service config. |
| 20 | Implemented | Requirements include hosted runtime dependencies. |
| 21 | Implemented | Relay lives in `cogs/relay.py`. |
| 22 | Implemented | `/dashboard` Discord command added. |
| 23 | Implemented | Dashboard health exposes database backend and OAuth state. |
| 24 | Implemented | `DATABASE_URL` Postgres adapter added while keeping SQLite default. |
| 25 | Implemented | `Procfile` and Railway deployment docs added. |
| 26 | Implemented | Session cookies remain HTTP-only and SameSite. |
| 27 | Implemented | Health panels/API include status surfaces. |
| 28 | Implemented | Web and desktop dashboard branding/tokens aligned around LOKI THE SUN GOD. |
| 29 | Implemented | WinUI shell uses `LOKI_DASHBOARD_URL`, hosted URL, or local dashboard. |
| 30 | Implemented | Local ops, deployment, Railway, and quality gate docs updated. |
| 31 | Automated | Python compile check. |
| 32 | Automated | Strict release preflight. |
| 33 | Automated | MCP smoke test. |
| 34 | Automated | Dashboard route, button, form-submit, mixer, NPC, activity, and export smoke tests. |
| 35 | Automated | SQLite migration smoke; Postgres when `DATABASE_URL` is set. |
| 36 | Automated | Relay config/readiness check. |
| 37 | Automated | OAuth callback guard test. |
| 38 | Automated | Desktop API smoke. |
| 39 | Automated | PyInstaller build creates, verifies, and copies desktop EXE. |
| 40 | Manual | WinUI build validates the WebView2 shell. |
| 41 | Implemented | Railway-compatible process, runtime, and environment docs are present for web, worker, Postgres, and Lavalink services. |
| 42 | Implemented | Hosted env checklist documented. |
| 43 | Implemented | Discord redirect checklist documented with hosted callback URL. |
| 44 | Automated | Packaged EXE launches dashboard mode and serves current `/healthz`. |
| 45 | Manual | Browser dashboard visual review. |
| 46 | Manual | Desktop dashboard visual review. |
| 47 | Manual | MemPalace mine/search verification. |
| 48 | Implemented | Final docs pass staged in docs. |
| 49 | Manual | Final risk review after hosted deploy; live Discord checks remain. |
| 50 | Manual | Hosted RC deployment is complete; browser OAuth consent, live `/dashboard`, and live post-restart relay checks remain. |

## Activity Bridge Addendum

The Activity Bridge adds release gates without changing the original 50-gate
baseline:

- `Automated`: TypeScript install, typecheck, and build pass from
  `services/activity-bridge`.
- `Automated`: Python dashboard smoke covers the Activity Control panel and
  disabled bridge states.
- `Automated`: bridge API auth fails closed when `ACTIVITY_BRIDGE_TOKEN` is
  missing and rejects unauthenticated room API calls.
- `Manual`: Discord Activity OAuth and Activity Instance API validation require
  a real hosted Discord application.
- `Manual`: Railway preview must include the separate Activity Bridge API/WS
  service plus a separately hosted static Activity client bundle.
- `Manual`: stream start/stop controls remain disabled until
  `ALLOW_STREAM_START_STOP=true` is set and the confirmation path is reviewed.
