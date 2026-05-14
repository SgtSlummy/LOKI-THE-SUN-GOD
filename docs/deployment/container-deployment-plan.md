# Container and Deployment Plan

Updated: 2026-05-14 13:07 UTC

This plan prepares deployment improvements without performing live deployment in autonomous cron runs.

## Services

| Service | Candidate runtime | Health check | Rollback |
|---|---|---|---|
| Dashboard web | Railway/Nixpacks or container web process | `/healthz` | Redeploy previous build/commit |
| Discord bot worker | Railway worker/container | logs + Discord ready event | Stop worker and redeploy prior commit |
| Activity Bridge | local/container service | service status/API smoke | Disable bridge env/route |
| Lavalink | managed/container Java service | Lavalink REST/socket health | Revert to previous Lavalink config/image |
| Persistence | SQLite local, future Postgres | schema bootstrap/drift check | DB backup + migration rollback |

## Environment Manifest Rule

Docs may list variable names but never values. Required and optional variables must be mirrored in `.env.example` and deployment docs.

## Pre-Deployment Gate

1. `python -m compileall ...`
2. `python scripts/secret_scan.py`
3. `python -m pytest tests -q`
4. Review `git diff` for secrets/generated noise.
5. Confirm rollback point and deployment target.
6. Obtain explicit operator approval for live deploy/restart.

## Database Drift Plan

Before migrations, generate a schema snapshot from `utils/db.py` bootstrap output, compare it in CI, and document rollback/backup steps. No autonomous destructive migration is allowed.
