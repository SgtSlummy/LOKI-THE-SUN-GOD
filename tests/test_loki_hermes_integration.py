from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loki_research.hermes_integration import (
    compile_loki_complete_package_manifest,
    compile_loki_final_product_blueprint,
    compile_loki_package_readiness_report,
    compile_v8_bot_assembly_plan,
    compile_v8_hermes_packet,
    render_hermes_integration_markdown,
    render_loki_complete_package_markdown,
    render_loki_final_product_markdown,
    render_loki_package_readiness_markdown,
    render_v8_bot_assembly_markdown,
    v8_hermes_integration_spec,
    write_hermes_integration_artifacts,
)


def test_v8_hermes_spec_is_local_operator_integration_only():
    spec = v8_hermes_integration_spec()

    assert spec.version == "V8"
    assert spec.lane == "hermes_agent_operator_integration"
    assert spec.local_only is True
    assert spec.launch_policy == "manifest_only_until_operator_approval"
    assert "Hermes project profile manifest" in spec.deliverables
    assert "hermes-agent" in spec.required_skills
    assert "test-driven-development" in spec.required_skills
    assert "hermes gateway install" in spec.blocked_actions
    assert "hermes cron create" in spec.blocked_actions
    assert "--yolo autonomous mutation" in spec.blocked_actions


def test_v8_packet_defines_safe_hermes_commands_and_toolsets():
    packet = compile_v8_hermes_packet()

    assert packet["sequence"] == "V8"
    assert packet["external_jobs_launched"] is False
    assert packet["hermes"]["profile_name"] == "loki-v8-local"
    assert packet["hermes"]["recommended_toolsets"] == [
        "terminal",
        "file",
        "skills",
        "session_search",
        "todo",
        "delegation",
    ]
    assert packet["hermes"]["skill_preload"] == [
        "hermes-agent",
        "test-driven-development",
        "systematic-debugging",
        "github-pr-workflow",
    ]
    assert packet["hermes"]["safe_commands"]["doctor"] == "hermes doctor"
    assert packet["hermes"]["safe_commands"]["local_query"].startswith("hermes -s hermes-agent")
    assert packet["hermes"]["forbidden_commands"] == [
        "hermes --yolo",
        "hermes gateway install",
        "hermes gateway run",
        "hermes cron create",
        "hermes chat -q with production mutation",
    ]


def test_v8_bot_assembly_plan_hard_codes_runtime_modules_and_gates():
    plan = compile_v8_bot_assembly_plan()

    assert plan["sequence"] == "V8-bot-assembly"
    assert plan["assembly_mode"] == "hard_coded_local_compile"
    assert plan["runtime_entrypoint"] == "bot.py"
    assert plan["external_jobs_launched"] is False
    assert plan["pending_tasks_required"] == "complete"
    assert plan["operator_approval_required"] is True
    assert plan["required_inputs"] == [
        ".loki_lab/hermes/v8_hermes_manifest.json",
        "docs/V8_HERMES_INTEGRATION.md",
        "docs/V4_V7_EXECUTION_MAP.md",
        "Mythos verifier packet",
        "Obliteratus advisory context",
    ]
    assert plan["core_modules"] == [
        "bot.py",
        "loki_engine/core.py",
        "loki_npc/persona.py",
        "loki_music/service.py",
        "loki_activity_bridge/client.py",
        "loki_mcp/server.py",
    ]
    compile_command = (
        "python -m compileall bot.py cogs loki_engine loki_npc loki_music loki_activity_bridge "
        "loki_mcp loki_research"
    )
    assert compile_command in plan["compile_commands"]
    assert "python scripts/release_check.py" in plan["verification_commands"]
    assert "DISCORD_TOKEN" in plan["required_runtime_secrets"]


