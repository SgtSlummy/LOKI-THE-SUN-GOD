from __future__ import annotations

import io
import os
import signal
import subprocess
from pathlib import Path

import pytest

from scripts import windows_service_common as service_common
from scripts.loki_bot_service import BOT_SERVICE_SPEC, LokiBotService
from scripts.loki_dashboard_service import DASHBOARD_SERVICE_SPEC, LokiDashboardService


class FakeProcess:
    def __init__(self, *, returncode: int = 0, time_out_once: bool = False) -> None:
        self.pid = 4321
        self.returncode = returncode
        self.time_out_once = time_out_once
        self.events: list[object] = []

    def send_signal(self, sent_signal: int) -> None:
        self.events.append(("signal", sent_signal))

    def terminate(self) -> None:
        self.events.append("terminate")

    def wait(self, timeout: float | None = None) -> int:
        self.events.append(("wait", timeout))
        if timeout is not None and self.time_out_once:
            self.time_out_once = False
            raise subprocess.TimeoutExpired("child", timeout)
        return self.returncode

    def kill(self) -> None:
        self.events.append("kill")


class FakePopen:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs: object) -> FakeProcess:
        self.calls.append((command, kwargs))
        return self.process


class FakePsutilProcess:
    def __init__(self, pid: int, command: list[str] | None) -> None:
        self.pid = pid
        self.info = {"pid": pid, "cmdline": command}


def prepare_release(tmp_path: Path) -> tuple[Path, Path, Path]:
    release_root = tmp_path / "releases" / "candidate-123"
    release_root.mkdir(parents=True)
    (release_root / "local_loki_runtime.py").write_text("# bot\n", encoding="utf-8")
    (release_root / "dashboard_app.py").write_text("# dashboard\n", encoding="utf-8")
    python_executable = tmp_path / "venvs" / "candidate-123" / "Scripts" / "python.exe"
    python_executable.parent.mkdir(parents=True)
    python_executable.write_bytes(b"")
    env_path = tmp_path / "config" / "lokithesungod.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("LOKI_LOCAL_ALLOW_FULL=true\n", encoding="utf-8")
    return release_root, python_executable, env_path


def make_host(
    tmp_path: Path,
    spec: service_common.ServiceSpec = BOT_SERVICE_SPEC,
    *,
    process: FakeProcess | None = None,
    process_iter=None,
    diagnostic_writer=None,
):
    release_root, python_executable, env_path = prepare_release(tmp_path)
    fake_process = process or FakeProcess()
    popen = FakePopen(fake_process)
    log_stream = io.StringIO()
    host = service_common.ChildServiceHost(
        spec,
        release_root=release_root,
        python_executable=python_executable,
        env_path=env_path,
        program_data=tmp_path / "ProgramData",
        popen_factory=popen,
        process_iter=process_iter or (lambda _attrs: []),
        log_opener=lambda *_args, **_kwargs: log_stream,
        diagnostic_writer=diagnostic_writer,
    )
    return host, fake_process, popen, log_stream


def test_bot_command_is_exact_and_absolute(tmp_path):
    host, _process, popen, _log = make_host(tmp_path)

    host.start()

    command, kwargs = popen.calls[0]
    assert command == [
        str(host.python_executable),
        str(host.release_root / "local_loki_runtime.py"),
        "--mode",
        "full",
        "--host",
        "127.0.0.1",
        "--port",
        "9101",
    ]
    assert all(Path(value).is_absolute() for value in command[:2])
    assert kwargs["cwd"] == str(host.release_root)
    assert kwargs["stderr"] == subprocess.STDOUT
    assert kwargs["stdout"] is not None
    assert "desktop_app.py" not in " ".join(command)


def test_dashboard_command_and_loopback_environment_are_enforced(tmp_path):
    host, _process, popen, _log = make_host(tmp_path, DASHBOARD_SERVICE_SPEC)
    host.base_environment = {
        "DASHBOARD_HOST": "0.0.0.0",
        "DASHBOARD_PORT": "9998",
        "PORT": "9999",
    }

    host.start()

    command, kwargs = popen.calls[0]
    assert command == [str(host.python_executable), str(host.release_root / "dashboard_app.py")]
    child_env = kwargs["env"]
    assert child_env["DASHBOARD_HOST"] == "127.0.0.1"
    assert child_env["DASHBOARD_PORT"] == "5000"
    assert child_env["PORT"] == "5000"


def test_child_environment_preserves_process_values_but_pins_stable_paths(tmp_path):
    host, _process, popen, _log = make_host(tmp_path)
    host.base_environment = {
        "DISCORD_TOKEN": "process-secret",
        "LOKI_APP_ROOT": "C:\\wrong-release",
        "LOKI_ENV_PATH": "C:\\wrong.env",
    }

    host.start()

    child_env = popen.calls[0][1]["env"]
    assert child_env["DISCORD_TOKEN"] == "process-secret"
    assert child_env["LOKI_APP_ROOT"] == str(host.release_root)
    assert child_env["LOKI_ENV_PATH"] == str(host.env_path)


