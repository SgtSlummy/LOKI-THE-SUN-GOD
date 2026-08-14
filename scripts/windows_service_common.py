from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, ClassVar, TextIO

import psutil

try:
    import servicemanager
    import win32api
    import win32event
    import win32service
    import win32serviceutil
except ImportError:  # pragma: no cover - exercised by Ubuntu CI collection
    servicemanager = None
    win32api = None
    win32event = None
    win32service = None
    win32serviceutil = None


PYWIN32_AVAILABLE = all(
    module is not None for module in (servicemanager, win32api, win32event, win32service, win32serviceutil)
)
DEFAULT_ENV_RELATIVE_PATH = Path("Loki") / "config" / "lokithesungod.env"
DEFAULT_LOG_RELATIVE_PATH = Path("Loki") / "logs"
DEFAULT_DB_RELATIVE_PATH = Path("Loki") / "data" / "bot.db"
DEFAULT_CACHE_RELATIVE_PATH = Path("Loki") / "cache"
STOP_EVENT_ENV = "LOKI_SERVICE_STOP_EVENT"


class DuplicateProcessError(RuntimeError):
    """Raised when a service would start a second copy of its child."""


class UnexpectedChildExit(RuntimeError):
    """Raised so an unexpected child exit becomes an SCM-visible failure."""


class ServiceStopRequested(RuntimeError):
    """Raised when SCM stop wins the race with child launch."""


class WindowsNamedStopEvent:
    def __init__(self, service_name: str) -> None:
        if not PYWIN32_AVAILABLE:
            raise RuntimeError("pywin32 is required for Windows named service events")
        self.name = f"Local\\{service_name}-{os.getpid()}-{uuid.uuid4().hex}"
        self._handle = win32event.CreateEvent(None, True, False, self.name)

    def signal(self) -> None:
        if self._handle is not None:
            win32event.SetEvent(self._handle)

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            win32api.CloseHandle(handle)


class InProcessNamedStopEvent:
    """Non-Windows test shim; native services never use this implementation."""

    def __init__(self, service_name: str) -> None:
        self.name = f"Local\\{service_name}-{os.getpid()}-{uuid.uuid4().hex}"
        self._event = threading.Event()

    def signal(self) -> None:
        self._event.set()

    def close(self) -> None:
        return


def create_named_stop_event(service_name: str) -> WindowsNamedStopEvent | InProcessNamedStopEvent:
    if PYWIN32_AVAILABLE and os.name == "nt":
        return WindowsNamedStopEvent(service_name)
    return InProcessNamedStopEvent(service_name)


@dataclass(frozen=True)
class ServiceSpec:
    service_name: str
    display_name: str
    description: str
    script_name: str
    arguments: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    log_name: str = "service.log"


def default_program_data() -> Path:
    configured = os.environ.get("PROGRAMDATA")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(r"C:\ProgramData")