def test_v8_bot_assembly_plan_blocks_autonomous_mutation_and_deploys():
    plan = compile_v8_bot_assembly_plan()

    assert plan["blocked_commands"] == [
        "hermes --yolo",
        "hermes gateway install",
        "hermes cron create",
        "railway up",
        "python bot.py",
        "destructive Obliteratus rewrite",
        "ungated Mythos promotion",
    ]
    assert plan["assembly_steps"] == [
        "confirm V4-V7 and V8 manifests are checked in",
        "compile Python bot modules without starting the Discord client",
        "run secret scan and local release gates",
        "stage operator-reviewed patch only after Mythos gate passes",
        "wait for explicit operator approval before runtime launch or deploy",
    ]


def test_rendered_v8_bot_assembly_markdown_lists_compile_and_blocked_commands():
    markdown = render_v8_bot_assembly_markdown(compile_v8_bot_assembly_plan())

    assert "# LOKI V8 Hard-Coded Bot Assembly" in markdown
    assert "bot.py" in markdown
    assert "python -m compileall" in markdown
    assert "python bot.py" in markdown
    assert "railway up" in markdown
    assert "No runtime launch, gateway install, cron job, or Railway deploy is performed" in markdown
    markdown = render_hermes_integration_markdown(compile_v8_hermes_packet())

    assert "# LOKI V8 Hermes Agent Integration" in markdown
    assert "Hermes project profile manifest" in markdown
    assert "hermes -s hermes-agent,test-driven-development" in markdown
    assert "hermes gateway install" in markdown
    assert "hermes cron create" in markdown
    assert "No Hermes gateway, cron job, or autonomous background agent is launched" in markdown


def test_final_product_blueprint_captures_loki_identity_and_surfaces():
    blueprint = compile_loki_final_product_blueprint()

    assert blueprint["product_name"] == "LOKI: THE SON GOD"
    assert blueprint["primary_interface"] == "Discord"
    assert blueprint["product_type"] == "AGI-style Discord bot and app"
    assert blueprint["deployment_target"] == "fully_hosted_online_with_optional_local_gpu_workers"
    assert blueprint["surfaces"] == [
        "Discord bot",
        "Discord app",
        "console dashboard",
        "desktop .exe controller",
        "Hermes operator profile",
    ]
    assert "interactable LLM input" in blueprint["console_dashboard"]["capabilities"]
    assert "sub-agent control" in blueprint["console_dashboard"]["capabilities"]
    assert "natural language Discord control" in blueprint["discord_experience"]["capabilities"]


def test_final_product_blueprint_covers_media_memory_research_and_camelot():
    blueprint = compile_loki_final_product_blueprint()

    assert blueprint["memory"]["system_of_record"] == "Camelot"
    assert blueprint["memory"]["member_memory"] == [
        "posted content history per Discord member",
        "admin-provided member notes",
        "summaries and askable profiles per member",
        "sub-agent maintained evidence trails",
    ]
    assert blueprint["media"]["modalities"] == ["music", "video", "image", "text", "websites", "games"]
    assert "generation" in blueprint["media"]["operations"]
    assert "local GPU model worker optional" in blueprint["models"]["deployment_modes"]
    assert blueprint["autonomy"]["web_crawling"] == "manual_and_autonomous_full_web_crawl_with_operator_policy"
    assert "post related ideas/pictures/websites/games to Discord" in blueprint["autonomy"]["community_actions"]
    assert "continue autonomous research/upgrade/evolution loop" in blueprint["autonomy"]["upgrade_loop"]


def test_final_product_blueprint_has_phased_delivery_and_safety_gates():
    blueprint = compile_loki_final_product_blueprint()

    assert [phase["id"] for phase in blueprint["delivery_phases"]] == [
        "P0",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
    ]
    assert blueprint["delivery_phases"][0]["title"] == "Foundation and hosted Discord core"
    assert blueprint["delivery_phases"][-1]["title"] == "Autonomous evolution with operator governance"
    assert "admin approval for posting/deploying/evolving" in blueprint["safety_gates"]
    assert "secret scan before every release" in blueprint["safety_gates"]
    assert "Camelot memory export/import test" in blueprint["acceptance_tests"]
    assert "Discord natural language member summary test" in blueprint["acceptance_tests"]