def test_pythonservice_executable_selects_sibling_python(tmp_path):
    scripts_dir = tmp_path / "venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python_service = scripts_dir / "pythonservice.exe"
    python_service.write_bytes(b"")
    python_executable = scripts_dir / "python.exe"
    python_executable.write_bytes(b"")

    resolved = service_common.resolve_python_executable(python_service)

    assert resolved == python_executable.resolve()


def test_pythonservice_at_venv_root_selects_scripts_python(tmp_path):
    venv_root = tmp_path / "release-venv"
    venv_root.mkdir()
    python_service = venv_root / "pythonservice.exe"
    python_service.write_bytes(b"")
    python_executable = venv_root / "Scripts" / "python.exe"
    python_executable.parent.mkdir()
    python_executable.write_bytes(b"")

    resolved = service_common.resolve_python_executable(python_service)

    assert resolved == python_executable.resolve()


def test_relative_or_missing_runtime_paths_are_rejected(tmp_path):
    release_root, python_executable, env_path = prepare_release(tmp_path)
    with pytest.raises(ValueError, match="absolute"):
        service_common.ChildServiceHost(
            BOT_SERVICE_SPEC,
            release_root=Path("relative-release"),
            python_executable=python_executable,
            env_path=env_path,
        )
    with pytest.raises(FileNotFoundError, match="python"):
        service_common.ChildServiceHost(
            BOT_SERVICE_SPEC,
            release_root=release_root,
            python_executable=tmp_path / "missing" / "python.exe",
            env_path=env_path,
        )


def test_duplicate_process_is_refused_without_exposing_its_command(tmp_path):
    secret = "do-not-print-this-credential"
    duplicate = FakePsutilProcess(
        6789,
        ["python.exe", "C:\\old-release\\local_loki_runtime.py", "--token", secret],
    )
    host, _process, popen, _log = make_host(
        tmp_path,
        process_iter=lambda _attrs: [duplicate],
    )

    with pytest.raises(service_common.DuplicateProcessError) as error:
        host.start()

    assert popen.calls == []
    assert "6789" in str(error.value)
    assert secret not in str(error.value)


def test_graceful_stop_signals_then_waits_without_kill(tmp_path):
    host, process, _popen, _log = make_host(tmp_path)
    host.start()

    host.stop(timeout=30)

    if os.name == "nt":
        assert process.events == [("signal", signal.CTRL_BREAK_EVENT), ("wait", 30)]
    else:
        assert process.events == ["terminate", ("wait", 30)]


def test_stop_forces_kill_only_after_graceful_timeout(tmp_path):
    process = FakeProcess(time_out_once=True)
    host, process, _popen, _log = make_host(tmp_path, process=process)
    host.start()

    host.stop(timeout=30)

    graceful_request = ("signal", signal.CTRL_BREAK_EVENT) if os.name == "nt" else "terminate"
    assert process.events == [graceful_request, ("wait", 30), "kill", ("wait", 30)]


def test_unexpected_child_exit_raises_for_scm_recovery(tmp_path):
    process = FakeProcess(returncode=23)
    host, _process, _popen, _log = make_host(tmp_path, process=process)
    host.start()

    with pytest.raises(service_common.UnexpectedChildExit, match="23"):
        host.wait_for_exit()


def test_requested_child_exit_is_not_reported_as_failure(tmp_path):
    process = FakeProcess(returncode=0)
    host, _process, _popen, _log = make_host(tmp_path, process=process)
    host.start()
    host.stop_requested.set()

    assert host.wait_for_exit() == 0


def test_host_diagnostics_never_include_command_or_environment_secrets(tmp_path):
    diagnostics: list[str] = []
    host, _process, popen, _log = make_host(tmp_path, diagnostic_writer=diagnostics.append)
    secret = "credential-value-that-must-not-leak"
    host.base_environment = {"DISCORD_TOKEN": secret}

    host.start()

    assert popen.calls[0][1]["env"]["DISCORD_TOKEN"] == secret
    rendered = "\n".join(diagnostics)
    assert diagnostics == ["LokiTHESunGodBot: child started (pid=4321)"]
    assert secret not in rendered
    assert "DISCORD_TOKEN" not in rendered
    assert str(host.release_root) not in rendered


def test_service_classes_use_native_pywin32_framework_when_available():
    if os.name != "nt" or not service_common.PYWIN32_AVAILABLE:
        pytest.skip("pywin32 service framework is Windows-only")

    import win32serviceutil

    assert issubclass(LokiBotService, win32serviceutil.ServiceFramework)
    assert issubclass(LokiDashboardService, win32serviceutil.ServiceFramework)
    assert LokiBotService._svc_name_ == "LokiTHESunGodBot"
    assert LokiDashboardService._svc_name_ == "LokiTHESunGodDashboard"
