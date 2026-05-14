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
    assembly_json_path: Path
    assembly_markdown_path: Path
    final_blueprint_json_path: Path
    final_blueprint_markdown_path: Path
    complete_packages_json_path: Path
    complete_packages_markdown_path: Path
    package_readiness_json_path: Path
    package_readiness_markdown_path: Path


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


def compile_v8_bot_assembly_plan() -> dict[str, Any]:
    return {
        "sequence": "V8-bot-assembly",
        "assembly_mode": "hard_coded_local_compile",
        "runtime_entrypoint": "bot.py",
        "external_jobs_launched": False,
        "pending_tasks_required": "complete",
        "operator_approval_required": True,
        "required_inputs": [
            ".loki_lab/hermes/v8_hermes_manifest.json",
            "docs/V8_HERMES_INTEGRATION.md",
            "docs/V4_V7_EXECUTION_MAP.md",
            "Mythos verifier packet",
            "Obliteratus advisory context",
        ],
        "core_modules": [
            "bot.py",
            "loki_engine/core.py",
            "loki_npc/persona.py",
            "loki_music/service.py",
            "loki_activity_bridge/client.py",
            "loki_mcp/server.py",
        ],
        "compile_commands": [
            (
                "python -m compileall bot.py cogs loki_engine loki_npc loki_music loki_activity_bridge "
                "loki_mcp loki_research"
            ),
        ],
        "verification_commands": [
            "python -m ruff check .",
            "python scripts/secret_scan.py",
            "python -m pytest -q",
            "npm run test:rooms",
            "npm run typecheck",
            "npm run build",
            "python scripts/release_check.py",
        ],
        "required_runtime_secrets": [
            "DISCORD_TOKEN",
            "DISCORD_CLIENT_ID",
            "DISCORD_CLIENT_SECRET",
            "DASHBOARD_SECRET_KEY",
        ],
        "blocked_commands": [
            "hermes --yolo",
            "hermes gateway install",
            "hermes cron create",
            "railway up",
            "python bot.py",
            "destructive Obliteratus rewrite",
            "ungated Mythos promotion",
        ],
        "assembly_steps": [
            "confirm V4-V7 and V8 manifests are checked in",
            "compile Python bot modules without starting the Discord client",
            "run secret scan and local release gates",
            "stage operator-reviewed patch only after Mythos gate passes",
            "wait for explicit operator approval before runtime launch or deploy",
        ],
    }


def render_v8_bot_assembly_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# LOKI V8 Hard-Coded Bot Assembly",
        "",
        "This is the compiled V8 bot assembly contract for the checked-in LOKI runtime modules.",
        "No runtime launch, gateway install, cron job, or Railway deploy is performed by this artifact.",
        "Obliteratus, Mythos, and Hermes remain advisory until explicit operator approval is recorded.",
        "",
        "## Assembly State",
        "",
        f"- Sequence: `{plan['sequence']}`.",
        f"- Assembly mode: `{plan['assembly_mode']}`.",
        f"- Runtime entrypoint: `{plan['runtime_entrypoint']}`.",
        f"- External jobs launched: `{plan['external_jobs_launched']}`.",
        f"- Pending tasks required: `{plan['pending_tasks_required']}`.",
        f"- Operator approval required: `{plan['operator_approval_required']}`.",
        "",
        "## Required Inputs",
        "",
        *(f"- `{item}`." for item in plan["required_inputs"]),
        "",
        "## Core Runtime Modules",
        "",
        *(f"- `{item}`." for item in plan["core_modules"]),
        "",
        "## Compile Commands",
        "",
        *(f"- `{item}`." for item in plan["compile_commands"]),
        "",
        "## Verification Commands",
        "",
        *(f"- `{item}`." for item in plan["verification_commands"]),
        "",
        "## Required Runtime Secrets",
        "",
        *(f"- `{item}`." for item in plan["required_runtime_secrets"]),
        "",
        "## Blocked Commands",
        "",
        *(f"- `{item}`." for item in plan["blocked_commands"]),
        "",
        "## Assembly Steps",
        "",
        *(f"- {item}." for item in plan["assembly_steps"]),
    ]
    return "\n".join(lines).rstrip() + "\n"


