from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from scripts import windows_service_common as service_common
from scripts.loki_bot_service import BOT_SERVICE_SPEC, LokiBotService
from scripts.loki_dashboard_service import DASHBOARD_SERVICE_SPEC, LokiDashboardService
from utils import service_stop


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int = 0,
        wait_timeouts: int = 0,
        terminate_error: Exception | None = None,
        kill_error: Exception | None = None,
    ) -> None:
        self.pid = 4321
        self.returncode = returncode
        self.wait_timeouts = wait_timeouts
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.events: list[object] = []

    def terminate(self) -> None:
        self.events.append("terminate")
        if self.terminate_error:
            raise self.terminate_error

    def wait(self, timeout: float | None = None) -> int:
        self.events.append(("wait", timeout))
        if timeout is not None and self.wait_timeouts:
            self.wait_timeouts -= 1
            raise subprocess.TimeoutExpired("child", timeout)
        return self.returncode

    def kill(self) -> None:
        self.events.append("kill")
        if self.kill_error:
            raise self.kill_error


class FakeNamedStopEvent:
    def __init__(self, service_name: str, *, signal_error: Exception | None = None) -> None:
        self.name = f"Local\\{service_name}-unit-test"
        self.signal_error = signal_error
        self.signaled = False
        self.closed = False

    def signal(self) -> None:
        self.signaled = True
        if self.signal_error:
            raise self.signal_error

    def close(self) -> None:
        self.closed = True


class FakeNamedStopEventFactory:
    def __init__(self, *, signal_error: Exception | None = None) -> None:
        self.signal_error = signal_error
        self.events: list[FakeNamedStopEvent] = []

    def __call__(self, service_name: str) -> FakeNamedStopEvent:
        event = FakeNamedStopEvent(service_name, signal_error=self.signal_error)
        self.events.append(event)
        return event


class FakePopen:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs: object) -> FakeProcess:
        self.calls.append((command, kwargs))
        return self.process


class FakePsutilProcess:
    def __init__(self, pid: int, command: list[str] | None, *, cwd: str | None = None) -> None:
        self.pid = pid
        self.info = {"pid": pid, "cmdline": command, "cwd": cwd}


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
    stop_event_factory=None,
):
    release_root, python_executable, env_path = prepare_release(tmp_path)
    fake_process = process or FakeProcess()
    popen = FakePopen(fake_process)
    log_stream = io.StringIO()
    event_factory = stop_event_factory or FakeNamedStopEventFactory()
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
        stop_event_factory=event_factory,
    )
    host.test_stop_event_factory = event_factory
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
    assert kwargs["env"][service_stop.STOP_EVENT_ENV] == "Local\\LokiTHESunGodBot-unit-test"


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
        "LOKI_DB_PATH": "C:\\wrong.db",
        "PYTHONPYCACHEPREFIX": "C:\\wrong-cache",
    }

    host.start()

    child_env = popen.calls[0][1]["env"]
    assert child_env["DISCORD_TOKEN"] == "process-secret"
    assert child_env["LOKI_APP_ROOT"] == str(host.release_root)
    assert child_env["LOKI_ENV_PATH"] == str(host.env_path)
    assert child_env["LOKI_DB_PATH"] == str(host.program_data / "Loki" / "data" / "bot.db")
    assert child_env["PYTHONPYCACHEPREFIX"] == str(
        host.program_data / "Loki" / "cache" / "LokiTHESunGodBot"
    )
    assert (host.program_data / "Loki" / "data").is_dir()
    assert (host.program_data / "Loki" / "cache" / "LokiTHESunGodBot").is_dir()


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
        ["C:\\old-venv\\Scripts\\python.exe", "C:\\old-release\\local_loki_runtime.py", "--token", secret],
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


