# Mythos Swarm Architecture

Updated: 2026-05-14 13:07 UTC

LOKI uses a Hermes/Mythos operating model for autonomous improvement while keeping production Discord behavior safe.

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
