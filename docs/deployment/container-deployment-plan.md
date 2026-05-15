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

---

Generated: 2026-05-13T22:26:30

## Current deployment surfaces

- Root Python app uses Railway/Nixpacks and a Procfile with `web` and `worker` processes.
- Activity Bridge is a separate Node workspace under `services/activity-bridge` with its own Railway config.
- Lavalink has a dedicated Dockerfile under `lavalink/`.

## Safe deployment plan

Treat dashboard web, Discord worker, Activity Bridge, and Lavalink as separate services; verify environment variable names only; run secret scan/tests before deploy; confirm health endpoints/logs; keep rollback command/config for each service; do not deploy from a dirty mixed working tree.

## Rollback checklist

Git branch/commit, previous Railway config, previous environment variable name set, database backup/restore if migrations changed, Activity Bridge previous commit, and Lavalink previous image/config.
