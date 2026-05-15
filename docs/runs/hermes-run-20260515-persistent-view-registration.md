# Hermes Run 2026-05-15 Persistent View Registration

## Scope

- Automation: `loki-the-sun`
- Branch: `codex/hermes-persistent-view-contracts-20260515-000504`
- Base: `origin/codex/hermes-component-id-contracts-20260515`
- Upgrade sector: Discord Core Bot Architecture / Testing, QA, CI/CD, and Automated Review

## Research

- Used Context7 for current `discord.py` guidance on persistent views.
- Confirmed persistent views require `timeout=None`, stable component `custom_id` values, and startup registration through `bot.add_view`.
- Confirmed application commands still require `CommandTree.sync()` and the `applications.commands` invite scope before they appear in Discord; this run only touched UI component startup contracts.

## Change

- Added `docs/schemas/discord-persistent-view-registration-snapshot.json`.
- Added `tests/test_discord_persistent_view_registration_snapshot.py` to statically verify every persistent view discovered by the component custom-id snapshot is registered with `bot.add_view` during cog startup.
- Added coverage for the fresh `FormPanelView` panel path, where `/form panel` creates a local view instance, registers it, and sends the same view.
- Registered the new snapshot in `scripts/check_foundation_contracts.py`, schema docs, the testing matrix, and the Camelot memory wing index.

## Verification Results

- Passed: `python3 tests/test_discord_persistent_view_registration_snapshot.py`
- Passed: `python3 scripts/check_foundation_contracts.py`
- Passed: `python3 -m json.tool docs/schemas/discord-persistent-view-registration-snapshot.json`
- Passed: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -s -q tests/test_discord_persistent_view_registration_snapshot.py tests/test_discord_component_custom_id_snapshot.py tests/test_form_custom_ids.py tests/test_discord_context_menu_snapshot.py`
- Passed: `python3 scripts/secret_scan.py`
- Passed: `python3 -m compileall tests/test_discord_persistent_view_registration_snapshot.py scripts/check_foundation_contracts.py`
- Passed: static import probe confirmed the persistent-view parser discovers four startup registrations and one runtime panel registration without importing `discord`.
- Passed: `git diff --check`
- Blocked: `python3 -m ruff check tests/test_discord_persistent_view_registration_snapshot.py scripts/check_foundation_contracts.py` because `/usr/bin/python3` has no `ruff` module installed.
- Partial Mythos: `cmd.exe /c mythos-skill ready` passed. No local WSL `mythos` binary was available on PATH for init/compile in this worktree.

## Upgrade Grade

- Impact: 6/10
- Risk: 2/10
- Complexity: 3/10
- Test Coverage: 8/10
- Maintainability: 8/10
- Performance Effect: 1/10
- Security Effect: 3/10
- Memory/Retrieval Value: 6/10
- Deployment Readiness: 7/10
- Documentation Quality: 7/10
- User Value: 6/10
- Overall Grade: B
- Overall Upgrade Score: 61/100
- Risk Level: Low
- Priority: Soon
- Rollback Difficulty: Low

## Rollback

Remove `tests/test_discord_persistent_view_registration_snapshot.py`, `docs/schemas/discord-persistent-view-registration-snapshot.json`, and the related foundation-contract, schema README, testing-plan, and Camelot index references.
