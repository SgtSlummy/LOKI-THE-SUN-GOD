# Reset and Restore Plan

Generated: 2026-05-13T22:26:30

## Current checkpoint

- Checkpoint branch: see `.mythos/hermes-runs/latest-checkpoint-branch`.
- Pre-upgrade status: `docs/rollback/pre-upgrade-status-20260513-221207.txt`.
- Pre-upgrade patch: `docs/rollback/pre-upgrade-working-diff-20260513-221207.patch`.
- Environment variable name snapshot: `docs/rollback/pre-upgrade-env-names.txt`.

## Docs-only rollback

Delete added docs/schemas/check/test files from this run and recommit. Existing dirty feature files should not be reset unless intentionally discarding that feature work.

No deployment was performed in this run.
