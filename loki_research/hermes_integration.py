from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HermesIntegrationSpec:
    version: str
    title: str
    lane: str
    summary: str
    local_only: bool
    launch_policy: str
    deliverables: tuple[str, ...]
    raw_code_targets: tuple[str, ...]
    required_gates: tuple[str, ...]
    required_skills: tuple[str, ...]
    acceptance_checklist: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    evidence_artifacts: tuple[str, ...]
    assembly_inputs: tuple[str, ...]
    promotion_state: str = "draft_local_only"


@dataclass(frozen=True)
class HermesIntegrationArtifacts:
    json_path: Path
    markdown_path: Path


def v8_hermes_integration_spec() -> HermesIntegrationSpec:
    return HermesIntegrationSpec(
        version="V8",
        title="Hermes Agent Operator Integration",
        lane="hermes_agent_operator_integration",
        summary=(
            "Integrate Hermes as a local operator and assembly orchestrator for LOKI after pending V4-V7 "
            "tasks are complete, using Obliteratus, Mythos, and Hermes as advisory inputs only."
        ),
        local_only=True,
        launch_policy="manifest_only_until_operator_approval",
        deliverables=(
            "Hermes project profile manifest",
            "hard-coded bot assembly contract",
            "Obliteratus advisory bridge",
            "Mythos evidence packet handoff",
            "Hermes skill-preload operator workflow",
        ),
        raw_code_targets=(
            "loki_research/hermes_integration.py",
            "scripts/compile_v8_hermes.py",
            "docs/V8_HERMES_INTEGRATION.md",
            ".loki_lab/hermes/v8_hermes_manifest.json",
        ),
        required_gates=(
            "all V4-V7 pending tasks complete",
            "python -m pytest tests/test_loki_hermes_integration.py",
            "python -m pytest tests/test_loki_version_pipeline.py",
            "python -m ruff check .",
            "python scripts/secret_scan.py",
            "mythos-skill gate",
        ),
        required_skills=(
            "hermes-agent",
            "test-driven-development",
            "systematic-debugging",
            "github-pr-workflow",
        ),
        acceptance_checklist=(
            "confirm V4-V7 artifacts and tests are complete before V8 assembly",
            "load Hermes with project-local skills before issuing any bot assembly prompt",
            "use Obliteratus and Mythos as advisory evidence sources, not autonomous mutators",
            "compile a hard-coded assembly manifest before touching runtime bot paths",
            "require operator approval before gateway, cron, or background agent execution",
        ),
        blocked_actions=(
            "hermes gateway install",
            "hermes cron create",
            "--yolo autonomous mutation",
            "production Discord bot mutation",
            "Railway deployment",
            "Obliteratus autonomous destructive rewrite",
            "Mythos ungated promotion",
        ),
        evidence_artifacts=(
            ".loki_lab/hermes/v8_hermes_manifest.json",
            "docs/V8_HERMES_INTEGRATION.md",
            "tests/test_loki_hermes_integration.py",
            "docs/V4_V7_EXECUTION_MAP.md",
        ),
        assembly_inputs=(
            "Obliteratus skill context",
            "Mythos verifier packet",
            "Hermes Agent operator profile",
            "LOKI command catalog",
            "Activity Bridge room-state tests",
        ),
    )


def compile_v8_hermes_packet() -> dict[str, Any]:
    spec = v8_hermes_integration_spec()
    return {
        "sequence": "V8",
        "compiled_from": (
            "docs/V4_V7_EXECUTION_MAP.md",
            "docs/AI_AGENT_WORKFLOW.md",
            "loki_memory/adapters.py",
            "hermes-agent skill",
        ),
        "external_jobs_launched": False,
        "global_guards": {
            "pending_tasks_required": "all_v4_v7_tasks_complete_first",
            "production_mutation": "blocked",
            "gateway_execution": "blocked_until_operator_approval",
            "cron_execution": "blocked_until_operator_approval",
            "raw_code_scope": "docs_tests_loki_research_loki_lab_only",
            "promotion_requires": [
                "V4-V7 artifacts complete",
                "reviewed patch or PR",
                "passing local gates",
                "passing Mythos gate",
                "explicit operator approval",
            ],
        },
        "hermes": {
            "profile_name": "loki-v8-local",
            "recommended_toolsets": [
                "terminal",
                "file",
                "skills",
                "session_search",
                "todo",
                "delegation",
            ],
            "skill_preload": [
                "hermes-agent",
                "test-driven-development",
                "systematic-debugging",
                "github-pr-workflow",
            ],
            "safe_commands": {
                "doctor": "hermes doctor",
                "status": "hermes status --all",
                "local_query": (
                    "hermes -s hermes-agent,test-driven-development "
                    "chat -q 'Assemble LOKI V8 from the checked-in manifest; do not launch gateway, cron, "
                    "or production mutation.'"
                ),
            },
            "forbidden_commands": [
                "hermes --yolo",
                "hermes gateway install",
                "hermes gateway run",
                "hermes cron create",
                "hermes chat -q with production mutation",
            ],
        },
        "versions": [asdict(spec)],
    }


