# Mythos Swarm Architecture

Generated: 2026-05-13T22:26:30

## Purpose

Normalize Hermes/Loki swarm execution through a single Mythos Router contract. Swarms may research, plan, test, and propose patches, but production-affecting actions remain gated.

## Swarm lanes

| Swarm | Writes allowed by default | Notes |
|---|---:|---|
| research | docs/research, .mythos packets | Must cite sources and confidence. |
| github | docs/github-review | Public metadata only unless authenticated access is intentionally configured. |
| architecture | docs/architecture, docs/schemas | No production code rewrites from architecture lane. |
| coding | feature branches only | Must avoid dirty files not owned by task. |
| testing | docs/testing, test reports | Avoid generated output commits unless intentional. |
| qc | docs/qc, run reports | Blocks commits on secrets or unsafe rollback. |
| deployment | docs/deployment | No live deploy without operator approval. |
| memory | docs/memory-palace, Camelot records | No secrets/raw private-channel capture. |
| mutation | .loki_lab only | Dry-run/sandbox only until promoted. |

## Task envelope

Canonical schema: `docs/schemas/mythos-task-envelope.schema.json`.

Every task must include objective, sector, swarm, repo paths, acceptance criteria, rollback plan, status, timestamps, and outputs. Task outputs should be evidence, not claims.

## Write-conflict policy

1. Detect `git status --short` before edits.
2. Avoid files already modified unless the task explicitly owns them.
3. Save rollback artifacts before changing tracked production code.
4. Keep docs/scaffolds separate from functional code commits.
5. Run validation before commit.

## Promotion gates

Docs/research require citations; code requires tests/lint/secret scan/review; database requires backup/migration dry run/restore plan; deployment requires health check and rollback command; autonomy/mutation requires sandbox result, Mythos verifier, and explicit operator approval.
