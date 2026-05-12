from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loki_research.version_pipeline import (
    compile_next_version_packet,
    next_four_versions,
    render_versions_markdown,
    write_version_artifacts,
)


def test_next_four_versions_are_v4_to_v7_with_expected_lanes():
    versions = next_four_versions()

    assert [version.version for version in versions] == ["V4", "V5", "V6", "V7"]
    assert [version.lane for version in versions] == [
        "research_lab_runner",
        "hf_trackio_training",
        "temporal_activity_orchestration",
        "cerebrum_agent_adapter",
    ]
    assert all(version.local_only for version in versions)
    assert all("mythos-skill gate" in version.required_gates for version in versions)


def test_compiled_packet_keeps_advanced_versions_blocked_from_production():
    packet = compile_next_version_packet()

    assert packet["sequence"] == "V4-V7"
    assert packet["global_guards"]["production_mutation"] == "blocked"
    assert packet["global_guards"]["promotion_requires"] == [
        "V2 hosted acceptance",
        "reviewed patch or PR",
        "passing local gates",
        "passing Mythos gate",
    ]
    assert packet["external_jobs_launched"] is False
    assert packet["versions"][1]["version"] == "V5"
    assert packet["versions"][1]["launch_policy"] == "plan_only_until_model_dataset_token_are_set"
    assert "HF_TOKEN" in packet["versions"][1]["required_secrets"]
    assert packet["versions"][2]["runtime_dependency"] == "Temporal CLI/SDK optional; no worker launch in V6 packet"
    assert packet["versions"][3]["python_constraint"] == "3.10_or_3.11"


def test_each_v4_to_v7_spec_has_readiness_checklist_and_blocked_actions():
    packet = compile_next_version_packet()

    assert packet["external_jobs_launched"] is False
    assert packet["global_guards"]["blocked_external_actions"] == [
        "huggingface_training_job_launch",
        "trackio_space_mutation",
        "temporal_worker_start",
        "obs_or_twitch_live_mutation",
        "cerebrum_or_aios_agent_execution",
    ]
    for version in packet["versions"]:
        assert version["promotion_state"] == "draft_local_only"
        assert len(version["acceptance_checklist"]) >= 4
        assert version["blocked_actions"]
        assert version["evidence_artifacts"]


def test_v4_to_v7_specs_include_lane_specific_safety_contracts():
    packet = compile_next_version_packet()
    versions = {version["version"]: version for version in packet["versions"]}

    assert "write artifacts only under .loki_lab and docs" in versions["V4"]["acceptance_checklist"]
    assert "production code mutation" in versions["V4"]["blocked_actions"]
    assert "validate dataset schema before any trainer command" in versions["V5"]["acceptance_checklist"]
    assert "training job launch" in versions["V5"]["blocked_actions"]
    assert "npm run test:rooms" in versions["V6"]["required_gates"]
    assert "Temporal worker launch" in versions["V6"]["blocked_actions"]
    assert "emit advisory-only adapter manifest" in versions["V7"]["acceptance_checklist"]
    assert "live Cerebrum/AIOS agent execution" in versions["V7"]["blocked_actions"]


def test_rendered_markdown_lists_all_versions_and_guardrails():
    markdown = render_versions_markdown(compile_next_version_packet())

    assert "# LOKI V4/V5/V6/V7 Raw Code Assembly" in markdown
    for expected in (
        "V4 - Local Research Lab Runner",
        "V5 - Hugging Face + Trackio Training Lane",
        "V6 - Temporal Activity Orchestration Lane",
        "V7 - Cerebrum Agent Adapter Lane",
    ):
        assert expected in markdown
    assert "No external training jobs, Temporal workers, or Cerebrum kernels are launched by this packet." in markdown
    assert "#### Acceptance Checklist" in markdown
    assert "#### Blocked Actions" in markdown


def test_write_version_artifacts_outputs_json_and_markdown(tmp_path):
    artifacts = write_version_artifacts(tmp_path)

    assert artifacts.json_path == tmp_path / ".loki_lab" / "version_packets" / "v4_v7_compiled.json"
    assert artifacts.markdown_path == tmp_path / "docs" / "V4_V7_EXECUTION_MAP.md"
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()

    packet = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert packet["sequence"] == "V4-V7"
    assert "V7 - Cerebrum Agent Adapter Lane" in artifacts.markdown_path.read_text(encoding="utf-8")


def test_compile_next_versions_script_runs_directly_from_any_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "compile_next_versions.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".loki_lab" / "version_packets" / "v4_v7_compiled.json").exists()
