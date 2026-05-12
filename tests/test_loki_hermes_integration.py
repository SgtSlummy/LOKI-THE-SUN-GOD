from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loki_research.hermes_integration import (
    compile_v8_hermes_packet,
    render_hermes_integration_markdown,
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


def test_v8_markdown_documents_operator_workflow_and_blocked_modes():
    markdown = render_hermes_integration_markdown(compile_v8_hermes_packet())

    assert "# LOKI V8 Hermes Agent Integration" in markdown
    assert "Hermes project profile manifest" in markdown
    assert "hermes -s hermes-agent,test-driven-development" in markdown
    assert "hermes gateway install" in markdown
    assert "hermes cron create" in markdown
    assert "No Hermes gateway, cron job, or autonomous background agent is launched" in markdown


def test_write_hermes_integration_artifacts_outputs_json_and_markdown(tmp_path):
    artifacts = write_hermes_integration_artifacts(tmp_path)

    assert artifacts.json_path == tmp_path / ".loki_lab" / "hermes" / "v8_hermes_manifest.json"
    assert artifacts.markdown_path == tmp_path / "docs" / "V8_HERMES_INTEGRATION.md"
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()

    packet = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert packet["versions"][0]["version"] == "V8"
    assert "LOKI V8 Hermes Agent Integration" in artifacts.markdown_path.read_text(encoding="utf-8")


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
