# LOKI Research Index

Updated: 2026-05-14 13:07 UTC

This index records research inputs for autonomous Hermes upgrade runs. Research is advisory until translated into tested local changes and operator-approved production actions.

## Source Classes

| Class | Current sources | Confidence | Action |
|---|---|---:|---|
| Local repo | `bot.py`, `cogs/`, `loki_engine/`, `loki_music/`, `loki_memory/`, `loki_mcp/`, `utils/`, `services/`, `docs/`, `tests/` | High | Primary source of truth |
| CI and tests | `.github/workflows/ci.yml`, `scripts/secret_scan.py`, `tests/` | High | Required gates before commit/push |
| Public GitHub | `SgtSlummy/LOKI-THE-SUN-GOD`, public stars/forks | Medium | Research only; no vendoring without review |
| Hermes doctrine | Hermes Agent skills, Mythos task envelopes, Camelot wing schema | Medium | Normalize run planning and reporting |
| Deployment docs | Railway, Discord, Lavalink/Wavelink, Docker/Nixpacks docs | Medium | Use before infrastructure changes |

## Active Research Threads

1. **Discord natural-language UX** — preserve conversational member-facing behavior; slash sync remains explicit operator fallback.
2. **Admin-gated mutation** — all mutating dashboard, MCP, Discord, deployment, credential, and database operations remain gated.
3. **Hermes direct control** — allow local read, docs, tests, and feature-branch commits; block live posting/deploying without approval.
4. **Music production path** — Lavalink/Wavelink remains the live playback target; local/DCA artifacts are fallback/asset paths.
5. **Memory and Camelot** — durable memory must minimize member data, avoid secrets, and distinguish run reports from long-term facts.
6. **Mythos/Swarm routing** — use normalized task envelopes and sector maps so future agents can resume safely.

## Third-Party Research Guardrails

- Capture URL, fetch timestamp, license status, maintenance status, dependency impact, and security notes before adopting ideas.
- Do not install, vendor, or execute third-party code from stars/forks in production without review.
- Treat unauthenticated public GitHub API data as incomplete for private repos/stars.

## Open Questions

- Which deployment topology should become canonical: single Railway web+worker, split dashboard/bot workers, or container-compose local first?
- Which memory backend should own member-facing Camelot records if LOKI graduates beyond local SQLite?
- Which Hermes bridge operations should be surfaced in Discord, dashboard, desktop app, and MCP respectively?

---

# Research Index

Generated: 2026-05-13T22:26:30

## Current research findings

- LOKI public repo: https://github.com/SgtSlummy/LOKI-THE-SUN-GOD
- Relevant source candidates: MemPalace, ASI-Evolve, swarms, OpenMythos, mythos-router, aadi-labs/evolution, vibecosystem, and mattpocock/skills.

No direct public GitHub match was found for exact `Quantum Roots` or `Camelot memory` naming during this pass. Treat those as local/conceptual adapter contracts unless a canonical source is later identified.

## Next research tasks

Document starred/forked repository shortlist, compare LOKI memory adapter contract against MemPalace patterns, extract Activity Bridge CI requirements, and add confidence/contradiction scoring rules.
