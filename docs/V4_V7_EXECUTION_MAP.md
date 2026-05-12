# LOKI V4/V5/V6/V7 Raw Code Assembly

This packet compiles the next four local-only versions after the V1/V2/V3 execution map.
No external training jobs, Temporal workers, or Cerebrum kernels are launched by this packet.

## Global Guards

- Production mutation: `blocked`.
- Railway execution: `blocked_for_v3_plus_experiments`.
- Raw code scope: `docs_tests_loki_research_only`.
- Blocked external actions: `huggingface_training_job_launch`, `trackio_space_mutation`, `temporal_worker_start`, `obs_or_twitch_live_mutation`, `cerebrum_or_aios_agent_execution`.
- Promotion requires: `V2 hosted acceptance`, `reviewed patch or PR`, `passing local gates`, `passing Mythos gate`.

## Versions

### V4 - Local Research Lab Runner

Assemble local dry-run experiment packets under .loki_lab without mutating production code.

- Lane: `research_lab_runner`.
- Launch policy: `dry_run_only_until_v2_acceptance`.
- Promotion state: `draft_local_only`.
- Deliverables: `version packet compiler`, `promotion checklist`, `rollback-required candidate contract`, `Mythos evidence run`.
- Raw code targets: `loki_research/version_pipeline.py`, `scripts/compile_next_versions.py`, `docs/V4_V7_EXECUTION_MAP.md`.
- Required gates: `python -m pytest tests/test_loki_version_pipeline.py`, `python -m ruff check .`, `python scripts/secret_scan.py`, `mythos-skill gate`.
- Required env flags: `LOKI_RESEARCH_LAB_ENABLED=true`.

#### Acceptance Checklist

- write artifacts only under .loki_lab and docs.
- compile V4-V7 JSON packet deterministically.
- render matching markdown execution map.
- include rollback-required promotion contract.

#### Blocked Actions

- production code mutation.
- Railway execution.
- external experiment launch.

#### Evidence Artifacts

- `.loki_lab/version_packets/v4_v7_compiled.json`.
- `docs/V4_V7_EXECUTION_MAP.md`.
- `tests/test_loki_version_pipeline.py`.

### V5 - Hugging Face + Trackio Training Lane

Prepare a plan-only LLM training lane with dataset validation and Trackio monitoring requirements.

- Lane: `hf_trackio_training`.
- Launch policy: `plan_only_until_model_dataset_token_are_set`.
- Promotion state: `draft_local_only`.
- Deliverables: `training job readiness schema`, `dataset validation checklist`, `Trackio project and Space requirements`, `Hub push safety checklist`.
- Raw code targets: `loki_research/version_pipeline.py`, `docs/V4_V7_EXECUTION_MAP.md`.
- Required gates: `dataset format validation`, `Trackio run config review`, `python -m pytest tests/test_loki_version_pipeline.py`, `mythos-skill gate`.
- Required env flags: `LOKI_RESEARCH_LAB_ENABLED=true`.
- Required secrets: `HF_TOKEN`.

#### Acceptance Checklist

- validate dataset schema before any trainer command.
- record model and dataset identifiers without downloading private data.
- review Trackio project and Space configuration.
- confirm HF_TOKEN exists only in operator environment.

#### Blocked Actions

- training job launch.
- Hub push.
- Trackio Space mutation.

#### Evidence Artifacts

- `docs/V4_V7_EXECUTION_MAP.md#v5---hugging-face--trackio-training-lane`.
- `.loki_lab/version_packets/v4_v7_compiled.json`.

### V6 - Temporal Activity Orchestration Lane

Define retryable OBS/Twitch/Activity Bridge orchestration before any worker is launched.

- Lane: `temporal_activity_orchestration`.
- Launch policy: `plan_only_until_temporal_cli_and_worker_config_exist`.
- Promotion state: `draft_local_only`.
- Deliverables: `workflow boundary map`, `activity retry policy checklist`, `OBS/Twitch idempotency notes`, `dashboard operator approval checkpoints`.
- Raw code targets: `loki_research/version_pipeline.py`, `docs/V4_V7_EXECUTION_MAP.md`.
- Required gates: `Activity Bridge health smoke`, `OBS/Twitch disconnected-mode smoke`, `npm run test:rooms`, `python -m pytest tests/test_loki_version_pipeline.py`, `mythos-skill gate`.
- Required env flags: `ACTIVITY_BRIDGE_URL`, `ACTIVITY_BRIDGE_TOKEN`.
- Runtime dependency: Temporal CLI/SDK optional; no worker launch in V6 packet.

#### Acceptance Checklist

- map workflow boundaries without starting a worker.
- document retry policy and idempotency keys.
- verify Activity Bridge room reducer tests.
- require dashboard operator approval before live controls.

#### Blocked Actions

- Temporal worker launch.
- OBS scene mutation.
- Twitch stream metadata mutation.

#### Evidence Artifacts

- `services/activity-bridge/server/tests/rooms.test.ts`.
- `docs/V4_V7_EXECUTION_MAP.md#v6---temporal-activity-orchestration-lane`.

### V7 - Cerebrum Agent Adapter Lane

Map Cerebrum/AIOS agents into advisory LOKI adapters with kernel and Python-version guards.

- Lane: `cerebrum_agent_adapter`.
- Launch policy: `static_adapter_manifest_until_aios_kernel_is_available`.
- Promotion state: `draft_local_only`.
- Deliverables: `agent adapter manifest`, `AIOS kernel availability guard`, `advisory-only output contract`, `permission-gated promotion checklist`.
- Raw code targets: `loki_research/version_pipeline.py`, `docs/V4_V7_EXECUTION_MAP.md`.
- Required gates: `Python 3.10/3.11 environment check`, `AIOS kernel health check when live mode is requested`, `python -m pytest tests/test_loki_version_pipeline.py`, `mythos-skill gate`.
- Required env flags: `CEREBRUM_KERNEL_URL`.
- Runtime dependency: AIOS kernel optional; no live agent execution in V7 packet.
- Python constraint: `3.10_or_3.11`.

#### Acceptance Checklist

- emit advisory-only adapter manifest.
- confirm Python version compatibility before live mode.
- require AIOS kernel health only when live mode is requested.
- preserve permission-gated promotion checklist.

#### Blocked Actions

- live Cerebrum/AIOS agent execution.
- kernel mutation.
- unreviewed autonomous patch application.

#### Evidence Artifacts

- `docs/V4_V7_EXECUTION_MAP.md#v7---cerebrum-agent-adapter-lane`.
- `.loki_lab/version_packets/v4_v7_compiled.json`.
