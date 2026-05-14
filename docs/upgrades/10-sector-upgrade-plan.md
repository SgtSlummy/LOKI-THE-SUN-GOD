# LOKI THE SUN GOD — 10-Sector Autonomous Upgrade Plan

Generated: 2026-05-13T22:26:30

This plan is the safe operating map for Hermes/Loki autonomous evolution. It is documentation and scaffold only; production mutation, live Discord posting, deployment, database migration, and credential changes still require explicit operator approval and passing gates.

## Current baseline

- Primary repo: `SgtSlummy/LOKI-THE-SUN-GOD`.
- Runtime surfaces: Discord bot (`bot.py` + `cogs/`), Flask dashboard (`dashboard_app.py`), desktop controller (`desktop_app.py`), MCP server (`loki_mcp/`), shared engine/memory modules, and Activity Bridge (`services/activity-bridge`).
- Persistence: SQLite by default, optional Postgres through `DATABASE_URL`; schema source is currently embedded in `utils/db.py`.
- Governance: existing docs keep research/evolution dry-run/advisory unless explicitly promoted.

## Rollback boundary

- Checkpoint branch: see `.mythos/hermes-runs/latest-checkpoint-branch`.
- Rollback artifacts: `docs/rollback/pre-upgrade-status-20260513-221207.txt`, `docs/rollback/pre-upgrade-working-diff-20260513-221207.patch`, and `docs/rollback/pre-upgrade-env-names.txt`.
- Existing dirty code files must not be swept into docs-only commits unless intentionally reviewed.

## Sector roadmap

| Sector | Scope | Current state | Next safe upgrade | Acceptance gate |
|---|---|---|---|---|
| 1. Discord Core Bot Architecture | Commands, cogs, relay, permissions, rate limits, observability | Mature cog layout with natural-language policy and relay work in progress | Add command/event ownership map and Discord permission matrix | Targeted relay tests + ruff + no secret scan findings |
| 2. AGI / Agent Reasoning Layer | Planning, tool registry, recovery, grading | `loki_research`, Hermes/MCP docs, advisory adapters | Keep planning artifacts as docs and dry-run packets; formalize promotion gates | No live mutation; Mythos packet includes verifier records |
| 3. Music and Media Systems | Lavalink/Wavelink, queue, metadata, playback health | `loki_music`, cogs, Lavalink config, DCA package docs | Add media queue/metadata schema and failure-mode test plan | Non-live unit tests; no media downloads without policy review |
| 4. Knowledge Management and Retrieval | Indexing, source tracking, retrieval evaluation | Docs, research modules, adapter stubs | Add research source map and retrieval evaluation checklist | Sources cited; stale/low-confidence entries labeled |
| 5. Camelot Memory Palace | Wings, provenance, privacy, cross-links | `mempalace.yaml`, `loki_memory/adapters.py`, memory docs | Add wing index and JSON schema for Camelot records | No secrets/raw private data; redaction rules documented |
| 6. Mythos Router and Swarm Orchestration | Task envelope, locks, retries, swarm status | `.mythos/` packets and `cogs/mythos_router.py` | Add canonical task-envelope schema and swarm status contract | JSON schema validates; docs define write-conflict prevention |
| 7. Plugin / Skill Expansion | Skill/plugin registry, sandbox protocol, grading | Hermes skills external to repo; plugin docs are scattered | Add skill/plugin expansion plan with sandbox gates | Candidate installs remain docs-only until reviewed |
| 8. Database, Railway, Persistence | Schema, migrations, backup/restore, indexes | `utils/db.py`, Railway/Nixpacks/Procfile | Add DB schema snapshot plan and backup/restore checklist | No migration without backup + local restore test |
| 9. Containers, Docker, Kubernetes, Deployment | Docker, compose, Railway, health, rollback | Railway configs; Lavalink Dockerfile | Add deployment checklist covering Python web/worker and Activity Bridge service split | Health checks and rollback path documented before deploy |
| 10. Testing, QC, Grading, Mutation, GitHub Automation | CI, secret scan, grading, mutation protocol | CI exists for Python; Activity Bridge checks are local only | Add grading schema, foundation contract check, and CI gap notes | Secret scan + targeted tests + schema validation pass |

## Required gates

Scope boundary, no secrets, rollback path, tests/lint/typecheck or documented blockers, upgrade grade, Camelot wing update for memory changes, deployment impact classification, and operator approval for production deployment/live posting/data migration/credential changes/autonomous mutation.
