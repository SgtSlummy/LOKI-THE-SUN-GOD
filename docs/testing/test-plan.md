# LOKI Test Plan

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
- Discord context menus: `tests/test_discord_context_menu_snapshot.py`
- Discord persistent UI components: `tests/test_discord_component_custom_id_snapshot.py`
- Discord persistent view startup registration: `tests/test_discord_persistent_view_registration_snapshot.py`
- Form persistent button bounds: `tests/test_form_custom_ids.py`
- Secret safety: `scripts/secret_scan.py`
- JSON schema parse: `scripts/check_foundation_contracts.py`
