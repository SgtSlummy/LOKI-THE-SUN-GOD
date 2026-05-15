# Skill and Plugin Expansion Plan

Updated: 2026-05-14 13:07 UTC

LOKI can learn from Hermes skills, MCP examples, and third-party agent/plugin projects, but production adoption is gated.

## Intake Rubric

| Field | Required before adoption |
|---|---|
| Source URL | Exact repo/release/doc URL |
| License | Compatible and recorded |
| Maintainer activity | Recent commits/releases/issues reviewed |
| Security risk | Secrets, network, filesystem, eval, subprocess behavior reviewed |
| Dependency impact | New packages, transitive dependencies, platform constraints |
| Sandbox result | Isolated test or spike output |
| LOKI fit | Maps to Discord UX/admin/music/memory/deployment goals |
| Promotion gate | Tests, rollback, docs, operator approval if runtime-affecting |

## Candidate Areas

1. Hermes skill authoring for reusable LOKI operations.
2. MCP examples for `loki_mcp` resources/prompts/tools.
3. Swarm/router concepts for Mythos task envelopes.
4. Memory skills for Camelot indexing and privacy minimization.
5. Deployment plugins only after Railway/container runbooks are stable.

## Blockers

- Do not silently install third-party skills/plugins into production.
- Do not add network-capable plugins without env docs, secret handling, and opt-in controls.
- Do not bypass admin gates through a plugin control surface.

---

Generated: 2026-05-13T22:26:30

## Inventory lanes

Installed Hermes skills are external to this repo; candidate bot plugins include Discord cogs, dashboard modules, MCP tools, and Activity Bridge adapters. Deprecated plugins are unsafe, unmaintained, or incompatible with privacy/deployment gates.

## Sandbox protocol

Record source/license/risk, test in isolated branch/sandbox, add config through `.env.example` names only, add tests/docs, grade with the upgrade schema, and promote only after operator approval for production-impacting integrations.

## High-value candidates

`kyegomez/swarms`, `MemPalace/mempalace`, `GAIR-NLP/ASI-Evolve`, `aadi-labs/evolution`, `vibeeval/vibecosystem`, `thewaltero/mythos-router`, and `kyegomez/OpenMythos`.