def render_hermes_integration_markdown(packet: dict[str, Any]) -> str:
    spec = packet["versions"][0]
    hermes = packet["hermes"]
    guards = packet["global_guards"]
    lines = [
        "# LOKI V8 Hermes Agent Integration",
        "",
        (
            "V8 integrates Hermes as a local operator and assembly orchestrator for LOKI after all pending V4-V7 "
            "tasks are complete."
        ),
        "No Hermes gateway, cron job, or autonomous background agent is launched by this packet.",
        (
            "Obliteratus and Mythos are advisory evidence inputs only; they do not mutate production code or deploy "
            "the bot."
        ),
        "",
        "## Global Guards",
        "",
        f"- Pending tasks required: `{guards['pending_tasks_required']}`.",
        f"- Production mutation: `{guards['production_mutation']}`.",
        f"- Gateway execution: `{guards['gateway_execution']}`.",
        f"- Cron execution: `{guards['cron_execution']}`.",
        f"- Raw code scope: `{guards['raw_code_scope']}`.",
        "- Promotion requires: " + ", ".join(f"`{item}`" for item in guards["promotion_requires"]) + ".",
        "",
        f"## {spec['version']} - {spec['title']}",
        "",
        spec["summary"],
        "",
        f"- Lane: `{spec['lane']}`.",
        f"- Launch policy: `{spec['launch_policy']}`.",
        f"- Promotion state: `{spec['promotion_state']}`.",
        "- Deliverables: " + ", ".join(f"`{item}`" for item in spec["deliverables"]) + ".",
        "- Raw code targets: " + ", ".join(f"`{item}`" for item in spec["raw_code_targets"]) + ".",
        "- Required gates: " + ", ".join(f"`{item}`" for item in spec["required_gates"]) + ".",
        "- Required skills: " + ", ".join(f"`{item}`" for item in spec["required_skills"]) + ".",
        "- Assembly inputs: " + ", ".join(f"`{item}`" for item in spec["assembly_inputs"]) + ".",
        "",
        "## Hermes Operator Manifest",
        "",
        f"- Profile name: `{hermes['profile_name']}`.",
        "- Recommended toolsets: " + ", ".join(f"`{item}`" for item in hermes["recommended_toolsets"]) + ".",
        "- Skill preload: " + ", ".join(f"`{item}`" for item in hermes["skill_preload"]) + ".",
        "",
        "### Safe Commands",
        "",
    ]
    for name, command in hermes["safe_commands"].items():
        lines.append(f"- `{name}`: `{command}`.")
    lines.extend(["", "### Forbidden Commands", ""])
    lines.extend(f"- `{command}`." for command in hermes["forbidden_commands"])
    lines.extend(["", "## Acceptance Checklist", ""])
    lines.extend(f"- {item}." for item in spec["acceptance_checklist"])
    lines.extend(["", "## Blocked Actions", ""])
    lines.extend(f"- {item}." for item in spec["blocked_actions"])
    lines.extend(["", "## Evidence Artifacts", ""])
    lines.extend(f"- `{item}`." for item in spec["evidence_artifacts"])
    return "\n".join(lines).rstrip() + "\n"


def write_hermes_integration_artifacts(root: Path | str = ".") -> HermesIntegrationArtifacts:
    root_path = Path(root)
    packet = compile_v8_hermes_packet()
    json_path = root_path / ".loki_lab" / "hermes" / "v8_hermes_manifest.json"
    markdown_path = root_path / "docs" / "V8_HERMES_INTEGRATION.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_hermes_integration_markdown(packet), encoding="utf-8")
    return HermesIntegrationArtifacts(json_path=json_path, markdown_path=markdown_path)