def compile_loki_final_product_blueprint() -> dict[str, Any]:
    return {
        "product_name": "LOKI: THE SUN GOD",
        "primary_interface": "Discord",
        "product_type": "AGI-style Discord bot and app",
        "deployment_target": "fully_hosted_online_with_optional_local_gpu_workers",
        "surfaces": [
            "Discord bot",
            "Discord app",
            "console dashboard",
            "desktop .exe controller",
            "Hermes operator profile",
        ],
        "discord_experience": {
            "capabilities": [
                "natural language Discord control",
                "admin-guided behavior tuning",
                "community-aware recommendations",
                "member summary requests",
                "safe autonomous content posting",
            ],
            "communication_mode": "Discord-first natural language",
        },
        "console_dashboard": {
            "capabilities": [
                "interactable LLM input",
                "sub-agent control",
                "component and subcomponent status panels",
                "Discord app telemetry",
                "manual crawl/search controls",
                "media generation queue controls",
            ],
        },
        "desktop_controller": {
            "package": "Windows .exe",
            "capabilities": [
                "local operator controls",
                "optional local GPU worker routing",
                "hosted bot health checks",
                "manual approval queue",
            ],
        },
        "models": {
            "training_sources": [
                "Discord content history",
                "admin-provided instructions",
                "Camelot memory summaries",
                "approved web research corpus",
            ],
            "deployment_modes": [
                "hosted API model",
                "local GPU model worker optional",
                "Hermes delegated sub-agent model",
            ],
        },
        "media": {
            "modalities": ["music", "video", "image", "text", "websites", "games"],
            "operations": ["input", "processing", "generation", "search", "recommendation", "posting"],
        },
        "memory": {
            "system_of_record": "Camelot",
            "member_memory": [
                "posted content history per Discord member",
                "admin-provided member notes",
                "summaries and askable profiles per member",
                "sub-agent maintained evidence trails",
            ],
        },
        "autonomy": {
            "web_crawling": "manual_and_autonomous_full_web_crawl_with_operator_policy",
            "community_actions": [
                "search and find content autonomously",
                "search and find content manually",
                "post related ideas/pictures/websites/games to Discord",
                "learn what each Discord member likes from posted content",
            ],
            "upgrade_loop": [
                "continue autonomous research/upgrade/evolution loop",
                "generate operator-reviewed improvement proposals",
                "run local gates before every self-upgrade",
            ],
        },
        "components": [
            "Hermes orchestration",
            "Obliteratus advisory rewrite context",
            "Mythos verifier gate",
            "Camelot memory",
            "Activity Bridge",
            "Discord MCP surface",
            "media processing/generation workers",
            "web crawler/search workers",
        ],
        "delivery_phases": [
            {"id": "P0", "title": "Foundation and hosted Discord core"},
            {"id": "P1", "title": "Console dashboard and admin LLM controls"},
            {"id": "P2", "title": "Camelot memory and member intelligence"},
            {"id": "P3", "title": "Media processing and generation"},
            {"id": "P4", "title": "Autonomous search, crawl, and recommendation"},
            {"id": "P5", "title": "Desktop .exe and local GPU workers"},
            {"id": "P6", "title": "Autonomous evolution with operator governance"},
        ],
        "safety_gates": [
            "admin approval for posting/deploying/evolving",
            "secret scan before every release",
            "no raw secret or token memory retention",
            "operator review for autonomous crawler policy changes",
            "Mythos gate before upgrade promotion",
        ],
        "acceptance_tests": [
            "Discord natural language member summary test",
            "Camelot memory export/import test",
            "console dashboard sub-agent control smoke test",
            "desktop .exe health-control smoke test",
            "media generation queue safety test",
            "autonomous crawler allowlist/policy test",
            "hosted Discord app end-to-end smoke test",
        ],
    }


