# Reset and Restore Plan

Updated: 2026-05-14 13:07 UTC

## Rollback Points

- Git HEAD before this run: recorded in `docs/rollback/pre-upgrade-head-20260514-130730.txt`.
- Pre-run status: `docs/rollback/pre-upgrade-status-20260514-130730.txt`.
- Pre-run working diff: `docs/rollback/pre-upgrade-working-diff-20260514-130730.patch`.

## Foundation Contract Restore Rules

- Restore natural-language Discord UX first if a change makes slash commands the default member path.
- Restore admin/operator gates first if a change exposes dashboard, database, deployment, credential, or live-posting mutation paths.
- Restore Lavalink music routing first if a change breaks production playback assumptions.
- Restore Hermes autonomous runs to local, advisory, tested, and approval-gated behavior before any live retry.

## Standard Revert

For the most recent local commit:

```bash
git revert HEAD
python -m compileall -q bot.py utils loki_engine loki_music loki_memory loki_mcp loki_activity_bridge scripts tests
python scripts/secret_scan.py
python -m pytest tests -q
```

## Selective Restore Before Commit

```bash
git restore -- path/to/file
git clean -fd -- path/to/untracked-dir-or-file
```

Use selective restore instead of broad reset when unrelated user or agent work may exist.

## Live Deployment Rollback

Autonomous cron runs do not deploy live by default. If an operator deploys a commit, rollback by redeploying the previous verified commit/image and restoring any database backup taken before migration.

## Production Data Rule

Never run destructive database migrations, credential rotations, Discord posting jobs, or Railway restarts from the autonomous loop without explicit approval and a fresh backup/rollback path.

---

Generated: 2026-05-13T22:26:30

## Current checkpoint

- Checkpoint branch: see `.mythos/hermes-runs/latest-checkpoint-branch`.
- Pre-upgrade status: `docs/rollback/pre-upgrade-status-20260513-221207.txt`.
- Pre-upgrade patch: `docs/rollback/pre-upgrade-working-diff-20260513-221207.patch`.
- Environment variable name snapshot: `docs/rollback/pre-upgrade-env-names.txt`.

## Docs-only rollback

Delete added docs/schemas/check/test files from this run and recommit. Existing dirty feature files should not be reset unless intentionally discarding that feature work.

No deployment was performed in this run.
