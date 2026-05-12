from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VersionSpec:
    version: str
    title: str
    lane: str
    summary: str
    local_only: bool
    launch_policy: str
    deliverables: tuple[str, ...]
    raw_code_targets: tuple[str, ...]
    required_gates: tuple[str, ...]
    acceptance_checklist: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    evidence_artifacts: tuple[str, ...]
    required_secrets: tuple[str, ...] = ()
    required_env_flags: tuple[str, ...] = ()
    runtime_dependency: str = ""
    python_constraint: str = ""
    promotion_state: str = "draft_local_only"


@dataclass(frozen=True)
class VersionArtifacts:
    json_path: Path
    markdown_path: Path


def next_four_versions() -> tuple[VersionSpec, ...]:
    return (
        VersionSpec(
            version="V4",
            title="Local Research Lab Runner",
            lane="research_lab_runner",
            summary="Assemble local dry-run experiment packets under .loki_lab without mutating production code.",
            local_only=True,
            launch_policy="dry_run_only_until_v2_acceptance",
            deliverables=(
                "version packet compiler",
                "promotion checklist",
                "rollback-required candidate contract",
                "Mythos evidence run",
            ),
            raw_code_targets=(
                "loki_research/version_pipeline.py",
                "scripts/compile_next_versions.py",
                "docs/V4_V7_EXECUTION_MAP.md",
            ),
            required_env_flags=("LOKI_RESEARCH_LAB_ENABLED=true",),
            required_gates=(
                "python -m pytest tests/test_loki_version_pipeline.py",
                "python -m ruff check .",
                "python scripts/secret_scan.py",
                "mythos-skill gate",
            ),
            acceptance_checklist=(
                "write artifacts only under .loki_lab and docs",
                "compile V4-V7 JSON packet deterministically",
                "render matching markdown execution map",
                "include rollback-required promotion contract",
            ),
            blocked_actions=(
                "production code mutation",
                "Railway execution",
                "external experiment launch",
            ),
            evidence_artifacts=(
                ".loki_lab/version_packets/v4_v7_compiled.json",
                "docs/V4_V7_EXECUTION_MAP.md",
                "tests/test_loki_version_pipeline.py",
            ),
        ),
        VersionSpec(
            version="V5",
            title="Hugging Face + Trackio Training Lane",
            lane="hf_trackio_training",
            summary=(
                "Prepare a plan-only LLM training lane with dataset validation "
                "and Trackio monitoring requirements."
            ),
            local_only=True,
            launch_policy="plan_only_until_model_dataset_token_are_set",
            deliverables=(
                "training job readiness schema",
                "dataset validation checklist",
                "Trackio project and Space requirements",
                "Hub push safety checklist",
            ),
            raw_code_targets=("loki_research/version_pipeline.py", "docs/V4_V7_EXECUTION_MAP.md"),
            required_secrets=("HF_TOKEN",),
            required_env_flags=("LOKI_RESEARCH_LAB_ENABLED=true",),
            required_gates=(
                "dataset format validation",
                "Trackio run config review",
                "python -m pytest tests/test_loki_version_pipeline.py",
                "mythos-skill gate",
            ),
            acceptance_checklist=(
                "validate dataset schema before any trainer command",
                "record model and dataset identifiers without downloading private data",
                "review Trackio project and Space configuration",
                "confirm HF_TOKEN exists only in operator environment",
            ),
            blocked_actions=(
                "training job launch",
                "Hub push",
                "Trackio Space mutation",
            ),
            evidence_artifacts=(
                "docs/V4_V7_EXECUTION_MAP.md#v5---hugging-face--trackio-training-lane",
                ".loki_lab/version_packets/v4_v7_compiled.json",
            ),
        ),
        VersionSpec(
            version="V6",
            title="Temporal Activity Orchestration Lane",
            lane="temporal_activity_orchestration",
            summary="Define retryable OBS/Twitch/Activity Bridge orchestration before any worker is launched.",
            local_only=True,
            launch_policy="plan_only_until_temporal_cli_and_worker_config_exist",
            deliverables=(
                "workflow boundary map",
                "activity retry policy checklist",
                "OBS/Twitch idempotency notes",
                "dashboard operator approval checkpoints",
            ),
            raw_code_targets=("loki_research/version_pipeline.py", "docs/V4_V7_EXECUTION_MAP.md"),
            required_env_flags=("ACTIVITY_BRIDGE_URL", "ACTIVITY_BRIDGE_TOKEN"),
            runtime_dependency="Temporal CLI/SDK optional; no worker launch in V6 packet",
            required_gates=(
                "Activity Bridge health smoke",
                "OBS/Twitch disconnected-mode smoke",
                "npm run test:rooms",
                "python -m pytest tests/test_loki_version_pipeline.py",
                "mythos-skill gate",
            ),
            acceptance_checklist=(
                "map workflow boundaries without starting a worker",
                "document retry policy and idempotency keys",
                "verify Activity Bridge room reducer tests",
                "require dashboard operator approval before live controls",
            ),
            blocked_actions=(
                "Temporal worker launch",
                "OBS scene mutation",
                "Twitch stream metadata mutation",
            ),
            evidence_artifacts=(
                "services/activity-bridge/server/tests/rooms.test.ts",
                "docs/V4_V7_EXECUTION_MAP.md#v6---temporal-activity-orchestration-lane",
            ),
        ),
        VersionSpec(
            version="V7",
            title="Cerebrum Agent Adapter Lane",
            lane="cerebrum_agent_adapter",
            summary="Map Cerebrum/AIOS agents into advisory LOKI adapters with kernel and Python-version guards.",
            local_only=True,
            launch_policy="static_adapter_manifest_until_aios_kernel_is_available",
            deliverables=(
                "agent adapter manifest",
                "AIOS kernel availability guard",
                "advisory-only output contract",
                "permission-gated promotion checklist",
            ),
            raw_code_targets=("loki_research/version_pipeline.py", "docs/V4_V7_EXECUTION_MAP.md"),
            required_env_flags=("CEREBRUM_KERNEL_URL",),
            runtime_dependency="AIOS kernel optional; no live agent execution in V7 packet",
            python_constraint="3.10_or_3.11",
            required_gates=(
                "Python 3.10/3.11 environment check",
                "AIOS kernel health check when live mode is requested",
                "python -m pytest tests/test_loki_version_pipeline.py",
                "mythos-skill gate",
            ),
            acceptance_checklist=(
                "emit advisory-only adapter manifest",
                "confirm Python version compatibility before live mode",
                "require AIOS kernel health only when live mode is requested",
                "preserve permission-gated promotion checklist",
            ),
            blocked_actions=(
                "live Cerebrum/AIOS agent execution",
                "kernel mutation",
                "unreviewed autonomous patch application",
            ),
            evidence_artifacts=(
                "docs/V4_V7_EXECUTION_MAP.md#v7---cerebrum-agent-adapter-lane",
                ".loki_lab/version_packets/v4_v7_compiled.json",
            ),
        ),
    )


