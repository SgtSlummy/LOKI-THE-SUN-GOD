from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TextIO

import psutil

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:  # pragma: no cover - exercised by Ubuntu CI collection
    servicemanager = None
    win32event = None
    win32service = None
    win32serviceutil = None


PYWIN32_AVAILABLE = all(
    module is not None for module in (servicemanager, win32event, win32service, win32serviceutil)
)
DEFAULT_ENV_RELATIVE_PATH = Path("Loki") / "config" / "lokithesungod.env"
DEFAULT_LOG_RELATIVE_PATH = Path("Loki") / "logs"


class DuplicateProcessError(RuntimeError):
    """Raised when a service would start a second copy of its child."""


class UnexpectedChildExit(RuntimeError):
    """Raised so an unexpected child exit becomes an SCM-visible failure."""


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


def _command_contains_script(command: Iterable[object], script_name: str) -> bool:
    expected = script_name.casefold()
    for value in command:
        normalized = str(value).strip('"').replace("\\", "/")
        if normalized.rsplit("/", 1)[-1].casefold() == expected:
            return True
    return False


def find_duplicate_process(
    script_name: str,
    *,
    process_iter: Callable[[list[str]], Iterable[Any]] = psutil.process_iter,
    current_pid: int | None = None,
) -> int | None:
    own_pid = os.getpid() if current_pid is None else current_pid
    for process in process_iter(["pid", "cmdline"]):
        try:
            if process.pid == own_pid:
                continue
            command = process.info.get("cmdline") or []
            if _command_contains_script(command, script_name):
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
        self.stop_requested = threading.Event()
        self.child: Any | None = None
        self._log_handle: TextIO | None = None

        script_path = self.release_root / self.spec.script_name
        if not script_path.is_file():
            raise FileNotFoundError(f"service child script does not exist: {script_path}")
        if self.spec.script_name.casefold() == "desktop_app.py":
            raise ValueError("desktop_app.py cannot run as a Windows service")

    @property
    def command(self) -> list[str]:
        return [
            str(self.python_executable),
            str(self.release_root / self.spec.script_name),
            *self.spec.arguments,
        ]

    @property
    def child_environment(self) -> dict[str, str]:
        environment = dict(self.base_environment)
        environment["LOKI_APP_ROOT"] = str(self.release_root)
        environment["LOKI_ENV_PATH"] = str(self.env_path)
        environment.update(self.spec.environment)
        return environment

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    def start(self) -> Any:
        if self.child is not None:
            raise RuntimeError(f"{self.spec.service_name} child already started")
        duplicate_pid = find_duplicate_process(
            self.spec.script_name,
            process_iter=self.process_iter,
        )
        if duplicate_pid is not None:
            raise DuplicateProcessError(
                f"{self.spec.service_name} refused duplicate child process (pid={duplicate_pid})"
            )

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_opener(
            self.log_path,
            "a",
            encoding="utf-8",
            buffering=1,
        )
        try:
            self.child = self.popen_factory(
                self.command,
                cwd=str(self.release_root),
                env=self.child_environment,
                stdin=subprocess.DEVNULL,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                creationflags=self._creation_flags(),
            )
        except Exception:
            self._close_log()
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
        self.start()
        try:
            return self.wait_for_exit()
        finally:
            self._close_log()

    def stop(self, timeout: float = 30) -> None:
        self.stop_requested.set()
        child = self.child
        if child is None:
            return
        self.diagnostic_writer(f"{self.spec.service_name}: stopping child")
        try:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                child.terminate()
        except (OSError, ProcessLookupError):
            child.terminate()

        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.diagnostic_writer(f"{self.spec.service_name}: forcing child stop after timeout")
            child.kill()
            child.wait(timeout=timeout)
        finally:
            self._close_log()

    def _close_log(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


if PYWIN32_AVAILABLE:

    class NativeServiceFramework(win32serviceutil.ServiceFramework):
        service_spec: ClassVar[ServiceSpec]

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.host = ChildServiceHost(
                self.service_spec,
                diagnostic_writer=servicemanager.LogInfoMsg,
            )

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=30_000)
            try:
                self.host.stop(timeout=30)
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