def test_final_product_markdown_and_artifact_paths_are_deterministic(tmp_path):
    markdown = render_loki_final_product_markdown(compile_loki_final_product_blueprint())

    assert "# LOKI: THE SON GOD Final Product Blueprint" in markdown
    assert "Discord bot" in markdown
    assert "Camelot" in markdown
    assert "local GPU" in markdown
    assert "Autonomous evolution with operator governance" in markdown

    artifacts = write_hermes_integration_artifacts(tmp_path)
    expected_blueprint_json = tmp_path / ".loki_lab" / "hermes" / "loki_final_product_blueprint.json"
    assert artifacts.final_blueprint_json_path == expected_blueprint_json
    assert artifacts.final_blueprint_markdown_path == tmp_path / "docs" / "LOKI_FINAL_PRODUCT_BLUEPRINT.md"
    assert artifacts.final_blueprint_json_path.exists()
    assert artifacts.final_blueprint_markdown_path.exists()
    artifacts = write_hermes_integration_artifacts(tmp_path)

    assert artifacts.json_path == tmp_path / ".loki_lab" / "hermes" / "v8_hermes_manifest.json"
    assert artifacts.markdown_path == tmp_path / "docs" / "V8_HERMES_INTEGRATION.md"
    assert artifacts.assembly_json_path == tmp_path / ".loki_lab" / "hermes" / "v8_bot_assembly_plan.json"
    assert artifacts.assembly_markdown_path == tmp_path / "docs" / "V8_BOT_ASSEMBLY.md"
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert artifacts.assembly_json_path.exists()
    assert artifacts.assembly_markdown_path.exists()

    packet = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert packet["versions"][0]["version"] == "V8"
    assert "LOKI V8 Hermes Agent Integration" in artifacts.markdown_path.read_text(encoding="utf-8")


def test_complete_package_manifest_defines_all_ship_targets_and_artifacts():
    manifest = compile_loki_complete_package_manifest()

    assert manifest["product_name"] == "LOKI: THE SON GOD"
    assert manifest["completion_state"] == "package_manifest_ready_local_only"
    assert manifest["external_jobs_launched"] is False
    assert [package["id"] for package in manifest["packages"]] == [
        "discord-runtime",
        "discord-app",
        "console-dashboard",
        "desktop-controller",
        "activity-bridge",
        "hermes-camelot-memory",
        "media-and-crawler-workers",
        "local-gpu-workers",
    ]
    desktop_package = next(package for package in manifest["packages"] if package["id"] == "desktop-controller")
    assert desktop_package["artifact"] == "dist/LOKI-THE-SUN-GOD-Dashboard.exe"
    assert "powershell -ExecutionPolicy Bypass -File ./scripts/build_standalone.ps1" in desktop_package[
        "build_commands"
    ]
    activity_package = next(package for package in manifest["packages"] if package["id"] == "activity-bridge")
    assert activity_package["artifact"] == "services/activity-bridge/client/dist"
    assert activity_package["build_commands"] == ["npm run typecheck", "npm run build"]


def test_complete_package_manifest_keeps_live_launch_and_deploy_blocked():
    manifest = compile_loki_complete_package_manifest()

    assert manifest["promotion_policy"] == "operator_review_required_before_any_live_package_launch"
    assert manifest["blocked_until_operator_approval"] == [
        "python bot.py",
        "railway up",
        "hermes gateway install",
        "hermes cron create",
        "publishing Discord app commands to a live guild",
        "autonomous crawler posting to Discord",
        "shipping desktop .exe without secret scan and release check evidence",
    ]
    assert "python scripts/release_check.py --strict-env" in manifest["final_release_gates"]
    assert "npm run test:rooms" in manifest["final_release_gates"]
    assert "manual Windows PyInstaller smoke for desktop .exe" in manifest["manual_gates"]


