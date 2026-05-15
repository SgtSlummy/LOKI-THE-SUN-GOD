from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from utils import runtime_paths

APP_ROOT = runtime_paths.app_root()
MYTHOS_ROOT = APP_ROOT / ".mythos"
DEFAULT_RUN_SLUG = "loki-diva-reprocess"
MAX_OUTPUT_CHARS = 1_800
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_DIR_ACTIONS = {"init", "compile", "gate"}
CLI_ACTIONS = RUN_DIR_ACTIONS | {"ready"}
ALLOWED_SOURCE_HOSTS = {"github.com"}


class MythosRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class MythosCommandResult:
    action: str
    ok: bool
    returncode: int
    command: tuple[str, ...]
    stdout: str
    stderr: str
    run_dir: Path | None = None
    timed_out: bool = False

    @property
    def output(self) -> str:
        joined = "\n".join(part.strip() for part in (self.stdout, self.stderr) if part and part.strip()).strip()
        return joined[:MAX_OUTPUT_CHARS] if joined else "No output."


def default_run_slug() -> str:
    configured = (os.getenv("LOKI_MYTHOS_RUN_SLUG") or "").strip()
    return sanitize_run_slug(configured or DEFAULT_RUN_SLUG)


def sanitize_run_slug(value: str) -> str:
    slug = value.strip().lower()
    if not SLUG_PATTERN.fullmatch(slug):
        raise MythosRouterError(
            "Mythos run slug must be 1-64 chars and use lowercase letters, numbers, dots, dashes, or underscores."
        )
    return slug


def mythos_run_dir(run_slug: str | None = None) -> Path:
    slug = sanitize_run_slug(run_slug or default_run_slug())
    return MYTHOS_ROOT / slug


def mythos_sources_path(run_slug: str | None = None) -> Path:
    return mythos_run_dir(run_slug) / "sources.json"


def resolve_mythos_skill() -> str:
    executable = shutil.which("mythos-skill")
    if not executable:
        raise MythosRouterError("mythos-skill is not installed or is not on PATH for this bot process.")
    return str(Path(executable).expanduser().resolve())


def mythos_snapshot(run_slug: str | None = None) -> dict[str, Any]:
    run_dir = mythos_run_dir(run_slug)
    packet_path = run_dir / "state" / "next_pass_packet.json"
    packet_summary: dict[str, Any] = {}
    packet_error = ""
    source_error = ""
    sources: list[dict[str, Any]] = []
    if packet_path.exists():
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet_summary = {
                "pass_id": packet.get("pass_id") or packet.get("id") or packet.get("packet_id"),
                "keys": sorted(packet)[:12],
                "evidence_count": _safe_len(packet.get("evidence") or packet.get("worker_results")),
                "verifier_count": _safe_len(packet.get("verifiers") or packet.get("verifier_results")),
                "blocker_count": _safe_len(packet.get("blockers")),
            }
        except (OSError, json.JSONDecodeError) as exc:
            packet_error = str(exc)
    try:
        sources = load_mythos_sources(run_slug)
    except MythosRouterError as exc:
        source_error = str(exc)

    files = []
    if run_dir.exists():
        files = [str(path.relative_to(APP_ROOT)) for path in sorted(run_dir.glob("**/*")) if path.is_file()]

    return {
        "run_slug": run_dir.name,
        "run_dir": str(run_dir),
        "exists": run_dir.exists(),
        "packet_path": str(packet_path),
        "packet_exists": packet_path.exists(),
        "packet_summary": packet_summary,
        "packet_error": packet_error,
        "source_count": len(sources),
        "sources": sources,
        "source_error": source_error,
        "file_count": len(files),
        "files": files[:50],
        "prime_consumption_rule": "Read compiled packet only after ingest/compile/gate.",
        "allowed_actions": sorted(CLI_ACTIONS | {"add", "status"}),
    }


def load_mythos_sources(run_slug: str | None = None) -> list[dict[str, Any]]:
    path = mythos_sources_path(run_slug)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MythosRouterError(f"Mythos source manifest is unreadable: {exc}") from exc
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise MythosRouterError("Mythos source manifest must contain a sources list.")
    return [source for source in sources if isinstance(source, dict)]