def render_loki_final_product_markdown(blueprint: dict[str, Any]) -> str:
    lines = [
        "# LOKI: THE SUN GOD Final Product Blueprint",
        "",
        "Communication is Discord-first. LOKI is the AGI-style Discord bot, Discord app, dashboard, "
        "desktop controller, and Hermes/Camelot-backed autonomous operator system for the community.",
        "",
        "## Identity",
        "",
        f"- Product name: `{blueprint['product_name']}`.",
        f"- Primary interface: `{blueprint['primary_interface']}`.",
        f"- Product type: `{blueprint['product_type']}`.",
        f"- Deployment target: `{blueprint['deployment_target']}`.",
        "",
        "## Surfaces",
        "",
        *(f"- {surface}." for surface in blueprint["surfaces"]),
        "",
        "## Discord Experience",
        "",
        *(f"- {item}." for item in blueprint["discord_experience"]["capabilities"]),
        "",
        "## Console Dashboard",
        "",
        *(f"- {item}." for item in blueprint["console_dashboard"]["capabilities"]),
        "",
        "## Memory",
        "",
        f"- System of record: `{blueprint['memory']['system_of_record']}`.",
        *(f"- {item}." for item in blueprint["memory"]["member_memory"]),
        "",
        "## Media and Models",
        "",
        "- Modalities: " + ", ".join(f"`{item}`" for item in blueprint["media"]["modalities"]) + ".",
        "- Operations: " + ", ".join(f"`{item}`" for item in blueprint["media"]["operations"]) + ".",
        "- Model deployment modes: "
        + ", ".join(f"`{item}`" for item in blueprint["models"]["deployment_modes"])
        + ".",
        "",
        "## Autonomy",
        "",
        f"- Web crawling: `{blueprint['autonomy']['web_crawling']}`.",
        *(f"- {item}." for item in blueprint["autonomy"]["community_actions"]),
        *(f"- {item}." for item in blueprint["autonomy"]["upgrade_loop"]),
        "",
        "## Delivery Phases",
        "",
        *(f"- `{phase['id']}`: {phase['title']}." for phase in blueprint["delivery_phases"]),
        "",
        "## Safety Gates",
        "",
        *(f"- {gate}." for gate in blueprint["safety_gates"]),
        "",
        "## Acceptance Tests",
        "",
        *(f"- {test}." for test in blueprint["acceptance_tests"]),
    ]
    return "\n".join(lines).rstrip() + "\n"


