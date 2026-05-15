# Hermes Run 2026-05-15 Component IDs

## Scope

- Automation: `loki-the-sun`
- Branch: `codex/hermes-component-id-contracts-20260515`
- Base: `origin/codex/hermes-context-menu-contracts-20260515`
- Upgrade sector: Discord Core Bot Architecture / Testing, QA, CI/CD, and Automated Review

## Research

- Used Context7 for current `discord.py` UI documentation.
- Confirmed persistent views rely on fixed component `custom_id` values and `timeout=None`.
- Confirmed persistent views must be registered on startup so component interactions can be routed after restarts.

## Change

- Added `docs/schemas/discord-component-custom-id-snapshot.json`.
- Added `tests/test_discord_component_custom_id_snapshot.py` to parse persistent Discord UI button IDs without importing Discord modules.
- Added `utils/form_ids.py` and `tests/test_form_custom_ids.py` to cap form keys at 72 characters, preserving Discord's 100-character `custom_id` limit even for 20-digit snowflakes.
- Wired the form-name guard into Discord form commands and dashboard form creation.
- Added the snapshot to foundation-contract validation, testing docs, and Camelot memory index.

## Verification Results

- Passed: `python3 tests/test_discord_component_custom_id_snapshot.py`
- Passed: `python3 tests/test_form_custom_ids.py`
- Passed: `python3 tests/test_discord_context_menu_snapshot.py`
- Passed: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -s -q tests/test_form_custom_ids.py tests/test_discord_component_custom_id_snapshot.py tests/test_discord_context_menu_snapshot.py`
- Passed: static import probe confirmed the component parser discovered 5 buttons without importing `discord`.
- Passed: `python3 -m compileall utils/form_ids.py cogs/forms.py dashboard_app.py tests/test_form_custom_ids.py tests/test_discord_component_custom_id_snapshot.py scripts/check_foundation_contracts.py`
- Passed: `python3 scripts/check_foundation_contracts.py`
- Passed: `python3 scripts/secret_scan.py`
- Passed: `git diff --check`
- Passed: direct Rust Mythos init/compile for `.mythos/hermes-component-id-contracts-20260515`.
- Blocked: `python3 -m ruff check ...` because `/usr/bin/python3` has no `ruff` module installed.
- Partial Mythos: `cmd.exe /c mythos-skill ready` passed. JS `mythos-skill init` was blocked because the Rust `mythos` binary is not on PATH for the wrapper, so direct Rust `mythos` was used for scaffold and compile.

## Upgrade Grade

- Impact: 7/10
- Risk: 2/10
- Complexity: 3/10
- Test Coverage: 8/10
- Maintainability: 8/10
- Performance Effect: 1/10
- Security Effect: 4/10
- Memory/Retrieval Value: 6/10
- Deployment Readiness: 7/10
- Documentation Quality: 7/10
- User Value: 7/10
- Overall Grade: B
- Overall Upgrade Score: 65/100
- Risk Level: Low
- Priority: Soon
- Rollback Difficulty: Low

## Rollback

Remove `utils/form_ids.py`, `tests/test_form_custom_ids.py`, `tests/test_discord_component_custom_id_snapshot.py`, `docs/schemas/discord-component-custom-id-snapshot.json`, and the related form/dashboard/docs/foundation-contract references.