def test_complete_package_markdown_and_artifact_paths_are_deterministic(tmp_path):
    markdown = render_loki_complete_package_markdown(compile_loki_complete_package_manifest())

    assert "# LOKI: THE SON GOD Complete Package Manifest" in markdown
    assert "discord-runtime" in markdown
    assert "desktop-controller" in markdown
    assert "dist/LOKI-THE-SUN-GOD-Dashboard.exe" in markdown
    assert "operator_review_required_before_any_live_package_launch" in markdown

    artifacts = write_hermes_integration_artifacts(tmp_path)
    expected_packages_json = tmp_path / ".loki_lab" / "hermes" / "loki_complete_packages.json"
    assert artifacts.complete_packages_json_path == expected_packages_json
    assert artifacts.complete_packages_markdown_path == tmp_path / "docs" / "LOKI_COMPLETE_PACKAGES.md"
    assert artifacts.complete_packages_json_path.exists()
    assert artifacts.complete_packages_markdown_path.exists()


def test_package_readiness_report_maps_each_package_to_completion_evidence():
    report = compile_loki_package_readiness_report()

    assert report["product_name"] == "LOKI: THE SON GOD"
    assert report["readiness_state"] == "local_package_evidence_compiled"
    assert report["external_jobs_launched"] is False
    assert report["summary"] == {
        "total_packages": 8,
        "automated_ready": 5,
        "contract_ready": 3,
        "manual_gate_required": 4,
    }
    assert [row["package_id"] for row in report["matrix"]] == [
        "discord-runtime",
        "discord-app",
        "console-dashboard",
        "desktop-controller",
        "activity-bridge",
        "hermes-camelot-memory",
        "media-and-crawler-workers",
        "local-gpu-workers",
    ]
    desktop = next(row for row in report["matrix"] if row["package_id"] == "desktop-controller")
    assert desktop["status"] == "manual_gate_required"
    assert desktop["evidence"] == [
        "LokiDashboard.spec",
        "scripts/build_standalone.ps1",
        "manual Windows PyInstaller smoke for desktop .exe",
    ]


def test_package_readiness_report_never_converts_manual_gates_into_launches():
    report = compile_loki_package_readiness_report()

    assert "python bot.py" in report["still_requires_operator_approval"]
    assert "railway up" in report["still_requires_operator_approval"]
    assert "hermes gateway install" in report["still_requires_operator_approval"]
    assert report["next_operator_actions"] == [
        "provide production secrets outside git",
        "run strict environment release check on the deployment host",
        "smoke-test desktop .exe on Windows after PyInstaller build",
        "verify Discord Developer Portal intents, OAuth redirect, and command publication target",
        "approve or reject live bot launch, crawler posting, and hosted deploy separately",
    ]


def test_package_readiness_markdown_and_artifact_paths_are_deterministic(tmp_path):
    markdown = render_loki_package_readiness_markdown(compile_loki_package_readiness_report())

    assert "# LOKI: THE SON GOD Package Readiness Report" in markdown
    assert "local_package_evidence_compiled" in markdown
    assert "desktop-controller" in markdown
    assert "manual Windows PyInstaller smoke for desktop .exe" in markdown
    assert "approve or reject live bot launch" in markdown

    artifacts = write_hermes_integration_artifacts(tmp_path)
    expected_report_json = tmp_path / ".loki_lab" / "hermes" / "loki_package_readiness.json"
    assert artifacts.package_readiness_json_path == expected_report_json
    assert artifacts.package_readiness_markdown_path == tmp_path / "docs" / "LOKI_PACKAGE_READINESS.md"
    assert artifacts.package_readiness_json_path.exists()
    assert artifacts.package_readiness_markdown_path.exists()


def test_compile_v8_hermes_script_runs_directly_from_any_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "compile_v8_hermes.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".loki_lab" / "hermes" / "v8_hermes_manifest.json").exists()
    assert (tmp_path / ".loki_lab" / "hermes" / "v8_bot_assembly_plan.json").exists()
    assert (tmp_path / "docs" / "V8_BOT_ASSEMBLY.md").exists()
    assert (tmp_path / ".loki_lab" / "hermes" / "loki_complete_packages.json").exists()
    assert (tmp_path / "docs" / "LOKI_COMPLETE_PACKAGES.md").exists()
    assert (tmp_path / ".loki_lab" / "hermes" / "loki_package_readiness.json").exists()
    assert (tmp_path / "docs" / "LOKI_PACKAGE_READINESS.md").exists()