def compile_next_version_packet() -> dict[str, Any]:
    versions = [asdict(version) for version in next_four_versions()]
    return {
        "sequence": "V4-V7",
        "compiled_from": ("docs/V123_EXECUTION_MAP.md", "docs/SELF_RESEARCH_EXPERIMENTS.md"),
        "external_jobs_launched": False,
        "global_guards": {
            "production_mutation": "blocked",
            "railway_execution": "blocked_for_v3_plus_experiments",
            "raw_code_scope": "docs_tests_loki_research_only",
            "blocked_external_actions": [
                "huggingface_training_job_launch",
                "trackio_space_mutation",
                "temporal_worker_start",
                "obs_or_twitch_live_mutation",
                "cerebrum_or_aios_agent_execution",
            ],
            "promotion_requires": [
                "V2 hosted acceptance",
                "reviewed patch or PR",
                "passing local gates",
                "passing Mythos gate",
            ],
        },
        "versions": versions,
    }


def render_versions_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# LOKI V4/V5/V6/V7 Raw Code Assembly",
        "",
        "This packet compiles the next four local-only versions after the V1/V2/V3 execution map.",
        "No external training jobs, Temporal workers, or Cerebrum kernels are launched by this packet.",
        "",
        "## Global Guards",
        "",
    ]
    guards = packet["global_guards"]
    lines.extend(
        [
            f"- Production mutation: `{guards['production_mutation']}`.",
            f"- Railway execution: `{guards['railway_execution']}`.",
            f"- Raw code scope: `{guards['raw_code_scope']}`.",
            "- Blocked external actions: "
            + ", ".join(f"`{item}`" for item in guards["blocked_external_actions"])
            + ".",
            "- Promotion requires: " + ", ".join(f"`{item}`" for item in guards["promotion_requires"]) + ".",
            "",
            "## Versions",
            "",
        ]
    )

    for version in packet["versions"]:
        lines.extend(
            [
                f"### {version['version']} - {version['title']}",
                "",
                version["summary"],
                "",
                f"- Lane: `{version['lane']}`.",
                f"- Launch policy: `{version['launch_policy']}`.",
                f"- Promotion state: `{version['promotion_state']}`.",
                "- Deliverables: " + ", ".join(f"`{item}`" for item in version["deliverables"]) + ".",
                "- Raw code targets: " + ", ".join(f"`{item}`" for item in version["raw_code_targets"]) + ".",
                "- Required gates: " + ", ".join(f"`{item}`" for item in version["required_gates"]) + ".",
            ]
        )
        if version["required_env_flags"]:
            env_flags = ", ".join(f"`{item}`" for item in version["required_env_flags"])
            lines.append(f"- Required env flags: {env_flags}.")
        if version["required_secrets"]:
            lines.append("- Required secrets: " + ", ".join(f"`{item}`" for item in version["required_secrets"]) + ".")
        if version["runtime_dependency"]:
            lines.append(f"- Runtime dependency: {version['runtime_dependency']}.")
        if version["python_constraint"]:
            lines.append(f"- Python constraint: `{version['python_constraint']}`.")
        lines.extend(
            [
                "",
                "#### Acceptance Checklist",
                "",
                *(f"- {item}." for item in version["acceptance_checklist"]),
                "",
                "#### Blocked Actions",
                "",
                *(f"- {item}." for item in version["blocked_actions"]),
                "",
                "#### Evidence Artifacts",
                "",
                *(f"- `{item}`." for item in version["evidence_artifacts"]),
            ]
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_version_artifacts(root: Path | str = ".") -> VersionArtifacts:
    root_path = Path(root)
    packet = compile_next_version_packet()
    json_path = root_path / ".loki_lab" / "version_packets" / "v4_v7_compiled.json"
    markdown_path = root_path / "docs" / "V4_V7_EXECUTION_MAP.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_versions_markdown(packet), encoding="utf-8")
    return VersionArtifacts(json_path=json_path, markdown_path=markdown_path)
