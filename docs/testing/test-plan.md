# LOKI Test Plan

Generated: 2026-05-13T22:26:30

## Baseline commands

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/secret_scan.py
python -m ruff check .
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests
```

If local dependencies are missing, run targeted tests that match the changed scope and document the missing packages.

For the 2026-05-22 revival, prefer the rebuilt project venv on Windows:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe scripts\release_check.py --local-db
.\.venv\Scripts\python.exe -m pytest -q
```

## Activity Bridge

```bash
cd services/activity-bridge
npm ci
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
