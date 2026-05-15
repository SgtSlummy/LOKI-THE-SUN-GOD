from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from utils import mythos_router


def test_mythos_router_rejects_path_traversal_slug():
    with pytest.raises(mythos_router.MythosRouterError):
        mythos_router.mythos_run_dir("../outside")


def test_mythos_router_runs_only_whitelisted_cli_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(mythos_router, "APP_ROOT", tmp_path)
    monkeypatch.setattr(mythos_router, "MYTHOS_ROOT", tmp_path / ".mythos")
    executable = str(tmp_path / "mythos-skill")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "compiled\n", "")

    monkeypatch.setattr(mythos_router, "resolve_mythos_skill", lambda: executable)
    monkeypatch.setattr(mythos_router.subprocess, "run", fake_run)

    result = mythos_router.run_mythos_action("compile", run_slug="loki-bot-router")

    assert result.ok is True
    assert result.output == "compiled"
    assert calls[0][0] == [
        executable,
        "compile",
        "--run-dir",
        str(Path(".mythos") / "loki-bot-router"),
    ]
    assert calls[0][1]["cwd"] == tmp_path
    assert "shell" not in calls[0][1]


def test_mythos_init_preserves_existing_source_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(mythos_router, "APP_ROOT", tmp_path)
    monkeypatch.setattr(mythos_router, "MYTHOS_ROOT", tmp_path / ".mythos")
    run_dir = tmp_path / ".mythos" / "backend-standards"
    run_dir.mkdir(parents=True)
    (run_dir / "sources.json").write_text('{"sources":[{"url":"https://github.com/futurice/backend-best-practices"}]}\n')

    def fake_run(command, **_kwargs):
        assert command[1:] == ["init", str(Path(".mythos") / "backend-standards")]
        assert not run_dir.exists()
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text("{}\n")
        verifier_dir = run_dir / "verifier-results"
        verifier_dir.mkdir()
        (verifier_dir / "findings.jsonl").write_text(
            '{"id":"vf-synthesis-pending","summary":"Synthesis has not consumed this packet yet",'
            '"status":"pending","verifier_score":0.0,"source_ids":["raw:objective.md"]}\n'
        )
        return subprocess.CompletedProcess(command, 0, "initialized\n", "")

    monkeypatch.setattr(mythos_router, "resolve_mythos_skill", lambda: str(tmp_path / "mythos-skill"))
    monkeypatch.setattr(mythos_router.subprocess, "run", fake_run)

    result = mythos_router.run_mythos_action("init", run_slug="backend-standards")

    assert result.ok is True
    assert mythos_router.load_mythos_sources("backend-standards")[0]["url"] == (
        "https://github.com/futurice/backend-best-practices"
    )
    assert "vf-codex-synthesis-pending" in (run_dir / "verifier-results" / "findings.jsonl").read_text()
    assert "vf-synthesis-pending" not in (run_dir / "verifier-results" / "findings.jsonl").read_text()


def test_mythos_compile_normalizes_legacy_synthesis_finding(monkeypatch, tmp_path):
    monkeypatch.setattr(mythos_router, "APP_ROOT", tmp_path)
    monkeypatch.setattr(mythos_router, "MYTHOS_ROOT", tmp_path / ".mythos")
    run_dir = tmp_path / ".mythos" / "backend-standards"
    verifier_dir = run_dir / "verifier-results"
    verifier_dir.mkdir(parents=True)
    findings_path = verifier_dir / "findings.jsonl"
    findings_path.write_text(
        '{"id":"vf-synthesis-pending","summary":"Synthesis has not consumed this packet yet",'
        '"status":"pending","verifier_score":0.0,"source_ids":["raw:objective.md"]}\n'
    )

    def fake_run(command, **_kwargs):
        findings = findings_path.read_text()
        assert "vf-codex-synthesis-pending" in findings
        assert "vf-synthesis-pending" not in findings
        return subprocess.CompletedProcess(command, 0, "compiled\n", "")

    monkeypatch.setattr(mythos_router, "resolve_mythos_skill", lambda: str(tmp_path / "mythos-skill"))
    monkeypatch.setattr(mythos_router.subprocess, "run", fake_run)

    result = mythos_router.run_mythos_action("compile", run_slug="backend-standards")

    assert result.ok is True


