from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import logging
import os
import random
import re
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from aiohttp import ClientError, ClientSession, ClientTimeout
from dotenv import load_dotenv

DISCORD_IDENTIFY_LIMIT_PER_24H = 1000
DEFAULT_MAX_RESTARTS_PER_24H = 20
DEFAULT_HEALTH_URL = "http://127.0.0.1:8080/healthz"


@dataclass(frozen=True)
class HealthResult:
    healthy: bool
    reason: str


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    command_line: str
    cwd: str | None = None
    name: str | None = None


@dataclass
class RestartPolicy:
    failure_threshold: int = 6
    max_restarts_per_24h: int = DEFAULT_MAX_RESTARTS_PER_24H
    base_restart_delay_seconds: float = 30.0
    max_restart_delay_seconds: float = 900.0
    consecutive_failures: int = 0
    restart_times: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.max_restarts_per_24h < 1:
            raise ValueError("max_restarts_per_24h must be >= 1")
        if self.max_restarts_per_24h >= DISCORD_IDENTIFY_LIMIT_PER_24H:
            raise ValueError("max_restarts_per_24h must remain below Discord's 1000 Identify/day limit")

    def record_health(self, result: HealthResult, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._prune_old_restarts(now)
        if result.healthy:
            self.consecutive_failures = 0
            return False
        self.consecutive_failures += 1
        return self.consecutive_failures >= self.failure_threshold and self.can_restart(now=now)

    def can_restart(self, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._prune_old_restarts(now)
        return len(self.restart_times) < self.max_restarts_per_24h

    def record_restart(self, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._prune_old_restarts(now)
        self.restart_times.append(now)
        self.consecutive_failures = 0

    def next_restart_delay(self) -> float:
        exponent = max(0, len(self.restart_times) - 1)
        delay = min(self.base_restart_delay_seconds * (2**exponent), self.max_restart_delay_seconds)
        jitter = random.uniform(0, max(1.0, delay * 0.1))
        return delay + jitter

    def _prune_old_restarts(self, now: float) -> None:
        cutoff = now - 24 * 60 * 60
        while self.restart_times and self.restart_times[0] <= cutoff:
            self.restart_times.popleft()


def build_default_bot_command() -> list[str]:
    return [sys.executable, "-m", "bot.main"]


def _normalize_for_process_match(value: str | Path) -> str:
    return str(value).replace("\\", "/").lower()


def find_duplicate_loki_processes(
    processes: Sequence[ProcessInfo],
    *,
    current_pid: int,
    project_dir: Path,
) -> list[ProcessInfo]:
    """Return running Loki bot/guardian processes for this checkout, excluding current_pid."""

    project_marker = _normalize_for_process_match(project_dir.resolve())
    module_pattern = re.compile(r"(?:^|\s)-m\s+(?:bot\.main|scripts\.loki_guardian)(?:\s|$)")
    duplicates: list[ProcessInfo] = []
    for process in processes:
        if process.pid == current_pid:
            continue
        command_line = _normalize_for_process_match(process.command_line)
        cwd = _normalize_for_process_match(process.cwd) if process.cwd else ""
        name = _normalize_for_process_match(process.name) if process.name else ""
        if name and not ("python" in name or "loki" in name):
            continue
        matches_project = project_marker in command_line or cwd == project_marker
        looks_like_loki = bool(module_pattern.search(command_line)) or any(
            marker in command_line
            for marker in ("bot/main.py", "scripts/loki_guardian", "loki_guardian.py", "loki-guardian")
        )
        if looks_like_loki and matches_project:
            duplicates.append(process)
    return duplicates


def list_running_processes() -> list[ProcessInfo]:
    psutil_processes = _list_processes_with_psutil()
    if psutil_processes:
        return psutil_processes
    if os.name == "nt":
        powershell_processes = _list_windows_processes_with_powershell()
        if powershell_processes:
            return powershell_processes
        return _list_windows_processes()
    return _list_posix_processes()


def _list_processes_with_psutil() -> list[ProcessInfo]:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return []
    processes: list[ProcessInfo] = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            info = process.info
            pid = int(info.get("pid") or 0)
            cmdline = info.get("cmdline") or []
            command_line = " ".join(str(part) for part in cmdline)
            cwd = info.get("cwd")
        except (psutil.Error, OSError, ValueError):
            continue
        if pid and command_line:
            name = info.get("name")
            processes.append(ProcessInfo(pid=pid, command_line=command_line, cwd=str(cwd) if cwd else None, name=str(name) if name else None))
    return processes


def _list_windows_processes_with_powershell() -> list[ProcessInfo]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,CommandLine,ExecutablePath | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    processes: list[ProcessInfo] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        command_line = str(row.get("CommandLine") or "").strip()
        if not command_line:
            continue
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid:
            name = row.get("Name")
            processes.append(ProcessInfo(pid=pid, command_line=command_line, name=str(name) if name else None))
    return processes


def _list_windows_processes() -> list[ProcessInfo]:
    try:
        result = subprocess.run(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    processes: list[ProcessInfo] = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        command_line = (row.get("CommandLine") or "").strip()
        pid_raw = (row.get("ProcessId") or "").strip()
        if not command_line or not pid_raw:
            continue
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        processes.append(ProcessInfo(pid=pid, command_line=command_line))
    return processes


def _list_posix_processes() -> list[ProcessInfo]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    processes: list[ProcessInfo] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_raw, _, command_line = stripped.partition(" ")
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        if command_line:
            processes.append(ProcessInfo(pid=pid, command_line=command_line))
    return processes


def format_duplicate_processes(processes: Sequence[ProcessInfo]) -> str:
    return "; ".join(f"pid={process.pid} cmd={redact_text(process.command_line)}" for process in processes)


def redact_text(text: str) -> str:
    patterns = [
        (r"(?i)(DISCORD_TOKEN\s*=\s*)\S+", r"\1<redacted>"),
        (r"(?i)(Authorization\s*:\s*Bot\s+)\S+", r"\1<redacted>"),
        (r"(?i)(\bBot\s+)[A-Za-z0-9._-]{20,}", r"\1<redacted>"),
        (r"(?i)(api[_-]?key\s*=\s*)\S+", r"\1<redacted>"),
        (r"(?i)(password\s*=\s*)\S+", r"\1<redacted>"),
        (r"(?i)(token\s*=\s*)\S+", r"\1<redacted>"),
    ]
    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def redact_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    skip_value = False
    secret_flags = {"--token", "--discord-token", "--api-key", "--password"}
    for part in command:
        if skip_value:
            redacted.append("<redacted>")
            skip_value = False
            continue
        lowered = part.lower()
        if lowered in secret_flags:
            redacted.append(part)
            skip_value = True
            continue
        if "token=" in lowered or "api_key=" in lowered or "password=" in lowered:
            key = part.split("=", 1)[0]
            redacted.append(f"{key}=<redacted>")
            continue
        redacted.append(part)
    return redacted


def evaluate_health_payload(payload: dict[str, object]) -> HealthResult:
    if payload.get("ok") is not True:
        return HealthResult(False, "health payload ok=false")
    if payload.get("discord_connected") is not True:
        return HealthResult(False, "Discord gateway is not connected")
    if payload.get("db_connected") is False:
        return HealthResult(False, "database health check failed")
    return HealthResult(True, "ok")


class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self._handle: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        while True:
            try:
                self._handle = os.open(str(self.path), flags)
            except FileExistsError as exc:
                if self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise RuntimeError(f"Guardian lock already exists at {self.path}") from exc
            os.write(self._handle, str(os.getpid()).encode("utf-8"))
            return

    def _is_stale(self) -> bool:
        try:
            raw_pid = self.path.read_text(encoding="utf-8").strip()
            pid = int(raw_pid)
        except (OSError, ValueError):
            return True
        if pid <= 0:
            return True
        if pid == os.getpid():
            return False
        try:
            os.kill(pid, 0)
        except (OSError, SystemError, ValueError):
            return True
        return False

    def release(self) -> None:
        if self._handle is not None:
            os.close(self._handle)
            self._handle = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class LokiGuardian:
    def __init__(
        self,
        *,
        command: Sequence[str],
        project_dir: Path,
        health_url: str = DEFAULT_HEALTH_URL,
        check_interval_seconds: float = 30.0,
        startup_grace_seconds: float = 90.0,
        restart_policy: RestartPolicy | None = None,
        log_path: Path | None = None,
    ):
        self.command = list(command)
        self.project_dir = project_dir
        self.health_url = health_url
        self.check_interval_seconds = check_interval_seconds
        self.startup_grace_seconds = startup_grace_seconds
        self.restart_policy = restart_policy or RestartPolicy()
        self.log_path = log_path or project_dir / "logs" / "loki-guardian.log"
        self.process: asyncio.subprocess.Process | None = None
        self.restart_count = 0
        self._stopping = False
        self._last_start_time = 0.0
        self.logger = logging.getLogger("loki.guardian")
        self._configure_logging()

    def _configure_logging(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.logger.handlers:
            return
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)

    async def run(self, *, max_runtime_seconds: float | None = None) -> None:
        deadline = time.monotonic() + max_runtime_seconds if max_runtime_seconds else None
        await self.start_bot()
        try:
            while not self._stopping:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                await asyncio.sleep(self.check_interval_seconds)
                await self.check_once()
        finally:
            await self.stop_bot()

    async def start_bot(self) -> None:
        self._last_start_time = time.monotonic()
        self.logger.info("Starting Loki bot: %s", " ".join(redact_command(self.command)))
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        asyncio.create_task(self._pump_output(self.process))

    async def stop_bot(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        self.logger.info("Stopping Loki bot gracefully")
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            self.logger.warning("Loki bot did not stop gracefully; killing process")
            self.process.kill()
            await self.process.wait()

    async def check_once(self) -> None:
        if self.process is None:
            await self._restart("process handle missing")
            return
        return_code = self.process.returncode
        if return_code is None:
            try:
                return_code = self.process.returncode if self.process.returncode is not None else await self._poll_returncode()
            except Exception:
                return_code = None
        if return_code is not None:
            await self._restart(f"bot process exited with code {return_code}")
            return

        if not self.health_url:
            return
        if time.monotonic() - self._last_start_time < self.startup_grace_seconds:
            return
        health = await self.fetch_health()
        if self.restart_policy.record_health(health):
            await self._restart(f"health check failed: {health.reason}")
        elif not health.healthy:
            self.logger.warning(
                "Health check failed (%s/%s): %s",
                self.restart_policy.consecutive_failures,
                self.restart_policy.failure_threshold,
                health.reason,
            )

    async def _poll_returncode(self) -> int | None:
        assert self.process is not None
        try:
            return await asyncio.wait_for(self.process.wait(), timeout=0.01)
        except asyncio.TimeoutError:
            return None

    async def fetch_health(self) -> HealthResult:
        timeout = ClientTimeout(total=10.0)
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.get(self.health_url) as response:
                    text = await response.text()
                    if response.status >= 500:
                        return HealthResult(False, f"health endpoint returned HTTP {response.status}")
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        return HealthResult(False, "health endpoint returned non-JSON")
        except (asyncio.TimeoutError, ClientError, OSError) as exc:
            return HealthResult(False, f"health endpoint request failed: {exc}")
        if not isinstance(payload, dict):
            return HealthResult(False, "health endpoint returned unexpected JSON")
        return evaluate_health_payload(payload)

    async def _restart(self, reason: str) -> None:
        now = time.time()
        if not self.restart_policy.can_restart(now=now):
            self.logger.error(
                "Restart blocked after %s restarts in 24h to avoid Discord Identify-limit churn. Reason: %s",
                len(self.restart_policy.restart_times),
                reason,
            )
            self._stopping = True
            return
        self.restart_policy.record_restart(now=now)
        self.restart_count += 1
        delay = self.restart_policy.next_restart_delay()
        self.logger.warning("Restarting Loki bot in %.1fs: %s", delay, reason)
        await self.stop_bot()
        await asyncio.sleep(delay)
        if not self._stopping:
            await self.start_bot()

    async def _pump_output(self, process: asyncio.subprocess.Process) -> None:
        if process.stdout is None:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            self.logger.info("bot: %s", redact_text(line.decode("utf-8", errors="replace").rstrip()))


def default_health_url() -> str:
    explicit = os.getenv("LOKI_GUARDIAN_HEALTH_URL")
    if explicit:
        return explicit
    port = os.getenv("HEALTH_PORT") or os.getenv("PORT") or "8080"
    return f"http://127.0.0.1:{port}/healthz"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description="Keep the Loki Discord bot running with conservative restart safeguards.")
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--health-url", default=default_health_url())
    parser.add_argument("--check-interval", type=float, default=float(os.getenv("LOKI_GUARDIAN_CHECK_INTERVAL", "30")))
    parser.add_argument("--startup-grace", type=float, default=float(os.getenv("LOKI_GUARDIAN_STARTUP_GRACE", "90")))
    parser.add_argument("--failure-threshold", type=int, default=int(os.getenv("LOKI_GUARDIAN_FAILURE_THRESHOLD", "6")))
    parser.add_argument("--max-restarts-per-24h", type=int, default=int(os.getenv("LOKI_GUARDIAN_MAX_RESTARTS_PER_24H", str(DEFAULT_MAX_RESTARTS_PER_24H))))
    parser.add_argument("--base-restart-delay", type=float, default=float(os.getenv("LOKI_GUARDIAN_BASE_RESTART_DELAY", "30")))
    parser.add_argument("--max-restart-delay", type=float, default=float(os.getenv("LOKI_GUARDIAN_MAX_RESTART_DELAY", "900")))
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--lock-path", type=Path, default=None)
    parser.add_argument("--skip-duplicate-process-check", action="store_true")
    parser.add_argument("--", dest="separator", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Optional bot command; default: python -m bot.main")
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = args.command or build_default_bot_command()
    policy = RestartPolicy(
        failure_threshold=args.failure_threshold,
        max_restarts_per_24h=args.max_restarts_per_24h,
        base_restart_delay_seconds=args.base_restart_delay,
        max_restart_delay_seconds=args.max_restart_delay,
    )
    project_dir = args.project_dir.resolve()
    lock_path = args.lock_path or project_dir / "logs" / "loki-guardian.lock"
    lock = SingleInstanceLock(lock_path)
    guardian = LokiGuardian(
        command=command,
        project_dir=project_dir,
        health_url=args.health_url,
        check_interval_seconds=args.check_interval,
        startup_grace_seconds=args.startup_grace,
        restart_policy=policy,
        log_path=args.log_path,
    )

    def request_stop() -> None:
        guardian._stopping = True

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, request_stop)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        lock.acquire()
        if not args.skip_duplicate_process_check:
            duplicates = find_duplicate_loki_processes(
                list_running_processes(),
                current_pid=os.getpid(),
                project_dir=project_dir,
            )
            if duplicates:
                raise RuntimeError(
                    "Duplicate Loki process(es) detected for this checkout; refusing to start another Discord bot session: "
                    f"{format_duplicate_processes(duplicates)}"
                )
        await guardian.run()
    except RuntimeError as exc:
        guardian.logger.error("%s", exc)
        return 2
    finally:
        lock.release()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
