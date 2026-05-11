from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

LEASE_NAME = "loki-bot-worker"
LEASE_TTL_SECONDS = 45
LEASE_HEARTBEAT_SECONDS = 15
LOCAL_SHUTDOWN_TIMEOUT_SECONDS = 6


class DuplicateWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerLease:
    name: str
    owner_id: str


_ACTIVE_LEASE: WorkerLease | None = None
_HARD_SHUTDOWN_ENABLED = True
_HARD_SHUTDOWN_REQUESTED = False


def set_active_worker_lease(lease: WorkerLease) -> None:
    global _ACTIVE_LEASE
    _ACTIVE_LEASE = lease


def clear_active_worker_lease(lease: WorkerLease | None = None) -> None:
    global _ACTIVE_LEASE
    if lease is None or _ACTIVE_LEASE == lease:
        _ACTIVE_LEASE = None


def active_worker_lease() -> WorkerLease | None:
    return _ACTIVE_LEASE


def set_hard_shutdown_enabled(enabled: bool) -> bool:
    global _HARD_SHUTDOWN_ENABLED
    old = _HARD_SHUTDOWN_ENABLED
    _HARD_SHUTDOWN_ENABLED = enabled
    return old


def hard_shutdown_requested() -> bool:
    return _HARD_SHUTDOWN_REQUESTED


def clear_hard_shutdown_request() -> None:
    global _HARD_SHUTDOWN_REQUESTED
    _HARD_SHUTDOWN_REQUESTED = False


def request_hard_shutdown(reason: str) -> None:
    global _HARD_SHUTDOWN_REQUESTED
    _HARD_SHUTDOWN_REQUESTED = True
    if _HARD_SHUTDOWN_ENABLED:
        os._exit(70)


def _is_railway() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_DEPLOYMENT_ID",
            "RAILWAY_REPLICA_ID",
        )
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _workspace_key(path: str | Path | None) -> str:
    if not path:
        return ""
    raw = str(path).strip().replace("\\", "/")
    if len(raw) >= 2 and raw[1] == ":":
        win = PureWindowsPath(raw)
        drive = win.drive[:1].lower()
        tail = "/".join(win.parts[1:])
        raw = f"/mnt/{drive}/{tail}" if drive else tail
    try:
        raw = str(Path(raw).resolve()).replace("\\", "/")
    except Exception:
        pass
    return raw.casefold().rstrip("/")


def _same_workspace(path: str | Path | None, root: Path) -> bool:
    root_key = _workspace_key(root)
    path_key = _workspace_key(path)
    return bool(path_key and (path_key == root_key or path_key.endswith("/" + root.name.casefold())))


def _cmdline_is_bot_worker(cmdline: list[str]) -> bool:
    lowered = [part.casefold().replace("\\", "/") for part in cmdline]
    for index, part in enumerate(lowered[:-1]):
        if part == "-m" and lowered[index + 1] == "bot":
            return True
    return any(part.endswith("/bot.py") or part == "bot.py" for part in lowered)


def _process_is_same_workspace_bot(info: dict[str, Any], root: Path) -> bool:
    cmdline = list(info.get("cmdline") or [])
    if not cmdline or not _cmdline_is_bot_worker(cmdline):
        return False
    cwd = info.get("cwd")
    if _same_workspace(cwd, root):
        return True
    for part in cmdline:
        if not part.endswith(("bot.py", 'bot.py"')):
            continue
        parent = PureWindowsPath(part).parent if len(part) >= 2 and part[1] == ":" else Path(str(part)).parent
        if _same_workspace(parent, root):
            return True
    return False


def stop_local_duplicate_workers(root: Path | None = None) -> list[int]:
    if _is_railway():
        return []

    try:
        import psutil
    except ImportError:
        raise SystemExit("psutil is required to enforce LOKI THE SUN GOD local duplicate worker shutdown.")

    project_root = root or _project_root()
    current_pid = os.getpid()
    duplicates = []
    for proc in psutil.process_iter(["pid", "cmdline", "cwd", "create_time"]):
        try:
            if proc.pid == current_pid:
                continue
            if _process_is_same_workspace_bot(proc.info, project_root):
                duplicates.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    for proc in duplicates:
        with contextlib.suppress(Exception):
            proc.terminate()

    gone, alive = psutil.wait_procs(duplicates, timeout=LOCAL_SHUTDOWN_TIMEOUT_SECONDS)
    for proc in alive:
        with contextlib.suppress(Exception):
            proc.kill()
    if alive:
        psutil.wait_procs(alive, timeout=LOCAL_SHUTDOWN_TIMEOUT_SECONDS)

    return [proc.pid for proc in duplicates]