def _resolve_absolute(path: str | os.PathLike[str], label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return candidate.resolve()


def resolve_release_root(release_root: str | os.PathLike[str] | None = None) -> Path:
    candidate = release_root if release_root is not None else Path(__file__).resolve().parents[1]
    resolved = _resolve_absolute(candidate, "release root")
    if not resolved.is_dir():
        raise FileNotFoundError(f"release root does not exist: {resolved}")
    return resolved


def resolve_python_executable(executable: str | os.PathLike[str] | None = None) -> Path:
    candidate = _resolve_absolute(executable or sys.executable, "python executable")
    if candidate.name.casefold() == "pythonservice.exe":
        sibling_python = candidate.with_name("python.exe")
        venv_scripts_python = candidate.parent / "Scripts" / "python.exe"
        candidate = sibling_python if sibling_python.is_file() else venv_scripts_python
    if not candidate.is_file():
        raise FileNotFoundError(f"python executable does not exist: {candidate}")
    if candidate.name.casefold() not in {"python.exe", "python"}:
        raise ValueError("service child executable must be python.exe")
    return candidate


def _path_name(value: object) -> str:
    return str(value).strip('"').replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _absolute_command_path(
    value: object,
    cwd: object | None = None,
) -> Path | PureWindowsPath | None:
    text = str(value).strip('"')
    native_path = Path(text)
    if native_path.is_absolute():
        return native_path
    windows_path = PureWindowsPath(text)
    if windows_path.is_absolute():
        return windows_path
    if cwd is None:
        return None

    cwd_text = str(cwd).strip('"')
    native_cwd = Path(cwd_text)
    if native_cwd.is_absolute():
        return native_cwd / native_path
    windows_cwd = PureWindowsPath(cwd_text)
    if windows_cwd.is_absolute():
        return windows_cwd / windows_path
    return None


def _python_script_argument(command: list[object]) -> object | None:
    simple_flags = frozenset("bBdEiIOPqRsSuvx")
    index = 1
    while index < len(command):
        argument = str(command[index]).strip('"')
        if argument == "--":
            return command[index + 1] if index + 1 < len(command) else None
        if argument in {"-c", "-m"} or argument.startswith(("-c", "-m")):
            return None
        if argument in {"-X", "-W"}:
            index += 2
            continue
        if argument.startswith(("-X", "-W")) and len(argument) > 2:
            index += 1
            continue
        if argument.startswith("-") and len(argument) > 1 and all(
            flag in simple_flags for flag in argument[1:]
        ):
            index += 1
            continue
        if argument.startswith("-"):
            return None
        return command[index]
    return None


def _command_is_service_child(
    command: Iterable[object],
    script_name: str,
    *,
    cwd: object | None = None,
    expected_script: object | None = None,
    managed_release_bases: Iterable[object] = (),
) -> bool:
    values = list(command)
    release_bases = tuple(managed_release_bases)
    if len(values) < 2:
        return False
    if _path_name(values[0]) not in {"python", "python.exe", "pythonw.exe"}:
        return False
    script_argument = _python_script_argument(values)
    if script_argument is None:
        return False
    target_script = _absolute_command_path(script_argument, cwd)
    if target_script is None or target_script.name.casefold() != script_name.casefold():
        return False
    if expected_script is None and not release_bases:
        return True
    if expected_script is not None and _path_identity(target_script) == _path_identity(expected_script):
        return True
    target_identity = _path_identity(target_script)
    for base in release_bases:
        base_identity = _path_identity(base)
        if target_identity[0] != base_identity[0]:
            continue
        relative_parts = target_identity[1][len(base_identity[1]) :]
        if target_identity[1][: len(base_identity[1])] == base_identity[1] and len(relative_parts) == 2:
            return relative_parts[0].startswith("loki-") and relative_parts[-1] == script_name.casefold()
    return False


def _path_identity(value: object) -> tuple[str, tuple[str, ...]]:
    text = str(value).strip('"')
    windows_path = PureWindowsPath(text)
    if windows_path.is_absolute():
        return "windows", tuple(part.casefold() for part in windows_path.parts)
    native_path = Path(text)
    return "native", tuple(part.casefold() for part in native_path.parts)


def find_duplicate_process(
    script_name: str,
    *,
    expected_script: object | None = None,
    managed_release_bases: Iterable[object] = (),
    process_iter: Callable[[list[str]], Iterable[Any]] = psutil.process_iter,
    current_pid: int | None = None,
) -> int | None:
    own_pid = os.getpid() if current_pid is None else current_pid
    for process in process_iter(["pid", "cmdline", "cwd"]):
        try:
            if process.pid == own_pid:
                continue
            command = process.info.get("cmdline") or []
            if _command_is_service_child(
                command,
                script_name,
                cwd=process.info.get("cwd"),
                expected_script=expected_script,
                managed_release_bases=managed_release_bases,
            ):
                return int(process.pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return None


class ChildServiceHost:
    def __init__(
        self,
        spec: ServiceSpec,
        *,
        release_root: str | os.PathLike[str] | None = None,
        python_executable: str | os.PathLike[str] | None = None,
        env_path: str | os.PathLike[str] | None = None,
        program_data: str | os.PathLike[str] | None = None,
        base_environment: Mapping[str, str] | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        process_iter: Callable[[list[str]], Iterable[Any]] = psutil.process_iter,
        log_opener: Callable[..., TextIO] = open,
        diagnostic_writer: Callable[[str], None] | None = None,
        stop_event_factory: Callable[[str], Any] = create_named_stop_event,
    ) -> None:
        self.spec = spec
        self.release_root = resolve_release_root(release_root)
        self.python_executable = resolve_python_executable(python_executable)
        self.env_path = _resolve_absolute(
            env_path or (default_program_data() / DEFAULT_ENV_RELATIVE_PATH),
            "environment path",
        )
        if not self.env_path.is_file():
            raise FileNotFoundError(f"environment config does not exist: {self.env_path}")
        self.program_data = _resolve_absolute(program_data or default_program_data(), "ProgramData path")
        self.log_path = self.program_data / DEFAULT_LOG_RELATIVE_PATH / spec.log_name
        self.base_environment = dict(os.environ if base_environment is None else base_environment)
        self.popen_factory = popen_factory
        self.process_iter = process_iter
        self.log_opener = log_opener
        self.diagnostic_writer = diagnostic_writer or (lambda _message: None)
        self.stop_event_factory = stop_event_factory
        self.stop_requested = threading.Event()
        self.child: Any | None = None
        self._log_handle: TextIO | None = None
        self._stop_event: Any | None = None
        self._lifecycle = "new"
        self._lifecycle_lock = threading.RLock()

        self.script_path = self.release_root / self.spec.script_name
        if not self.script_path.is_file():
            raise FileNotFoundError(f"service child script does not exist: {self.script_path}")
        if self.spec.script_name.casefold() == "desktop_app.py":
            raise ValueError("desktop_app.py cannot run as a Windows service")

    @property
    def command(self) -> list[str]:
        return [
            str(self.python_executable),
            str(self.script_path),
            *self.spec.arguments,
        ]

    @property
    def child_environment(self) -> dict[str, str]:
        environment = dict(self.base_environment)
        environment.update(self.spec.environment)
        environment["LOKI_APP_ROOT"] = str(self.release_root)
        environment["LOKI_ENV_PATH"] = str(self.env_path)
        environment["LOKI_DB_PATH"] = str(self.program_data / DEFAULT_DB_RELATIVE_PATH)
        environment["PYTHONPYCACHEPREFIX"] = str(
            self.program_data / DEFAULT_CACHE_RELATIVE_PATH / self.spec.service_name
        )
        environment["LOKI_LOCAL_ALLOW_FULL"] = "true"
        environment["RELAY_ENABLED"] = "false"
        environment["LOKI_ENABLE_SLASH_SYNC"] = "false"
        if self._stop_event is not None:
            environment[STOP_EVENT_ENV] = self._stop_event.name
        return environment

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def start(self) -> Any:
        with self._lifecycle_lock:
            if self.stop_requested.is_set() or self._lifecycle in {"stopping", "stopped"}:
                raise ServiceStopRequested(f"{self.spec.service_name} stop requested before launch")
            if self._lifecycle != "new" or self.child is not None:
                raise RuntimeError(f"{self.spec.service_name} child already started")
            self._lifecycle = "starting"

        try:
            duplicate_pid = find_duplicate_process(
                self.spec.script_name,
                expected_script=self.script_path,
                managed_release_bases=(
                    self.program_data / "Loki" / "releases",
                    PureWindowsPath(r"C:\ProgramData\Loki\releases"),
                ),
                process_iter=self.process_iter,
            )
            with self._lifecycle_lock:
                if self.stop_requested.is_set() or self._lifecycle == "stopping":
                    self._lifecycle = "stopped"
                    raise ServiceStopRequested(f"{self.spec.service_name} stop requested before launch")
                if duplicate_pid is not None:
                    self._lifecycle = "failed"
                    raise DuplicateProcessError(
                        f"{self.spec.service_name} refused duplicate child process (pid={duplicate_pid})"
                    )

                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                (self.program_data / DEFAULT_DB_RELATIVE_PATH).parent.mkdir(parents=True, exist_ok=True)
                (self.program_data / DEFAULT_CACHE_RELATIVE_PATH / self.spec.service_name).mkdir(
                    parents=True,
                    exist_ok=True,
                )
                self._log_handle = self.log_opener(
                    self.log_path,
                    "a",
                    encoding="utf-8",
                    buffering=1,
                )
                self._stop_event = self.stop_event_factory(self.spec.service_name)
                self.child = self.popen_factory(
                    self.command,
                    cwd=str(self.release_root),
                    env=self.child_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=self._creation_flags(),
                )
                self._lifecycle = "running"
        except Exception:
            with self._lifecycle_lock:
                if self._lifecycle not in {"stopped", "failed"}:
                    self._lifecycle = "failed"
            self._cleanup_resources()
            raise
        self.diagnostic_writer(f"{self.spec.service_name}: child started (pid={self.child.pid})")
        return self.child

    def wait_for_exit(self) -> int:
        if self.child is None:
            raise RuntimeError(f"{self.spec.service_name} child has not started")
        exit_code = int(self.child.wait())
        if not self.stop_requested.is_set():
            self.diagnostic_writer(
                f"{self.spec.service_name}: child exited unexpectedly (code={exit_code})"
            )
            raise UnexpectedChildExit(
                f"{self.spec.service_name} child exited unexpectedly with code {exit_code}"
            )
        return exit_code

    def run(self) -> int:
        try:
            self.start()
        except ServiceStopRequested:
            self._cleanup_resources()
            return 0
        try:
            return self.wait_for_exit()
        finally:
            self._cleanup_resources()

    def request_stop(self) -> None:
        with self._lifecycle_lock:
            self.stop_requested.set()
            if self._lifecycle != "stopped":
                self._lifecycle = "stopping"

    def stop(self, timeout: float = 30) -> None:
        self.request_stop()
        try:
            with self._lifecycle_lock:
                child = self.child
                stop_event = self._stop_event
            if child is None:
                return

            self.diagnostic_writer(f"{self.spec.service_name}: stopping child")
            try:
                if stop_event is None:
                    raise RuntimeError("named stop event unavailable")
                stop_event.signal()
            except Exception:
                try:
                    child.terminate()
                except Exception:
                    pass

            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.diagnostic_writer(f"{self.spec.service_name}: forcing child stop after timeout")
                try:
                    child.kill()
                except Exception:
                    pass
                child.wait(timeout=5)
        finally:
            with self._lifecycle_lock:
                self._lifecycle = "stopped"
            self._cleanup_resources()

    def _cleanup_resources(self) -> None:
        with self._lifecycle_lock:
            log_handle, self._log_handle = self._log_handle, None
            stop_event, self._stop_event = self._stop_event, None
        if log_handle is not None:
            try:
                log_handle.close()
            except Exception:
                pass
        if stop_event is not None:
            try:
                stop_event.close()
            except Exception:
                pass


if PYWIN32_AVAILABLE:

    class NativeServiceFramework(win32serviceutil.ServiceFramework):
        service_spec: ClassVar[ServiceSpec]

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self._svc_stop_lock = threading.Lock()
            self._svc_stop_started = False
            self._svc_stop_worker: threading.Thread | None = None
            self.host = ChildServiceHost(
                self.service_spec,
                diagnostic_writer=servicemanager.LogInfoMsg,
            )

        def SvcStop(self) -> None:
            with self._svc_stop_lock:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=40_000)
                if self._svc_stop_started:
                    return
                self.host.request_stop()
                self._svc_stop_started = True
                worker = threading.Thread(
                    target=self._stop_child_worker,
                    name=f"{self.service_spec.service_name}-stop",
                    daemon=True,
                )
                self._svc_stop_worker = worker
                worker.start()

        def _stop_child_worker(self) -> None:
            try:
                self.host.stop(timeout=30)
            except Exception as error:
                servicemanager.LogErrorMsg(
                    f"{self.service_spec.service_name}: child stop failed ({type(error).__name__})"
                )
            finally:
                win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self) -> None:
            servicemanager.LogInfoMsg(f"{self.service_spec.service_name}: service starting")
            try:
                self.host.run()
            except Exception as error:
                servicemanager.LogErrorMsg(
                    f"{self.service_spec.service_name}: service failed ({type(error).__name__})"
                )
                raise

else:

    class NativeServiceFramework:  # pragma: no cover - non-Windows import shim
        service_spec: ClassVar[ServiceSpec]

        def __init__(self, _args: list[str]) -> None:
            raise RuntimeError("pywin32 is required to run Loki Windows services")


def handle_command_line(service_class: type[NativeServiceFramework]) -> int:
    if not PYWIN32_AVAILABLE:
        raise RuntimeError("pywin32 is required to install or run Loki Windows services")
    win32serviceutil.HandleCommandLine(service_class)
    return 0