def compile_loki_complete_package_manifest() -> dict[str, Any]:
    return {
        "product_name": "LOKI: THE SUN GOD",
        "completion_state": "package_manifest_ready_local_only",
        "external_jobs_launched": False,
        "promotion_policy": "operator_review_required_before_any_live_package_launch",
        "packages": [
            {
                "id": "discord-runtime",
                "artifact": "bot.py + cogs + loki_* Python packages",
                "purpose": "Discord bot worker for LOKI natural-language communication",
                "build_commands": [
                    (
                        "python -m compileall bot.py cogs loki_engine loki_npc loki_music loki_activity_bridge "
                        "loki_mcp loki_research"
                    ),
                    "python scripts/release_check.py",
                ],
            },
            {
                "id": "discord-app",
                "artifact": "Discord Developer Portal application plus slash-command catalog",
                "purpose": "Discord App identity, OAuth, intents, and slash command surface",
                "build_commands": ["python scripts/release_check.py --strict-env"],
            },
            {
                "id": "console-dashboard",
                "artifact": "dashboard_app.py and dashboard_standalone.py",
                "purpose": "operator console dashboard with LLM input and sub-agent controls",
                "build_commands": [
                    "python scripts/build_dashboard_raw.py",
                    "powershell -ExecutionPolicy Bypass -File ./scripts/build_dashboard_standalone.ps1",
                ],
            },
            {
                "id": "desktop-controller",
                "artifact": "dist/LOKI-THE-SUN-GOD-Dashboard.exe",
                "purpose": "Windows .exe controller for local operator control and hosted health checks",
                "build_commands": [
                    "powershell -ExecutionPolicy Bypass -File ./scripts/build_standalone.ps1",
                ],
            },
            {
                "id": "activity-bridge",
                "artifact": "services/activity-bridge/client/dist",
                "purpose": "Discord Activity-style room state, shared queue, and media watch bridge",
                "build_commands": ["npm run typecheck", "npm run build"],
            },
            {
                "id": "hermes-camelot-memory",
                "artifact": ".loki_lab/hermes/*.json + Camelot memory adapter contract",
                "purpose": "Hermes orchestration, Camelot memory, member summaries, and upgrade evidence",
                "build_commands": ["python scripts/compile_v8_hermes.py"],
            },
            {
                "id": "media-and-crawler-workers",
                "artifact": "media/search/crawler worker package contract",
                "purpose": "music/video/image/text/web/game processing, generation, crawling, and posting queues",
                "build_commands": ["python scripts/release_check.py"],
            },
            {
                "id": "local-gpu-workers",
                "artifact": "optional local GPU model worker contract",
                "purpose": "optional local model execution routed through desktop/Hermes operator controls",
                "build_commands": ["python scripts/release_check.py"],
            },
        ],
        "final_release_gates": [
            "python -m ruff check .",
            "python scripts/secret_scan.py",
            "python -m pytest -q",
            "npm run test:rooms",
            "npm run typecheck",
            "npm run build",
            "python scripts/release_check.py",
            "python scripts/release_check.py --strict-env",
        ],
        "manual_gates": [
            "manual Windows PyInstaller smoke for desktop .exe",
            "manual Discord Developer Portal app/intents/OAuth verification",
            "manual hosted Railway/web/worker health verification",
            "manual Camelot backup/restore verification before live memory promotion",
        ],
        "blocked_until_operator_approval": [
            "python bot.py",
            "railway up",
            "hermes gateway install",
            "hermes cron create",
            "publishing Discord app commands to a live guild",
            "autonomous crawler posting to Discord",
            "shipping desktop .exe without secret scan and release check evidence",
        ],
    }


def render_loki_complete_package_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# LOKI: THE SUN GOD Complete Package Manifest",
        "",
        "This manifest defines every package target needed to ship the Discord-first LOKI product while keeping "
        "live launch, deploy, and autonomous posting blocked until operator approval.",
        "",
        "## Package State",
        "",
        f"- Product name: `{manifest['product_name']}`.",
        f"- Completion state: `{manifest['completion_state']}`.",
        f"- External jobs launched: `{manifest['external_jobs_launched']}`.",
        f"- Promotion policy: `{manifest['promotion_policy']}`.",
        "",
        "## Packages",
        "",
    ]
    for package in manifest["packages"]:
        lines.extend(
            [
                f"### {package['id']}",
                "",
                f"- Artifact: `{package['artifact']}`.",
                f"- Purpose: {package['purpose']}.",
                "- Build commands: " + ", ".join(f"`{command}`" for command in package["build_commands"]) + ".",
                "",
            ]
        )
    lines.extend(["## Final Release Gates", ""])
    lines.extend(f"- `{gate}`." for gate in manifest["final_release_gates"])
    lines.extend(["", "## Manual Gates", ""])
    lines.extend(f"- {gate}." for gate in manifest["manual_gates"])
    lines.extend(["", "## Blocked Until Operator Approval", ""])
    lines.extend(f"- `{command}`." for command in manifest["blocked_until_operator_approval"])
    return "\n".join(lines).rstrip() + "\n"


