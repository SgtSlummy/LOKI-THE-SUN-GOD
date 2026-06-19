from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from scripts.loki_guardian import (
    HealthResult,
    ProcessInfo,
    RestartPolicy,
    SingleInstanceLock,
    build_default_bot_command,
    evaluate_health_payload,
    find_duplicate_loki_processes,
    format_duplicate_processes,
    parse_args,
    redact_command,
    redact_text,
)


def test_build_default_bot_command_runs_loki_module():
    assert build_default_bot_command() == [sys.executable, "-m", "bot.main"]


def test_redact_command_hides_discord_tokens():
    redacted = redact_command(["python", "-m", "bot.main", "--token", "abc", "DISCORD_TOKEN=secret"])

    assert "abc" not in " ".join(redacted)
    assert "secret" not in " ".join(redacted)
    assert redacted == ["python", "-m", "bot.main", "--token", "<redacted>", "DISCORD_TOKEN=<redacted>"]


def test_redact_text_hides_child_output_secrets():
    text = "DISCORD_TOKEN=abc Authorization: Bot abcdefghijklmnopqrstuvwxyz token=secret api_key=value password=pw"

    redacted = redact_text(text)

    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "secret" not in redacted
    assert "api_key=value" not in redacted
    assert "password=pw" not in redacted
    assert redacted.count("<redacted>") >= 4


def test_format_duplicate_processes_redacts_command_lines():
    formatted = format_duplicate_processes([ProcessInfo(pid=1, command_line="python -m bot.main DISCORD_TOKEN=secret")])

    assert "secret" not in formatted
    assert "DISCORD_TOKEN=<redacted>" in formatted


def test_parse_args_loads_dotenv_health_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HEALTH_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("LOKI_GUARDIAN_HEALTH_URL", raising=False)
    (tmp_path / ".env").write_text("HEALTH_PORT=12345\n", encoding="utf-8")

    args = parse_args([])

    assert args.health_url == "http://127.0.0.1:12345/healthz"


def test_evaluate_health_payload_requires_ok_and_discord_connected():
    assert evaluate_health_payload({"ok": True, "discord_connected": True}).healthy is True
    assert evaluate_health_payload({"ok": True, "discord_connected": False}).healthy is False
    assert evaluate_health_payload({"ok": False, "discord_connected": True}).healthy is False


def test_restart_policy_requires_consecutive_failures_and_limits_daily_restarts():
    policy = RestartPolicy(failure_threshold=3, max_restarts_per_24h=2)

    assert policy.record_health(HealthResult(False, "bad"), now=100.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=101.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=102.0) is True
    policy.record_restart(now=102.0)

    assert policy.record_health(HealthResult(True, "ok"), now=103.0) is False
    assert policy.consecutive_failures == 0

    assert policy.record_health(HealthResult(False, "bad"), now=104.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=105.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=106.0) is True
    policy.record_restart(now=106.0)

    assert policy.record_health(HealthResult(False, "bad"), now=107.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=108.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=109.0) is False


def test_restart_policy_prunes_old_restart_records():
    policy = RestartPolicy(failure_threshold=1, max_restarts_per_24h=1)
    policy.record_restart(now=0.0)

    assert policy.record_health(HealthResult(False, "bad"), now=10.0) is False
    assert policy.record_health(HealthResult(False, "bad"), now=24 * 60 * 60 + 1.0) is True


def test_single_instance_lock_recovers_stale_lock_file(tmp_path: Path):
    lock_path = tmp_path / "guardian.lock"
    lock_path.write_text("999999999", encoding="utf-8")

    lock = SingleInstanceLock(lock_path)
    lock.acquire()
    assert lock_path.exists()
    lock.release()
    assert not lock_path.exists()


def test_duplicate_process_detection_ignores_current_process_and_unrelated_python(tmp_path: Path):
    project_dir = tmp_path / "Loki 2.0"
    processes = [
        ProcessInfo(pid=10, command_line=f"python -m scripts.loki_guardian --project-dir {project_dir}", name="python.exe"),
        ProcessInfo(pid=11, command_line=f"python -m bot.main --cwd {project_dir}", name="python.exe"),
        ProcessInfo(pid=12, command_line="python -m other.service", name="python.exe"),
        ProcessInfo(pid=13, command_line=f"python -m scripts.loki_guardian --project-dir {project_dir}", name="python.exe"),
        ProcessInfo(pid=14, command_line="python -m bot.main", cwd=str(project_dir), name="python.exe"),
        ProcessInfo(pid=15, command_line="python bot/main.py", cwd=str(project_dir), name="python.exe"),
        ProcessInfo(pid=16, command_line=f"bash.exe -lic set +m; python -m scripts.loki_guardian --project-dir {project_dir}", cwd=str(project_dir), name="bash.exe"),
    ]

    duplicates = find_duplicate_loki_processes(processes, current_pid=10, project_dir=project_dir)

    assert [process.pid for process in duplicates] == [11, 13, 14, 15]


def test_duplicate_process_detection_does_not_match_other_loki_checkout(tmp_path: Path):
    project_dir = tmp_path / "Loki 2.0"
    other_project_dir = tmp_path / "Other Loki"
    processes = [
        ProcessInfo(pid=20, command_line=f"python -m bot.main --cwd {other_project_dir}"),
        ProcessInfo(pid=21, command_line="python -m bot.main"),
    ]

    assert find_duplicate_loki_processes(processes, current_pid=99, project_dir=project_dir) == []


@pytest.mark.asyncio
async def test_guardian_can_restart_a_crashed_child_process(tmp_path: Path):
    script = tmp_path / "crash_once.py"
    marker = tmp_path / "marker"
    script.write_text(
        "from pathlib import Path\n"
        f"marker = Path({str(marker)!r})\n"
        "if not marker.exists():\n"
        "    marker.write_text('crashed')\n"
        "    raise SystemExit(7)\n"
        "import time\n"
        "time.sleep(3)\n",
        encoding="utf-8",
    )

    from scripts.loki_guardian import LokiGuardian

    guardian = LokiGuardian(
        command=[sys.executable, str(script)],
        project_dir=tmp_path,
        health_url="",
        check_interval_seconds=0.1,
        startup_grace_seconds=0.0,
        restart_policy=RestartPolicy(failure_threshold=1, max_restarts_per_24h=5, base_restart_delay_seconds=0.1),
        log_path=tmp_path / "guardian.log",
    )

    task = asyncio.create_task(guardian.run(max_runtime_seconds=1.0))
    await task

    assert guardian.restart_count >= 1
    assert marker.exists()
    assert (tmp_path / "guardian.log").exists()
