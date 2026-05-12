# LOKI V8 Hermes Agent Integration

V8 integrates Hermes as a local operator and assembly orchestrator for LOKI after all pending V4-V7 tasks are complete.
No Hermes gateway, cron job, or autonomous background agent is launched by this packet.
Obliteratus and Mythos are advisory evidence inputs only; they do not mutate production code or deploy the bot.

## Global Guards

- Pending tasks required: `all_v4_v7_tasks_complete_first`.
- Production mutation: `blocked`.
- Gateway execution: `blocked_until_operator_approval`.
- Cron execution: `blocked_until_operator_approval`.
- Raw code scope: `docs_tests_loki_research_loki_lab_only`.
- Promotion requires: `V4-V7 artifacts complete`, `reviewed patch or PR`, `passing local gates`, `passing Mythos gate`, `explicit operator approval`.

## V8 - Hermes Agent Operator Integration

Integrate Hermes as a local operator and assembly orchestrator for LOKI after pending V4-V7 tasks are complete, using Obliteratus, Mythos, and Hermes as advisory inputs only.

- Lane: `hermes_agent_operator_integration`.
- Launch policy: `manifest_only_until_operator_approval`.
- Promotion state: `draft_local_only`.
- Deliverables: `Hermes project profile manifest`, `hard-coded bot assembly contract`, `Obliteratus advisory bridge`, `Mythos evidence packet handoff`, `Hermes skill-preload operator workflow`.
- Raw code targets: `loki_research/hermes_integration.py`, `scripts/compile_v8_hermes.py`, `docs/V8_HERMES_INTEGRATION.md`, `.loki_lab/hermes/v8_hermes_manifest.json`.
- Required gates: `all V4-V7 pending tasks complete`, `python -m pytest tests/test_loki_hermes_integration.py`, `python -m pytest tests/test_loki_version_pipeline.py`, `python -m ruff check .`, `python scripts/secret_scan.py`, `mythos-skill gate`.
- Required skills: `hermes-agent`, `test-driven-development`, `systematic-debugging`, `github-pr-workflow`.
- Assembly inputs: `Obliteratus skill context`, `Mythos verifier packet`, `Hermes Agent operator profile`, `LOKI command catalog`, `Activity Bridge room-state tests`.

## Hermes Operator Manifest

- Profile name: `loki-v8-local`.
- Recommended toolsets: `terminal`, `file`, `skills`, `session_search`, `todo`, `delegation`.
- Skill preload: `hermes-agent`, `test-driven-development`, `systematic-debugging`, `github-pr-workflow`.

### Safe Commands

- `doctor`: `hermes doctor`.
- `status`: `hermes status --all`.
- `local_query`: `hermes -s hermes-agent,test-driven-development chat -q 'Assemble LOKI V8 from the checked-in manifest; do not launch gateway, cron, or production mutation.'`.

### Forbidden Commands

- `hermes --yolo`.
- `hermes gateway install`.
- `hermes gateway run`.
- `hermes cron create`.
- `hermes chat -q with production mutation`.

## Acceptance Checklist

- confirm V4-V7 artifacts and tests are complete before V8 assembly.
- load Hermes with project-local skills before issuing any bot assembly prompt.
- use Obliteratus and Mythos as advisory evidence sources, not autonomous mutators.
- compile a hard-coded assembly manifest before touching runtime bot paths.
- require operator approval before gateway, cron, or background agent execution.

## Blocked Actions

- hermes gateway install.
- hermes cron create.
- --yolo autonomous mutation.
- production Discord bot mutation.
- Railway deployment.
- Obliteratus autonomous destructive rewrite.
- Mythos ungated promotion.

## Evidence Artifacts

- `.loki_lab/hermes/v8_hermes_manifest.json`.
- `docs/V8_HERMES_INTEGRATION.md`.
- `tests/test_loki_hermes_integration.py`.
- `docs/V4_V7_EXECUTION_MAP.md`.