def compile_loki_package_readiness_report() -> dict[str, Any]:
    manifest = compile_loki_complete_package_manifest()
    evidence_by_package = {
        "discord-runtime": ["bot.py", "cogs/", "python scripts/release_check.py"],
        "discord-app": ["utils/command_catalog.py", "python scripts/release_check.py --strict-env"],
        "console-dashboard": [
            "dashboard_app.py",
            "dashboard_standalone.py",
            "scripts/build_dashboard_raw.py",
        ],
        "desktop-controller": [
            "LokiDashboard.spec",
            "scripts/build_standalone.ps1",
            "manual Windows PyInstaller smoke for desktop .exe",
        ],
        "activity-bridge": [
            "services/activity-bridge/client/dist",
            "npm run test:rooms",
            "npm run typecheck",
            "npm run build",
        ],
        "hermes-camelot-memory": [
            ".loki_lab/hermes/v8_hermes_manifest.json",
            ".loki_lab/hermes/loki_final_product_blueprint.json",
            ".loki_lab/hermes/loki_complete_packages.json",
        ],
        "media-and-crawler-workers": [
            "media/search/crawler worker package contract",
            "manual crawler allowlist/policy verification",
        ],
        "local-gpu-workers": [
            "optional local GPU model worker contract",
            "manual GPU host smoke required when enabled",
        ],
    }
    status_by_package = {
        "discord-runtime": "automated_ready",
        "discord-app": "manual_gate_required",
        "console-dashboard": "automated_ready",
        "desktop-controller": "manual_gate_required",
        "activity-bridge": "automated_ready",
        "hermes-camelot-memory": "automated_ready",
        "media-and-crawler-workers": "contract_ready",
        "local-gpu-workers": "contract_ready",
    }
    readiness_rows = [
        {
            "package_id": package["id"],
            "status": status_by_package[package["id"]],
            "artifact": package["artifact"],
            "evidence": evidence_by_package[package["id"]],
        }
        for package in manifest["packages"]
    ]
    status_counts = {
        status: sum(1 for row in readiness_rows if row["status"] == status)
        for status in ("automated_ready", "contract_ready", "manual_gate_required")
    }
    return {
        "product_name": manifest["product_name"],
        "readiness_state": "local_package_evidence_compiled",
        "external_jobs_launched": False,
        "summary": {
            "total_packages": len(readiness_rows),
            "automated_ready": status_counts["automated_ready"],
            "contract_ready": status_counts["contract_ready"],
            "manual_gate_required": status_counts["manual_gate_required"],
        },
        "matrix": readiness_rows,
        "still_requires_operator_approval": manifest["blocked_until_operator_approval"],
        "next_operator_actions": [
            "provide production secrets outside git",
            "run strict environment release check on the deployment host",
            "smoke-test desktop .exe on Windows after PyInstaller build",
            "verify Discord Developer Portal intents, OAuth redirect, and command publication target",
            "approve or reject live bot launch, crawler posting, and hosted deploy separately",
        ],
    }


def render_loki_package_readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# LOKI: THE SUN GOD Package Readiness Report",
        "",
        "This report converts the complete package manifest into a local evidence matrix. It does not launch the "
        "bot, deploy hosting, install Hermes gateway/cron, or publish autonomous crawler output.",
        "",
        "## Summary",
        "",
        f"- Product name: `{report['product_name']}`.",
        f"- Readiness state: `{report['readiness_state']}`.",
        f"- External jobs launched: `{report['external_jobs_launched']}`.",
        f"- Total packages: `{report['summary']['total_packages']}`.",
        f"- Automated ready: `{report['summary']['automated_ready']}`.",
        f"- Contract ready: `{report['summary']['contract_ready']}`.",
        f"- Manual gate required: `{report['summary']['manual_gate_required']}`.",
        "",
        "## Readiness Matrix",
        "",
    ]
    for row in report["matrix"]:
        lines.extend(
            [
                f"### {row['package_id']}",
                "",
                f"- Status: `{row['status']}`.",
                f"- Artifact: `{row['artifact']}`.",
                "- Evidence: " + ", ".join(f"`{item}`" for item in row["evidence"]) + ".",
                "",
            ]
        )
    lines.extend(["## Still Requires Operator Approval", ""])
    lines.extend(f"- `{item}`." for item in report["still_requires_operator_approval"])
    lines.extend(["", "## Next Operator Actions", ""])
    lines.extend(f"- {item}." for item in report["next_operator_actions"])
    return "\n".join(lines).rstrip() + "\n"