def test_duplicate_matching_ignores_editor_and_relative_test_commands(tmp_path):
    processes = [
        FakePsutilProcess(6001, ["C:\\Program Files\\Editor\\code.exe", "C:\\repo\\dashboard_app.py"]),
        FakePsutilProcess(6002, ["C:\\Python312\\python.exe", "tests\\dashboard_app.py"]),
    ]
    host, _process, popen, _log = make_host(
        tmp_path,
        DASHBOARD_SERVICE_SPEC,
        process_iter=lambda _attrs: processes,
    )

    host.start()

    assert len(popen.calls) == 1


def test_duplicate_matching_resolves_manual_relative_script_from_process_cwd(tmp_path):
    requested_attrs: list[list[str]] = []
    manual_runtime = FakePsutilProcess(
        6003,
        ["python.exe", "local_loki_runtime.py", "--mode", "full"],
        cwd="C:\\ProgramData\\Loki\\releases\\old-candidate",
    )

    def process_iter(attrs):
        requested_attrs.append(attrs)
        return [manual_runtime]

    host, _process, popen, _log = make_host(tmp_path, process_iter=process_iter)

    with pytest.raises(service_common.DuplicateProcessError, match="6003"):
        host.start()

    assert popen.calls == []
    assert requested_attrs == [["pid", "cmdline", "cwd"]]


def test_duplicate_matching_uses_script_argv_slot_not_later_absolute_argument(tmp_path):
    runner = FakePsutilProcess(
        6004,
        ["python.exe", "runner.py", "C:\\repo\\dashboard_app.py"],
        cwd="C:\\repo",
    )
    host, _process, popen, _log = make_host(
        tmp_path,
        DASHBOARD_SERVICE_SPEC,
        process_iter=lambda _attrs: [runner],
    )

    host.start()

    assert len(popen.calls) == 1


def test_duplicate_matching_accepts_unbuffered_option_before_relative_script(tmp_path):
    runtime = FakePsutilProcess(
        6005,
        ["python.exe", "-u", "local_loki_runtime.py", "--mode", "full"],
        cwd="C:\\ProgramData\\Loki\\releases\\old-candidate",
    )
    host, _process, popen, _log = make_host(
        tmp_path,
        process_iter=lambda _attrs: [runtime],
    )

    with pytest.raises(service_common.DuplicateProcessError, match="6005"):
        host.start()

    assert popen.calls == []


def test_duplicate_matching_accepts_x_option_value_before_dashboard_script(tmp_path):
    dashboard = FakePsutilProcess(
        6006,
        ["python.exe", "-X", "utf8", "dashboard_app.py"],
        cwd="C:\\ProgramData\\Loki\\releases\\old-candidate",
    )
    host, _process, popen, _log = make_host(
        tmp_path,
        DASHBOARD_SERVICE_SPEC,
        process_iter=lambda _attrs: [dashboard],
    )

    with pytest.raises(service_common.DuplicateProcessError, match="6006"):
        host.start()

    assert popen.calls == []


@pytest.mark.parametrize(
    "options",
    [
        ["-OOu"],
        ["-Xutf8"],
        ["-W", "ignore"],
        ["-Wignore"],
        ["--"],
    ],
)
def test_duplicate_matching_accepts_supported_interpreter_option_forms(tmp_path, options):
    runtime = FakePsutilProcess(
        6007,
        ["python.exe", *options, "local_loki_runtime.py"],
        cwd="C:\\ProgramData\\Loki\\releases\\old-candidate",
    )
    host, _process, _popen, _log = make_host(
        tmp_path,
        process_iter=lambda _attrs: [runtime],
    )

    with pytest.raises(service_common.DuplicateProcessError, match="6007"):
        host.start()


@pytest.mark.parametrize("mode_option", ["-c", "-m"])
def test_duplicate_matching_rejects_code_and_module_commands_with_later_script_argument(tmp_path, mode_option):
    command = FakePsutilProcess(
        6008,
        ["python.exe", mode_option, "print('runner')", "C:\\repo\\dashboard_app.py"],
        cwd="C:\\repo",
    )
    host, _process, popen, _log = make_host(
        tmp_path,
        DASHBOARD_SERVICE_SPEC,
        process_iter=lambda _attrs: [command],
    )

    host.start()

    assert len(popen.calls) == 1


