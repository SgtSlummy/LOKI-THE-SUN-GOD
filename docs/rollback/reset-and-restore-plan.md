# Reset and Restore Plan

Updated: 2026-05-14 13:07 UTC

## Rollback Points

- Git HEAD before this run: recorded in `docs/rollback/pre-upgrade-head-20260514-130730.txt`.
- Pre-run status: `docs/rollback/pre-upgrade-status-20260514-130730.txt`.
- Pre-run working diff: `docs/rollback/pre-upgrade-working-diff-20260514-130730.patch`.

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
