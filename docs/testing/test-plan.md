# LOKI Test Plan

Updated: 2026-05-14 13:07 UTC

## Baseline Gates

Run before commit/push:

```bash
python -m compileall -q bot.py utils loki_engine loki_music loki_memory loki_mcp loki_activity_bridge scripts tests
python scripts/secret_scan.py
python -m pytest tests -q
```

Current observed baseline for this run: `134 passed, 1 warning`; compile and secret scan passed.

## Test Categories

| Category | Coverage target |
|---|---|
| Natural-language UX | LOKI responds to conversational prompts and does not require slash commands by default |
| Admin gates | Mutating actions require Discord/admin/dashboard permissions |
| Link/media safety | URL parsing, SSRF guards, preview sanitization, music metadata extraction |
| Music/Lavalink | Queue state, permission controls, reconnect/degraded behavior where offline-testable |
| MCP | Local tools/resources/prompts stay offline-safe and gated |
| Activity Bridge | Local bridge status, posting gates, retry/degraded behavior |
| Dashboard/Desktop | Health endpoints, operator controls, local bridge surfaces |
| Persistence | Schema bootstrap and future drift checks |
| Deployment | Preflight, env-name manifest, rollback evidence |

## New Regression Added This Run

`tests/test_link_previews.py` now explicitly blocks IPv6 loopback, link-local, unspecified, and `0.0.0.0` preview URLs. This is a test-only SSRF regression guard for Discord relay/media preview inputs.

---

Generated: 2026-05-13T22:26:30

## Baseline commands

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/secret_scan.py
python -m ruff check .
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests
```

If local dependencies are missing, run targeted tests that match the changed scope and document the missing packages.

## Activity Bridge

```bash
cd services/activity-bridge
npm run test:rooms
npm run typecheck
npm run build
```

`npm run build` writes `dist/`; run it only when generated artifacts are acceptable or ignored.

## Current targeted matrix

- Relay preview feature: `tests/test_relay_previews.py`
- Activity room snapshot behavior: Activity Bridge `test:rooms` and `typecheck`
- Foundation docs/schemas: `tests/test_foundation_contracts.py`
- Secret safety: `scripts/secret_scan.py`
- JSON schema parse: `scripts/check_foundation_contracts.py`
