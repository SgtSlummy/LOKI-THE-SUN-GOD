# Mythos Swarm Architecture

Updated: 2026-05-14 13:07 UTC

LOKI uses a Hermes/Mythos operating model for autonomous improvement while keeping production Discord behavior safe.

## Foundation Contract

- Preserve natural-language Discord UX as the default member-facing path.
- Keep admin and operator approval gates in front of mutations, live posting, deployment, and credential changes.
- Preserve the Lavalink music path unless a tested migration plan and rollback path are approved.
- Keep Hermes autonomous work advisory, branch-local, tested, and reversible before any live action.

## Control Plane

```text
Hermes cron/job
  -> sense repo/process/test/deployment state
  -> create Mythos task envelopes
  -> delegate research/testing/QC swarms where safe
  -> write docs/run artifacts
  -> make minimal local changes on a branch
  -> run compile/secret/test gates
  -> commit only verified work
  -> block live deploy/post/mutation until approved
```

## Mythos Task Envelope Schema

Every durable task packet should include:

```yaml
task_id: string
parent_task_id: string | null
sector: discord | agi | music | knowledge | memory | router | plugins | database | deployment | qc
swarm: research | github | docs | architecture | coding | testing | qc | deployment | memory | mutation | media | plugin
priority: integer
status: queued | running | blocked | complete | failed
objective: string
inputs: list
outputs: list
memory_targets: list
repo_paths: list
docs_paths: list
dependencies: list
acceptance_criteria: list
rollback_plan: string
grade: object
created_at: timestamp
updated_at: timestamp
```

## Role Boundaries

| Role | Allowed by default | Blocked without approval |
|---|---|---|
| Research | Read public docs/repos, summarize sources | Install/vendor unreviewed code |
| GitHub Review | Inspect public metadata, compare patterns | Push/merge without green gates |
| Architecture | Draft docs and contracts | Replace core production flows silently |
| Coding | Small local branch changes with tests | Destructive rewrites or secret changes |
| Testing/QC | Compile, secret scan, pytest, smoke tests | Claim live Discord/Railway success without evidence |
| Deployment | Prepare runbooks/config docs | Live deployment/restart without approval |
| Memory | Write redacted Camelot schemas/docs | Store secrets/private member content |
| Mutation | Sandbox experiments | Production mutation or ungated autonomous posting |

## Permission Matrix

| Actor | Read | Mutate config/data | Deploy/post live | Notes |
|---|---|---|---|---|
| Public Discord member | Public bot responses | No | No | Natural language only |
| DJ/music role | Music queue controls as configured | Limited music actions | No infrastructure | Lavalink path preserved |
| Guild admin/manage-guild | Admin bot/dashboard operations | Yes, gated | No infra unless operator | Audit changes |
| Local operator | Full local controls | Yes | Yes | Human approval boundary |
| Hermes autonomous job | Repo/docs/tests/local branch | Minimal tested commits | No | Advisory/control-plane only |
| MCP write-enabled mode | Tool-specific | Explicitly gated | No | Default local/offline posture |

---

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