def _make_owner_id() -> str:
    railway_bits = [
        os.getenv("RAILWAY_SERVICE_ID", ""),
        os.getenv("RAILWAY_DEPLOYMENT_ID", ""),
        os.getenv("RAILWAY_REPLICA_ID", ""),
    ]
    environment = "railway" if _is_railway() else "local"
    identity = ":".join(bit for bit in railway_bits if bit) or socket.gethostname()
    return f"{environment}:{identity}:pid-{os.getpid()}:{int(time.time())}:{uuid.uuid4().hex[:12]}"


async def claim_worker_lease(owner_id: str | None = None, *, replace_existing: bool | None = None) -> WorkerLease:
    from utils import db
    from utils.guard_audit import record_guard_audit

    lease = WorkerLease(LEASE_NAME, owner_id or _make_owner_id())
    should_replace = _is_railway() if replace_existing is None else replace_existing
    now = int(time.time())
    expires_at = now + LEASE_TTL_SECONDS
    hostname = socket.gethostname()
    pid = os.getpid()
    row = None
    stolen_details: dict[str, Any] | None = None

    async with db.get() as conn:
        await conn.execute("DELETE FROM worker_leases WHERE expires_at<=?", (now,))
        cur = await conn.execute(
            "INSERT OR IGNORE INTO worker_leases(lease_name,owner_id,hostname,pid,started_at,heartbeat_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (lease.name, lease.owner_id, hostname, pid, now, now, expires_at),
        )
        await conn.commit()
        if cur.rowcount == 1:
            return lease

        row = await (
            await conn.execute(
                "SELECT owner_id, hostname, pid, heartbeat_at, expires_at FROM worker_leases WHERE lease_name=?",
                (lease.name,),
            )
        ).fetchone()
        if row and row[0] == lease.owner_id:
            renewed = await conn.execute(
                "UPDATE worker_leases SET hostname=?, pid=?, heartbeat_at=?, expires_at=? "
                "WHERE lease_name=? AND owner_id=?",
                (hostname, pid, now, expires_at, lease.name, lease.owner_id),
            )
            await conn.commit()
            if renewed.rowcount == 1:
                return lease

        if should_replace:
            replaced = await conn.execute(
                "UPDATE worker_leases SET owner_id=?, hostname=?, pid=?, started_at=?, heartbeat_at=?, expires_at=? "
                "WHERE lease_name=?",
                (lease.owner_id, hostname, pid, now, now, expires_at, lease.name),
            )
            await conn.commit()
            if replaced.rowcount == 1:
                if row:
                    stolen_details = {
                        "previous_owner_id": row[0],
                        "previous_hostname": row[1],
                        "previous_pid": row[2],
                        "previous_heartbeat_at": row[3],
                        "previous_expires_at": row[4],
                    }
                else:
                    stolen_details = {"previous_owner_id": "<unknown>"}
            else:
                row = await (
                    await conn.execute(
                        "SELECT owner_id, hostname, pid, heartbeat_at, expires_at "
                        "FROM worker_leases WHERE lease_name=?",
                        (lease.name,),
                    )
                ).fetchone()

    if stolen_details is not None:
        await record_guard_audit(
            "worker_lease",
            "lease_stolen",
            owner_id=lease.owner_id,
            details=stolen_details,
        )
        return lease

    if row:
        detail = f"owner={row[0]} host={row[1]} pid={row[2]} heartbeat={row[3]} expires={row[4]}"
    else:
        detail = "owner=<unknown>"
    raise DuplicateWorkerError(
        "LOKI THE SUN GOD worker singleton refused startup because another bot worker is active: "
        f"{detail}. Stop the duplicate worker or wait for its lease to expire."
    )


async def verify_active_worker_lease() -> tuple[bool, str, WorkerLease | None]:
    from utils import db

    lease = active_worker_lease()
    if lease is None:
        return False, "missing_active_lease", None
    try:
        async with db.get() as conn:
            row = await (
                await conn.execute(
                    "SELECT owner_id FROM worker_leases WHERE lease_name=?",
                    (lease.name,),
                )
            ).fetchone()
    except Exception:
        return False, "lease_check_error", lease
    if row and row[0] == lease.owner_id:
        return True, "ok", lease
    return False, "lease_lost", lease


async def renew_worker_lease(lease: WorkerLease) -> bool:
    from utils import db

    now = int(time.time())
    expires_at = now + LEASE_TTL_SECONDS
    async with db.get() as conn:
        cur = await conn.execute(
            "UPDATE worker_leases SET heartbeat_at=?, expires_at=? WHERE lease_name=? AND owner_id=?",
            (now, expires_at, lease.name, lease.owner_id),
        )
        await conn.commit()
    return cur.rowcount == 1


