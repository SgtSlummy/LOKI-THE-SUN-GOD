# Container and Deployment Plan

Generated: 2026-05-13T22:26:30

## Current deployment surfaces

- Root Python app uses Railway/Nixpacks and a Procfile with `web` and `worker` processes.
- Activity Bridge is a separate Node workspace under `services/activity-bridge` with its own Railway config.
- Lavalink has a dedicated Dockerfile under `lavalink/`.

## Safe deployment plan

Treat dashboard web, Discord worker, Activity Bridge, and Lavalink as separate services; verify environment variable names only; run secret scan/tests before deploy; confirm health endpoints/logs; keep rollback command/config for each service; do not deploy from a dirty mixed working tree.

## Rollback checklist

Git branch/commit, previous Railway config, previous environment variable name set, database backup/restore if migrations changed, Activity Bridge previous commit, and Lavalink previous image/config.
