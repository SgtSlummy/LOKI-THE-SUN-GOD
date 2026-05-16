# LOKI/Hermes Swarm Development Plan Import

Generated: 2026-05-16T19:14:08+00:00
Source PDF present: True
Source PDF text hash: `3e76c356e6368323`

## Sources

- `mission-control`: [Mission Control — Hermes Agent Multi-Agent & Orchestration](https://hermesatlas.com/projects/builderz-labs/mission-control) — agent fleet orchestration, telemetry, approval gates
- `swarmclaw`: [SwarmClaw — Hermes Agent Multi-Agent & Orchestration](https://hermesatlas.com/projects/swarmclawai/swarmclaw) — self-hosted swarms, delegation, memory, scheduled tasks
- `opencode-hermes-multiagent`: [OpenCode Hermes Multi-Agent Pipeline](https://hermesatlas.com/projects/1ilkhamov/opencode-hermes-multiagent) — specialist agents, pipeline roles, mandatory quality gates
- `hermes-watchers`: [Hermes Watchers — Poll RSS, JSON APIs, and GitHub with watermark dedup](https://hermes-agent.nousresearch.com/docs/user-guide/skills/optional/devops/devops-watchers) — watch scripts, watermark deduplication, cron-safe output
- `pep8`: [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/) — Python formatting, naming, indentation, wrapping
- `google-pyguide`: [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) — Python linting, pylint use, style discipline
- `loki-backlog`: [LOKI Online AGI / Discord Bot / Music / LLM / Knowledge System Completion Backlog](docs/upgrades/online-agi-discordbot-completion-backlog.md) — current LOKI remaining programming goals and release gates
- `loki-agent-workflow`: [LOKI AI Agent Workflow](docs/AI_AGENT_WORKFLOW.md) — bounded autonomy, agent lanes, memory and safety gates

## Fixed Task List

### research-library-001 — Initialize deterministic source and summary library

- Pass: `pass-1-research-preparation`
- Sector: `knowledge-library`
- Priority/risk: `P0` / `low`
- Depends on: none
- References: `mission-control`, `swarmclaw`, `opencode-hermes-multiagent`, `loki-backlog`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Create a repository-local SQLite library containing source metadata, summaries, task links, env metadata, cron schedules, and grading records.

### research-frameworks-002 — Document orchestration patterns for HermesP and HermesS

- Pass: `pass-1-research-preparation`
- Sector: `mythos-router-and-swarm-orchestration`
- Priority/risk: `P0` / `medium`
- Depends on: `research-library-001`
- References: `mission-control`, `swarmclaw`, `opencode-hermes-multiagent`, `hermes-watchers`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Compare Mission Control, SwarmClaw, OpenCode Hermes, and Hermes watcher patterns, then map them into LOKI's advisory-only autonomy model.

### env-bootstrap-003 — Capture redacted environment and runtime inventory

- Pass: `pass-1-research-preparation`
- Sector: `database-railway-persistence`
- Priority/risk: `P0` / `low`
- Depends on: `research-library-001`
- References: `loki-backlog`, `loki-agent-workflow`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Record Python, OS, package/tool presence, Railway variable names, and service URLs without storing secret values.

### watchers-core-004 — Implement RSS, GitHub, and JSON watcher modules

- Pass: `pass-2-implementation-linking`
- Sector: `plugin-skill-expansion`
- Priority/risk: `P1` / `medium`
- Depends on: `research-frameworks-002`, `env-bootstrap-003`
- References: `hermes-watchers`, `pep8`, `google-pyguide`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Build cron-safe watcher scripts with watermark deduplication, capped state, rate-limit handling, and test fixtures for external APIs.

### crawler-policy-005 — Add safe crawler/recommendation policy and queue

- Pass: `pass-2-implementation-linking`
- Sector: `knowledge-management-and-retrieval`
- Priority/risk: `P4` / `high`
- Depends on: `watchers-core-004`
- References: `loki-backlog`, `loki-agent-workflow`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Define allowlist/denylist controls, source confidence scoring, unsafe-content filters, audit receipts, and operator approval before posting.

### shepherd-router-006 — Build Shepherd Router task queue and heartbeat monitor

- Pass: `pass-2-implementation-linking`
- Sector: `mythos-router-and-swarm-orchestration`
- Priority/risk: `P5` / `high`
- Depends on: `research-frameworks-002`, `env-bootstrap-003`
- References: `mission-control`, `swarmclaw`, `opencode-hermes-multiagent`, `loki-agent-workflow`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Create HermesS persistence for task dispatch, dependencies, heartbeats, restart/reassign decisions, role rotation, audit logs, and cron schedules.

### camelot-profiles-007 — Add dashboard/operator views for Camelot exports and source-aware profiles

- Pass: `pass-2-implementation-linking`
- Sector: `camelot-memory-palace`
- Priority/risk: `P1` / `medium`
- Depends on: `research-library-001`
- References: `loki-backlog`, `loki-agent-workflow`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Finish the remaining P1 surface by displaying deterministic member profiles and Camelot exports while preserving public-memory-only redaction rules.

### activity-heartbeat-008 — Add Activity Bridge room heartbeat, stale cleanup, and persistence contract

- Pass: `pass-2-implementation-linking`
- Sector: `discord-core-bot-architecture`
- Priority/risk: `P2` / `medium`
- Depends on: `env-bootstrap-003`
- References: `loki-backlog`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Complete the remaining Activity Bridge slice with durable room status, stale cleanup semantics, and Discord command failure tests.

### audio-capabilities-009 — Add optional FFmpeg/DCA capability probes and wrappers

- Pass: `pass-2-implementation-linking`
- Sector: `music-and-media-systems`
- Priority/risk: `P3` / `medium`
- Depends on: `env-bootstrap-003`
- References: `loki-backlog`, `pep8`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Implement non-blocking optional audio capability checks, ffmpeg wrappers, and DCA asset helpers that never block Railway startup when dependencies are absent.

### mythos-packet-010 — Expose safe Mythos packet compilation and proposal queue

- Pass: `pass-2-implementation-linking`
- Sector: `agi-agent-reasoning-layer`
- Priority/risk: `P5` / `high`
- Depends on: `shepherd-router-006`
- References: `loki-backlog`, `loki-agent-workflow`, `opencode-hermes-multiagent`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Build a dashboard/operator endpoint for redacted status packets, proposal grading, rollback metadata, and advisory-only approval boundaries.

### evaluation-grading-011 — Grade every slice and retry below-threshold work safely

- Pass: `pass-3-evaluation-grading`
- Sector: `testing-qc-grading-mutation-github-automation`
- Priority/risk: `P0` / `medium`
- Depends on: `watchers-core-004`, `crawler-policy-005`, `shepherd-router-006`, `camelot-profiles-007`, `activity-heartbeat-008`, `audio-capabilities-009`, `mythos-packet-010`
- References: `pep8`, `google-pyguide`, `loki-backlog`
- Gate: `pytest, ruff, release_check, secret_scan, git diff --check`
- Summary: Run local gates, validate source coverage, grade each task across code, tests, docs, security, rollback, memory integration, and user value.

## Cron Schedule Seeds

- `rss-watcher` → `*/15 * * * *` for `watchers-core-004`
- `github-watcher` → `*/15 * * * *` for `watchers-core-004`
- `json-api-watcher` → `*/15 * * * *` for `watchers-core-004`
- `shepherd-heartbeat` → `*/5 * * * *` for `shepherd-router-006`
- `daily-grade-report` → `0 9 * * *` for `evaluation-grading-011`

## Runtime Inventory

```json
{
  "executable": "C:\\Users\\carme\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe",
  "packages": {
    "kernels": "0.14.1",
    "torch": "2.12.0+cpu",
    "transformers": "5.8.1"
  },
  "platform": "Windows-11-10.0.26200-SP0",
  "python": "3.12.10"
}
```

## Safety Notes

- Environment values are redacted; only names/presence are stored.
- External posting and Discord mutation remain operator-approved only.
- Watchers must print only new deduplicated items and preserve watermarks.
- Quality gate target remains release-safe, not self-modifying production code.