async def release_worker_lease(lease: WorkerLease) -> None:
    from utils import db

    async with db.get() as conn:
        await conn.execute(
            "DELETE FROM worker_leases WHERE lease_name=? AND owner_id=?",
            (lease.name, lease.owner_id),
        )
        await conn.commit()


async def maintain_worker_lease(lease: WorkerLease) -> None:
    from utils.guard_audit import record_guard_audit

    while True:
        await asyncio.sleep(LEASE_HEARTBEAT_SECONDS)
        try:
            renewed = await renew_worker_lease(lease)
        except Exception as exc:
            await record_guard_audit(
                "worker_lease",
                "heartbeat_error",
                owner_id=lease.owner_id,
                details={"error_type": type(exc).__name__},
            )
            request_hard_shutdown("worker lease heartbeat error")
            return
        if not renewed:
            await record_guard_audit(
                "worker_lease",
                "lease_lost_heartbeat",
                owner_id=lease.owner_id,
            )
            request_hard_shutdown("worker lease lost on heartbeat")
            return


async def self_check() -> None:
    from utils import db

    old_path = os.environ.get("LOKI_DB_PATH")
    old_database_url = os.environ.pop("DATABASE_URL", None)
    old_hard_shutdown = set_hard_shutdown_enabled(False)
    try:
        with tempfile.TemporaryDirectory(prefix="loki-worker-singleton-") as tmp:
            os.environ["LOKI_DB_PATH"] = str(Path(tmp) / "bot.db")
            await db.init()
            clear_hard_shutdown_request()
            first = await claim_worker_lease("test-worker-one", replace_existing=False)
            try:
                await claim_worker_lease("test-worker-two", replace_existing=False)
            except DuplicateWorkerError:
                pass
            else:
                raise AssertionError("worker singleton allowed a second active owner")

            second = await claim_worker_lease("test-worker-two", replace_existing=True)
            async with db.get() as conn:
                row = await (
                    await conn.execute("SELECT owner_id FROM worker_leases WHERE lease_name=?", (LEASE_NAME,))
                ).fetchone()
                audit_row = await (
                    await conn.execute(
                        "SELECT COUNT(*) FROM guard_audit WHERE event_type=? AND reason=?",
                        ("worker_lease", "lease_stolen"),
                    )
                ).fetchone()
            if not row or row[0] != second.owner_id:
                raise AssertionError("worker singleton takeover did not leave exactly one current owner")
            if not audit_row or audit_row[0] < 1:
                raise AssertionError("worker singleton takeover did not write a durable audit row")
            set_active_worker_lease(first)
            ok, reason, _ = await verify_active_worker_lease()
            if ok or reason != "lease_lost":
                raise AssertionError("stolen worker lease did not fence out the old owner")
            request_hard_shutdown("self-check lease loss")
            if not hard_shutdown_requested():
                raise AssertionError("worker singleton did not request shutdown after lease loss")

            clear_hard_shutdown_request()
            set_active_worker_lease(second)
            ok, reason, _ = await verify_active_worker_lease()
            if not ok:
                raise AssertionError(f"new worker lease owner did not verify: {reason}")
            if not await renew_worker_lease(second):
                raise AssertionError("worker singleton could not renew its active owner")
            await release_worker_lease(second)
            clear_active_worker_lease(second)

            root = _project_root()
            if not _process_is_same_workspace_bot({"cmdline": ["python", "-m", "bot"], "cwd": str(root)}, root):
                raise AssertionError("worker singleton did not match python -m bot")
            if not _process_is_same_workspace_bot(
                {"cmdline": ["python", str(root / "bot.py")], "cwd": str(root)}, root
            ):
                raise AssertionError("worker singleton did not match bot.py")
            if _process_is_same_workspace_bot({"cmdline": ["python", "-m", "dashboard_app"], "cwd": str(root)}, root):
                raise AssertionError("worker singleton matched a dashboard process as a bot worker")
    finally:
        set_hard_shutdown_enabled(old_hard_shutdown)
        clear_active_worker_lease()
        clear_hard_shutdown_request()
        if old_path is None:
            os.environ.pop("LOKI_DB_PATH", None)
        else:
            os.environ["LOKI_DB_PATH"] = old_path
        if old_database_url is not None:
            os.environ["DATABASE_URL"] = old_database_url


def run_self_check() -> None:
    asyncio.run(self_check())