def test_stop_during_start_barrier_prevents_child_launch(tmp_path):
    scan_entered = threading.Event()
    release_scan = threading.Event()

    def blocking_process_iter(_attrs):
        scan_entered.set()
        assert release_scan.wait(timeout=2)
        return []

    host, _process, popen, _log = make_host(tmp_path, process_iter=blocking_process_iter)
    errors: list[Exception] = []

    def start_host() -> None:
        try:
            host.start()
        except Exception as error:
            errors.append(error)

    start_thread = threading.Thread(target=start_host)
    start_thread.start()
    assert scan_entered.wait(timeout=2)

    host.stop()
    release_scan.set()
    start_thread.join(timeout=2)

    assert popen.calls == []
    assert len(errors) == 1
    assert isinstance(errors[0], service_common.ServiceStopRequested)


def test_run_returns_cleanly_when_stop_was_requested_before_launch(tmp_path):
    host, _process, popen, _log = make_host(tmp_path)
    host.stop()

    assert host.run() == 0
    assert popen.calls == []


def test_graceful_stop_sets_named_event_then_waits_without_kill(tmp_path):
    host, process, _popen, _log = make_host(tmp_path)
    host.start()
    named_event = host.test_stop_event_factory.events[0]

    host.stop(timeout=30)

    assert named_event.signaled is True
    assert named_event.closed is True
    assert process.events == [("wait", 30)]


def test_stop_forces_kill_only_after_graceful_timeout(tmp_path):
    process = FakeProcess(wait_timeouts=1)
    host, process, _popen, _log = make_host(tmp_path, process=process)
    host.start()

    host.stop(timeout=30)

    assert process.events == [("wait", 30), "kill", ("wait", 5)]


def test_stop_fallback_errors_are_tolerated_and_resources_always_close(tmp_path):
    event_factory = FakeNamedStopEventFactory(signal_error=OSError("sensitive event failure"))
    process = FakeProcess(terminate_error=ProcessLookupError("already exited"))
    host, _process, _popen, log_stream = make_host(
        tmp_path,
        process=process,
        stop_event_factory=event_factory,
    )
    host.start()

    host.stop(timeout=30)

    assert process.events == ["terminate", ("wait", 30)]
    assert event_factory.events[0].closed is True
    assert log_stream.closed is True


def test_stop_cleanup_runs_even_when_child_survives_force_kill(tmp_path):
    process = FakeProcess(wait_timeouts=2)
    host, _process, _popen, log_stream = make_host(tmp_path, process=process)
    host.start()
    named_event = host.test_stop_event_factory.events[0]

    with pytest.raises(subprocess.TimeoutExpired):
        host.stop(timeout=30)

    assert process.events == [("wait", 30), "kill", ("wait", 5)]
    assert named_event.closed is True
    assert log_stream.closed is True


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


def test_real_windows_named_event_stops_waiting_subprocess():
    if os.name != "nt" or not service_common.PYWIN32_AVAILABLE:
        pytest.skip("Windows named events require pywin32")

    named_event = service_common.WindowsNamedStopEvent("LokiNamedEventIntegrationTest")
    environment = dict(os.environ)
    environment[service_stop.STOP_EVENT_ENV] = named_event.name
    code = (
        "from utils.service_stop import wait_for_service_stop; "
        "raise SystemExit(0 if wait_for_service_stop(5000) else 2)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
    )
    try:
        named_event.signal()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
        named_event.close()


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