def add_mythos_source(
    url: str,
    *,
    run_slug: str | None = None,
    note: str = "",
    added_by: str = "operator",
) -> dict[str, Any]:
    source = normalize_source_url(url)
    path = mythos_sources_path(run_slug)
    sources = load_mythos_sources(run_slug)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {
        "url": source["url"],
        "source_type": source["source_type"],
        "host": source["host"],
        "owner": source["owner"],
        "repo": source["repo"],
        "added_at": now,
        "added_by": str(added_by)[:120],
        "note": note.strip()[:500],
    }
    for index, existing in enumerate(sources):
        if existing.get("url") == record["url"]:
            record["first_added_at"] = existing.get("first_added_at") or existing.get("added_at") or now
            sources[index] = record
            break
    else:
        record["first_added_at"] = now
        sources.append(record)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sources": sources}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def normalize_source_url(url: str) -> dict[str, str]:
    raw = url.strip()
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if parsed.scheme != "https" or host not in ALLOWED_SOURCE_HOSTS:
        raise MythosRouterError("Mythos sources must be HTTPS GitHub repository URLs.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise MythosRouterError("GitHub source URL must include owner and repository.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not GITHUB_NAME_PATTERN.fullmatch(owner) or not GITHUB_NAME_PATTERN.fullmatch(repo):
        raise MythosRouterError("GitHub source owner and repo contain unsupported characters.")
    return {
        "url": f"https://github.com/{owner}/{repo}",
        "source_type": "github_repository",
        "host": host,
        "owner": owner,
        "repo": repo,
    }


def run_mythos_action(action: str, *, run_slug: str | None = None, timeout: int = 90) -> MythosCommandResult:
    normalized = action.strip().lower()
    if normalized not in CLI_ACTIONS:
        raise MythosRouterError(f"Unsupported Mythos action: {action}")

    executable = resolve_mythos_skill()
    run_dir = mythos_run_dir(run_slug) if normalized in RUN_DIR_ACTIONS else None
    source_manifest = _prepare_init_run_dir(run_dir) if normalized == "init" and run_dir is not None else None
    if normalized == "compile":
        _normalize_seed_synthesis_finding(run_dir)
    command = _command_for_action(executable, normalized, run_dir)

    try:
        result = subprocess.run(
            command,
            cwd=mythos_workdir(),
            capture_output=True,
            env=mythos_env(),
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _restore_init_sources(run_dir, source_manifest)
        return MythosCommandResult(
            action=normalized,
            ok=False,
            returncode=124,
            command=tuple(command),
            stdout=_expired_output(exc.stdout),
            stderr=_expired_output(exc.stderr) or f"mythos-skill {normalized} timed out after {timeout}s.",
            run_dir=run_dir,
            timed_out=True,
        )

    _restore_init_sources(run_dir, source_manifest)
    if normalized == "init" and result.returncode == 0:
        _normalize_seed_synthesis_finding(run_dir)
    return MythosCommandResult(
        action=normalized,
        ok=result.returncode == 0,
        returncode=result.returncode,
        command=tuple(command),
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        run_dir=run_dir,
    )


def _prepare_init_run_dir(run_dir: Path | None) -> str | None:
    if run_dir is None or not run_dir.exists():
        return None
    entries = list(run_dir.iterdir())
    if any(entry.name != "sources.json" for entry in entries):
        return None
    source_manifest = run_dir / "sources.json"
    payload = source_manifest.read_text(encoding="utf-8") if source_manifest.exists() else None
    shutil.rmtree(run_dir)
    return payload


def _restore_init_sources(run_dir: Path | None, payload: str | None) -> None:
    if run_dir is None or payload is None:
        return
    source_manifest = run_dir / "sources.json"
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_manifest.write_text(payload, encoding="utf-8")


def _normalize_seed_synthesis_finding(run_dir: Path | None) -> None:
    """Keep Rust `mythos init` output compatible with JS record-synthesis."""
    if run_dir is None:
        return
    findings_path = run_dir / "verifier-results" / "findings.jsonl"
    if not findings_path.exists():
        return
    records: list[dict[str, Any]] = []
    changed = False
    try:
        lines = findings_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(record, dict):
            return
        records.append(record)

    has_codex_pending = any(record.get("id") == "vf-codex-synthesis-pending" for record in records)
    normalized: list[dict[str, Any]] = []
    for record in records:
        if record.get("id") != "vf-synthesis-pending":
            normalized.append(record)
            continue
        changed = True
        if has_codex_pending:
            continue
        normalized.append(
            {
                **record,
                "id": "vf-codex-synthesis-pending",
                "summary": record.get("summary") or "Codex synthesis has not consumed this packet yet",
            }
        )
        has_codex_pending = True

    if changed:
        findings_path.write_text(
            "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in normalized),
            encoding="utf-8",
        )


def mythos_env() -> dict[str, str]:
    env = dict(os.environ)
    path_entries: list[str] = []
    local_bin = _local_mythos_bin_dir()
    if local_bin is not None:
        path_entries.append(str(local_bin))
    if not shutil.which("node", path=env.get("PATH", "")):
        path_entries.extend(str(path) for path in _node_bin_dirs(env))
    if path_entries:
        existing_path = env.get("PATH", "")
        path_entries.extend(entry for entry in existing_path.split(os.pathsep) if entry)
        env["PATH"] = os.pathsep.join(dict.fromkeys(path_entries))
    return env


def _local_mythos_bin_dir() -> Path | None:
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    candidate = Path(local_appdata) / "mythos-skill-src" / "mythos-compiler" / "target" / "debug"
    executable = candidate / ("mythos.exe" if os.name == "nt" else "mythos")
    return candidate if executable.exists() else None


def _node_bin_dirs(env: dict[str, str] | None = None) -> list[Path]:
    values = env or os.environ
    candidates: list[Path] = []

    for key in ("ProgramFiles", "LOCALAPPDATA", "ProgramFiles(x86)"):
        root = (values.get(key) or "").strip()
        if not root:
            continue
        candidates.append(Path(root) / "nodejs")

    if os.name != "nt":
        candidates.extend(
            [
                Path("/mnt/c/Program Files/nodejs"),
                Path("/mnt/c/Users") / (values.get("USERNAME") or "") / "AppData/Local/Programs/nodejs",
                Path("/mnt/c/Program Files (x86)/nodejs"),
            ]
        )

    discovered: list[Path] = []
    for candidate in candidates:
        node_binary = candidate / ("node.exe" if candidate.drive or candidate.suffix == ".exe" or os.name == "nt" else "node")
        if node_binary.exists():
            discovered.append(candidate)
    return discovered


def mythos_workdir() -> Path:
    override = (os.getenv("LOKI_MYTHOS_WORKDIR") or "").strip()
    if override:
        return Path(override)
    if " " not in str(APP_ROOT):
        return APP_ROOT
    link = Path(tempfile.gettempdir()) / "loki-mythos-workdir"
    if link.exists():
        return link
    if os.name == "nt":
        link.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(APP_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise MythosRouterError(f"Could not create no-space Mythos workdir junction: {detail}")
        return link
    try:
        link.symlink_to(APP_ROOT, target_is_directory=True)
    except OSError as exc:
        raise MythosRouterError(f"Could not create no-space Mythos workdir symlink: {exc}") from exc
    return link


def _command_for_action(executable: str, action: str, run_dir: Path | None) -> list[str]:
    if action == "ready":
        return [executable, "ready"]
    if run_dir is None:
        raise MythosRouterError(f"Mythos action {action} requires a run directory.")
    cli_run_dir = _cli_run_dir(run_dir)
    if action == "init":
        return [executable, "init", cli_run_dir]
    if action == "compile":
        return [executable, "compile", "--run-dir", cli_run_dir]
    if action == "gate":
        return [executable, "gate", "--run-dir", cli_run_dir]
    raise MythosRouterError(f"Unsupported Mythos action: {action}")


def _cli_run_dir(run_dir: Path) -> str:
    try:
        return str(run_dir.relative_to(APP_ROOT))
    except ValueError:
        return str(run_dir)


def _safe_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _expired_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