def test_mythos_snapshot_summarizes_compiled_packet(monkeypatch, tmp_path):
    monkeypatch.setattr(mythos_router, "APP_ROOT", tmp_path)
    monkeypatch.setattr(mythos_router, "MYTHOS_ROOT", tmp_path / ".mythos")
    run_dir = tmp_path / ".mythos" / "loki-bot-router" / "state"
    run_dir.mkdir(parents=True)
    (run_dir / "next_pass_packet.json").write_text(
        '{"pass_id":"pass-2","evidence":[{}],"verifier_results":[{},{}],"blockers":[]}',
        encoding="utf-8",
    )

    snapshot = mythos_router.mythos_snapshot("loki-bot-router")

    assert snapshot["exists"] is True
    assert snapshot["packet_exists"] is True
    assert snapshot["packet_summary"]["pass_id"] == "pass-2"
    assert snapshot["packet_summary"]["evidence_count"] == 1
    assert snapshot["packet_summary"]["verifier_count"] == 2


def test_mythos_add_source_records_normalized_github_source(monkeypatch, tmp_path):
    monkeypatch.setattr(mythos_router, "APP_ROOT", tmp_path)
    monkeypatch.setattr(mythos_router, "MYTHOS_ROOT", tmp_path / ".mythos")

    record = mythos_router.add_mythos_source(
        "https://github.com/futurice/backend-best-practices/",
        run_slug="backend-standards",
        note="Codex backend standards",
        added_by="123",
    )

    assert record["url"] == "https://github.com/futurice/backend-best-practices"
    assert record["owner"] == "futurice"
    assert record["repo"] == "backend-best-practices"
    assert mythos_router.load_mythos_sources("backend-standards")[0]["note"] == "Codex backend standards"
    assert mythos_router.mythos_snapshot("backend-standards")["source_count"] == 1


def test_mythos_add_source_rejects_non_github_urls():
    with pytest.raises(mythos_router.MythosRouterError):
        mythos_router.normalize_source_url("http://localhost:5000/private")


def test_mythos_env_adds_windows_node_path_when_node_missing(monkeypatch, tmp_path):
    node_dir = tmp_path / "nodejs"
    node_dir.mkdir(parents=True)
    (node_dir / "node.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(mythos_router, "_local_mythos_bin_dir", lambda: None)
    monkeypatch.setattr(mythos_router.os, "environ", {"PATH": "", "ProgramFiles": str(tmp_path)})
    monkeypatch.setattr(mythos_router.shutil, "which", lambda command, path=None: None)

    env = mythos_router.mythos_env()

    assert str(node_dir) in env["PATH"].split(mythos_router.os.pathsep)


def test_mythos_env_keeps_existing_node_path_order(monkeypatch, tmp_path):
    local_bin = tmp_path / "mythos-bin"
    local_bin.mkdir()

    monkeypatch.setattr(mythos_router, "_local_mythos_bin_dir", lambda: local_bin)
    monkeypatch.setattr(
        mythos_router.os,
        "environ",
        {"PATH": "/usr/bin", "ProgramFiles": str(tmp_path)},
    )
    monkeypatch.setattr(
        mythos_router.shutil,
        "which",
        lambda command, path=None: "/usr/bin/node" if command == "node" else None,
    )

    env = mythos_router.mythos_env()
    entries = env["PATH"].split(mythos_router.os.pathsep)

    assert entries[0] == str(local_bin)
    assert entries[1:] == ["/usr/bin"]


def test_command_catalog_exposes_owner_only_mythos_router():
    from utils.command_catalog import parse_command_catalog

    catalog = parse_command_catalog(Path(__file__).resolve().parents[1])
    names = {item["full_name"] for item in catalog}

    assert {"mythos status", "mythos ready", "mythos add", "mythos compile", "mythos gate"}.issubset(names)