def write_hermes_integration_artifacts(root: Path | str = ".") -> HermesIntegrationArtifacts:
    root_path = Path(root)
    packet = compile_v8_hermes_packet()
    assembly_plan = compile_v8_bot_assembly_plan()
    final_blueprint = compile_loki_final_product_blueprint()
    complete_packages = compile_loki_complete_package_manifest()
    package_readiness = compile_loki_package_readiness_report()
    json_path = root_path / ".loki_lab" / "hermes" / "v8_hermes_manifest.json"
    markdown_path = root_path / "docs" / "V8_HERMES_INTEGRATION.md"
    assembly_json_path = root_path / ".loki_lab" / "hermes" / "v8_bot_assembly_plan.json"
    assembly_markdown_path = root_path / "docs" / "V8_BOT_ASSEMBLY.md"
    final_blueprint_json_path = root_path / ".loki_lab" / "hermes" / "loki_final_product_blueprint.json"
    final_blueprint_markdown_path = root_path / "docs" / "LOKI_FINAL_PRODUCT_BLUEPRINT.md"
    complete_packages_json_path = root_path / ".loki_lab" / "hermes" / "loki_complete_packages.json"
    complete_packages_markdown_path = root_path / "docs" / "LOKI_COMPLETE_PACKAGES.md"
    package_readiness_json_path = root_path / ".loki_lab" / "hermes" / "loki_package_readiness.json"
    package_readiness_markdown_path = root_path / "docs" / "LOKI_PACKAGE_READINESS.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    assembly_json_path.parent.mkdir(parents=True, exist_ok=True)
    assembly_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    final_blueprint_json_path.parent.mkdir(parents=True, exist_ok=True)
    final_blueprint_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    complete_packages_json_path.parent.mkdir(parents=True, exist_ok=True)
    complete_packages_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    package_readiness_json_path.parent.mkdir(parents=True, exist_ok=True)
    package_readiness_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_hermes_integration_markdown(packet), encoding="utf-8")
    assembly_json_path.write_text(json.dumps(assembly_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assembly_markdown_path.write_text(render_v8_bot_assembly_markdown(assembly_plan), encoding="utf-8")
    final_blueprint_json_path.write_text(json.dumps(final_blueprint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final_blueprint_markdown_path.write_text(render_loki_final_product_markdown(final_blueprint), encoding="utf-8")
    complete_packages_json_path.write_text(
        json.dumps(complete_packages, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    complete_packages_markdown_path.write_text(
        render_loki_complete_package_markdown(complete_packages),
        encoding="utf-8",
    )
    package_readiness_json_path.write_text(
        json.dumps(package_readiness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    package_readiness_markdown_path.write_text(
        render_loki_package_readiness_markdown(package_readiness),
        encoding="utf-8",
    )
    return HermesIntegrationArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        assembly_json_path=assembly_json_path,
        assembly_markdown_path=assembly_markdown_path,
        final_blueprint_json_path=final_blueprint_json_path,
        final_blueprint_markdown_path=final_blueprint_markdown_path,
        complete_packages_json_path=complete_packages_json_path,
        complete_packages_markdown_path=complete_packages_markdown_path,
        package_readiness_json_path=package_readiness_json_path,
        package_readiness_markdown_path=package_readiness_markdown_path,
    )