def test_svc_stop_returns_promptly_and_starts_only_one_stop_worker(monkeypatch):
    if os.name != "nt" or not service_common.PYWIN32_AVAILABLE:
        pytest.skip("native SCM control test requires pywin32")

    class BlockingHost:
        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()
            self.timeouts: list[float] = []
            self.request_stop_calls = 0

        def request_stop(self) -> None:
            self.request_stop_calls += 1

        def stop(self, timeout: float) -> None:
            self.timeouts.append(timeout)
            self.entered.set()
            assert self.release.wait(timeout=2)

    host = BlockingHost()
    reports: list[tuple[int, int]] = []
    wait_event_signals: list[object] = []
    monkeypatch.setattr(service_common.win32event, "SetEvent", wait_event_signals.append)
    service = object.__new__(service_common.NativeServiceFramework)
    service.service_spec = BOT_SERVICE_SPEC
    service.host = host
    service.hWaitStop = object()
    service._svc_stop_lock = threading.Lock()
    service._svc_stop_started = False
    service._svc_stop_worker = None
    service.ReportServiceStatus = lambda status, waitHint=0: reports.append((status, waitHint))

    caller = threading.Thread(target=service.SvcStop)
    caller.start()
    assert host.entered.wait(timeout=1)
    try:
        caller.join(timeout=0.25)
        assert not caller.is_alive(), "SCM control handler blocked on child shutdown"
        first_worker = service._svc_stop_worker
        assert first_worker is not None and first_worker.is_alive()

        repeated_callers = [threading.Thread(target=service.SvcStop) for _index in range(4)]
        for repeated_caller in repeated_callers:
            repeated_caller.start()
        for repeated_caller in repeated_callers:
            repeated_caller.join(timeout=1)
            assert not repeated_caller.is_alive()

        assert service._svc_stop_worker is first_worker
        assert host.timeouts == [30]
        assert host.request_stop_calls == 1
        assert all(wait_hint >= 40_000 for _status, wait_hint in reports)
    finally:
        host.release.set()
        caller.join(timeout=2)
        worker = service._svc_stop_worker
        if worker is not None:
            worker.join(timeout=2)

    service.SvcStop()
    assert service._svc_stop_worker is first_worker
    assert host.timeouts == [30]
    assert wait_event_signals == [service.hWaitStop]


def test_svc_stop_marks_intent_before_delayed_worker_can_run(tmp_path, monkeypatch):
    if os.name != "nt" or not service_common.PYWIN32_AVAILABLE:
        pytest.skip("native SCM control test requires pywin32")

    class DelayedWorker:
        def __init__(self, *, target, name, daemon) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            self.finished = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started and not self.finished

        def join(self, timeout=None) -> None:
            return

        def run_now(self) -> None:
            self.target()
            self.finished = True

    host, process, popen, _log = make_host(tmp_path, process=FakeProcess(returncode=17))
    wait_event_signals: list[object] = []
    monkeypatch.setattr(service_common.win32event, "SetEvent", wait_event_signals.append)
    monkeypatch.setattr(service_common.threading, "Thread", DelayedWorker)
    service = object.__new__(service_common.NativeServiceFramework)
    service.service_spec = BOT_SERVICE_SPEC
    service.host = host
    service.hWaitStop = object()
    service._svc_stop_lock = threading.Lock()
    service._svc_stop_started = False
    service._svc_stop_worker = None
    service.ReportServiceStatus = lambda _status, waitHint=0: None

    service.SvcStop()
    worker = service._svc_stop_worker
    assert worker is not None and worker.started and worker.is_alive()
    try:
        assert host.stop_requested.is_set()
        with pytest.raises(service_common.ServiceStopRequested):
            host.start()
        assert host.run() == 0
        assert popen.calls == []

        host.child = process
        assert host.wait_for_exit() == 17
    finally:
        worker.run_now()

    assert wait_event_signals == [service.hWaitStop]


def test_service_wrapper_imports_when_launched_outside_release_root(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "loki_bot_service.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    output = result.stdout + result.stderr
    assert "No module named 'utils'" not in output
    assert "Usage:" in output or "pywin32 is required" in output
