"""
LOKI THE SUN GOD Desktop — native control panel.

Tabs:
    Services  — start/stop/restart processes, live logs
    LOKI THE SUN GOD   — quick toggles + slash actions against the running bot
    Dashboards — embedded iframes for every web UI you wire up

Process model: spawns LOKI THE SUN GOD (bot.py), Dashboard (dashboard_app.py) and
the local dashboard control surface. Managed children are killed on close.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psutil
import webview
from flask import Flask, Response, jsonify, render_template_string, request, send_file

from utils import runtime_paths
from utils.dashboard_theme import DASHBOARD_BRAND

# ─── Paths ────────────────────────────────────────────────────────────────
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INSTALL_DIR = (
    Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
)
APP_DIR = INSTALL_DIR
HERE = INSTALL_DIR
CONFIG_PATH = Path(os.getenv("LOKI_DESKTOP_CONFIG_PATH", INSTALL_DIR / "desktop_config.json"))
ICON_PATH = INSTALL_DIR / "icon.png"
APP_LOG_PATH = INSTALL_DIR / "desktop_runtime.log"
SINGLE_INSTANCE_SOCKET: Optional[socket.socket] = None
WORKSPACE_CONFIG_KEY = "workspace_root"
MEE6_DASHBOARD_URL = "https://mee6.xyz/en/dashboard/1463393482306486387"


def _path_from_config_value(value: object) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value.strip().strip('"').strip("'")).expanduser()


def _has_workspace_files(path: Path) -> bool:
    return (path / "bot.py").exists() and (path / ".env").exists()


def _configured_workspace_root() -> Optional[Path]:
    if not CONFIG_PATH.exists():
        return None
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _path_from_config_value(config.get(WORKSPACE_CONFIG_KEY))


def _resolve_workspace_root() -> Path:
    env_root = _path_from_config_value(os.getenv("LOKI_APP_ROOT"))
    candidates = [
        env_root,
        _configured_workspace_root(),
        Path("C:/LOKI THE SUN GOD"),
        INSTALL_DIR,
        Path.cwd(),
        runtime_paths.SOURCE_ROOT,
    ]
    for candidate in candidates:
        if candidate is not None and _has_workspace_files(candidate):
            return candidate.resolve()
    return INSTALL_DIR.resolve()


WORKSPACE_ROOT = _resolve_workspace_root()
ROOT = WORKSPACE_ROOT


def configure_workspace_environment() -> None:
    os.environ["LOKI_APP_ROOT"] = str(WORKSPACE_ROOT)
    os.environ["LOKI_ENV_PATH"] = str(WORKSPACE_ROOT / ".env")
    os.environ["LOKI_DB_PATH"] = str(WORKSPACE_ROOT / "data" / "bot.db")
    os.environ["LOKI_COMMAND_ROOT"] = str(WORKSPACE_ROOT)
    os.environ["LOKI_DOCS_PATH"] = str(WORKSPACE_ROOT / "docs")
    os.environ["LOKI_AI_DOCS_PATH"] = str(WORKSPACE_ROOT / "docs" / "ai_library")
    os.environ["LOKI_RUNTIME_LOG_PATH"] = str(APP_LOG_PATH)


if getattr(sys, "frozen", False) or __name__ == "__main__":
    configure_workspace_environment()

from utils import operator_surface  # noqa: E402


def service_command(mode: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, mode]
    if mode == "--run-bot":
        return [sys.executable, "-m", "bot"]
    if mode == "--run-dashboard":
        return [sys.executable, "dashboard_app.py"]
    raise ValueError(f"unknown mode: {mode}")


def append_runtime_log(message: str):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with APP_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except Exception:
        pass


# ─── Default config ───────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    WORKSPACE_CONFIG_KEY: str(WORKSPACE_ROOT),
    "services": [
        {
            "id": "loki",
            "label": f"{DASHBOARD_BRAND['name']} Bot",
            "cmd": service_command("--run-bot"),
            "cwd": str(ROOT),
            "auto_start": True,
        },
        {
            "id": "dash",
            "label": f"{DASHBOARD_BRAND['name']} Web Dashboard",
            "cmd": service_command("--run-dashboard"),
            "cwd": str(ROOT),
            "auto_start": True,
        },
    ],
    "dashboards": [
        {
            "id": "loki_web",
            "label": DASHBOARD_BRAND["dashboard_title"],
            "url": "http://localhost:5000",
            "icon": "ui-checks",
            "color": "blurple",
        },
        {"id": "router9", "label": "9router", "url": "http://localhost:20128", "icon": "diagram-3", "color": "mint"},
        {
            "id": "discord_dev",
            "label": "Discord Developer Portal",
            "url": "https://discord.com/developers/applications",
            "icon": "discord",
            "color": "blurple",
        },
        {
            "id": "mee6_dashboard",
            "label": "MEE6 Dashboard",
            "url": MEE6_DASHBOARD_URL,
            "icon": "robot",
            "color": "amber",
        },
    ],
    "control_port": 7331,
    "app_lock_port": 7332,
    "test_guild_id": "1463393482306486387",
}

MANAGED_SERVICE_DEFAULTS = {svc["id"]: svc for svc in DEFAULT_CONFIG["services"] if svc["id"] in {"loki", "dash"}}
REMOVED_DASHBOARD_IDS = {"loki_cr"}


def is_removed_dashboard(dashboard: dict) -> bool:
    dashboard_id = str(dashboard.get("id") or "").strip()
    label = str(dashboard.get("label") or "").lower().replace("·", "-")
    url = str(dashboard.get("url") or "").lower()
    return (
        dashboard_id in REMOVED_DASHBOARD_IDS
        or ("9router" in label and "claude" in label)
        or "/dashboard/claude-router" in url
    )


def sanitize_dashboards(dashboards: list[dict]) -> list[dict]:
    defaults_by_id = {dashboard["id"]: dashboard for dashboard in DEFAULT_CONFIG["dashboards"]}
    merged: list[dict] = []
    seen: set[str] = set()
    for dashboard in dashboards:
        if not isinstance(dashboard, dict) or is_removed_dashboard(dashboard):
            continue
        dashboard_id = str(dashboard.get("id") or "").strip()
        if not dashboard_id or dashboard_id in seen:
            continue
        default = defaults_by_id.get(dashboard_id)
        merged.append({**dashboard, **default} if default else dashboard)
        seen.add(dashboard_id)
    for dashboard in DEFAULT_CONFIG["dashboards"]:
        if dashboard["id"] not in seen:
            merged.append(dashboard.copy())
            seen.add(dashboard["id"])
    return merged


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # merge defaults non-destructively
            for k, v in DEFAULT_CONFIG.items():
                existing.setdefault(k, v)
            workspace_root = _path_from_config_value(existing.get(WORKSPACE_CONFIG_KEY))
            if workspace_root is None or not _has_workspace_files(workspace_root):
                existing[WORKSPACE_CONFIG_KEY] = str(WORKSPACE_ROOT)
            # keep managed service launch commands current across source/frozen modes
            services = []
            seen_ids = set()
            for svc in existing.get("services", []):
                svc_id = svc.get("id")
                if svc_id == "millhouse":
                    continue
                if svc_id in MANAGED_SERVICE_DEFAULTS:
                    merged = {
                        **svc,
                        **{
                            "label": MANAGED_SERVICE_DEFAULTS[svc_id]["label"],
                            "cmd": MANAGED_SERVICE_DEFAULTS[svc_id]["cmd"],
                            "cwd": str(WORKSPACE_ROOT),
                            "auto_start": MANAGED_SERVICE_DEFAULTS[svc_id]["auto_start"],
                        },
                    }
                    services.append(merged)
                    seen_ids.add(svc_id)
                else:
                    services.append(svc)
            for svc_id, default in MANAGED_SERVICE_DEFAULTS.items():
                if svc_id not in seen_ids:
                    services.append(default.copy())
            existing["services"] = services
            existing["dashboards"] = sanitize_dashboards(existing.get("dashboards", []))
            CONFIG_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            return existing
        except Exception:
            pass
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {**DEFAULT_CONFIG, "dashboards": sanitize_dashboards(DEFAULT_CONFIG["dashboards"])}
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


# ─── Service manager ──────────────────────────────────────────────────────
@dataclass
class Service:
    id: str
    label: str
    cmd: list[str]
    cwd: str
    auto_start: bool = False
    proc: Optional[subprocess.Popen] = field(default=None, repr=False)
    log: deque = field(default_factory=lambda: deque(maxlen=2000))
    listeners: list[queue.Queue] = field(default_factory=list, repr=False)
    started_at: Optional[float] = None
    restarts: int = 0
    attached_pid: Optional[int] = None

    def _attached_process(self) -> Optional[psutil.Process]:
        if not self.attached_pid:
            return None
        try:
            proc = psutil.Process(self.attached_pid)
            if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                self.attached_pid = None
                return None
            return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.attached_pid = None
            return None

    def find_existing_pid(self) -> Optional[int]:
        markers: dict[str, list[tuple[str, ...]]] = {
            "loki": [
                ("--run-bot",),
                ("-m", "bot"),
                ("bot.py",),
            ],
            "dash": [
                ("--run-dashboard",),
                ("dashboard_app.py",),
            ],
        }
        patterns = markers.get(self.id, [])
        if not patterns:
            return None

        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                if proc.pid == os.getpid():
                    continue
                cmdline_raw = proc.info.get("cmdline") or []
                cmdline = [part.lower() for part in cmdline_raw]
                if not cmdline:
                    continue
                for pattern in patterns:
                    pattern_lower = tuple(part.lower() for part in pattern)
                    if len(pattern_lower) == 1:
                        needle = pattern_lower[0]
                        if any(Path(part).name.lower() == needle or part == needle for part in cmdline_raw):
                            return proc.pid
                    else:
                        for idx in range(len(cmdline) - len(pattern_lower) + 1):
                            if tuple(cmdline[idx : idx + len(pattern_lower)]) == pattern_lower:
                                return proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def is_running(self) -> bool:
        if self.proc is not None and self.proc.poll() is None:
            return True
        return self._attached_process() is not None

    def status(self) -> dict:
        attached = self._attached_process()
        d = {
            "id": self.id,
            "label": self.label,
            "running": self.is_running(),
            "pid": self.proc.pid
            if self.proc is not None and self.proc.poll() is None
            else (attached.pid if attached else None),
            "restarts": self.restarts,
            "uptime": int(time.time() - self.started_at) if self.is_running() and self.started_at else 0,
            "cmd": " ".join(self.cmd),
            "cwd": self.cwd,
            "attached": attached is not None and self.proc is None,
        }
        if self.is_running():
            try:
                p = psutil.Process(d["pid"])
                d["cpu"] = p.cpu_percent(interval=0.0)
                d["mem_mb"] = round(p.memory_info().rss / 1024 / 1024, 1)
            except Exception:
                pass
        return d

    def start(self):
        if self.is_running():
            append_runtime_log(f"{self.id}: start skipped because service is already running")
            return
        existing_pid = self.find_existing_pid()
        if existing_pid:
            self.attached_pid = existing_pid
            self.started_at = None
            self.log.append(f"--- attached to existing process PID {existing_pid} ---")
            append_runtime_log(f"{self.id}: attached to existing process pid={existing_pid}")
            return
        creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.attached_pid = None
        env = os.environ.copy()
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
        self.started_at = time.time()
        append_runtime_log(
            f"{self.id}: started pid={self.proc.pid} cwd={self.cwd} "
            f"workspace={env.get('LOKI_APP_ROOT', '')} env_path={env.get('LOKI_ENV_PATH', '')} "
            f"cmd={' '.join(self.cmd)}"
        )
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        if not self.proc or self.proc.stdout is None:
            return
        for line in iter(self.proc.stdout.readline, ""):
            entry = f"{time.strftime('%H:%M:%S')} {line.rstrip()}"
            self.log.append(entry)
            for q in list(self.listeners):
                try:
                    q.put_nowait(entry)
                except queue.Full:
                    pass
        rc = None
        if self.proc:
            try:
                rc = self.proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                rc = self.proc.poll()
        msg = f"--- exited code {rc} ---"
        self.log.append(msg)
        append_runtime_log(f"{self.id}: exited code={rc}")
        for q in list(self.listeners):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def stop(self, timeout: float = 5.0):
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            append_runtime_log(f"{self.id}: stopping pid={self.proc.pid}")
            self.proc.terminate() if os.name == "nt" else self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                append_runtime_log(f"{self.id}: force killing pid={self.proc.pid}")
                self.proc.kill()
        except Exception as e:
            self.log.append(f"--- stop error: {e} ---")
            append_runtime_log(f"{self.id}: stop error {e}")

    def restart(self):
        if self._attached_process() is not None and self.proc is None:
            self.log.append("--- restart skipped: service is attached to an external process ---")
            append_runtime_log(f"{self.id}: restart skipped for attached external process")
            return
        self.stop()
        self.restarts += 1
        time.sleep(0.4)
        self.start()


class ServiceManager:
    def __init__(self, cfg: dict):
        self.services: dict[str, Service] = {}
        for s in cfg.get("services", []):
            self.services[s["id"]] = Service(
                id=s["id"], label=s["label"], cmd=s["cmd"], cwd=s["cwd"], auto_start=s.get("auto_start", False)
            )

    def auto_start(self):
        for s in self.services.values():
            if s.auto_start:
                try:
                    s.start()
                except Exception as e:
                    s.log.append(f"--- start failed: {e} ---")

    def stop_all(self):
        for s in self.services.values():
            s.stop()


# ─── LOKI DB helpers (read-only convenience for the desktop) ────────────
DB_PATH = ROOT / "data" / "bot.db"
DOCS_PATH = ROOT / "docs"
AI_DOCS_PATH = DOCS_PATH / "ai_library"
CODEX_SETTINGS_PATH = Path.home() / ".Codex" / "settings.json"


def db_query(sql: str, params: tuple = ()) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_exec(sql: str, params: tuple = ()) -> int:
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def parse_command_catalog() -> list[dict]:
    return operator_surface.command_library()


def option_library() -> dict:
    return operator_surface.option_library()


def read_env_file() -> dict:
    env_path = ROOT / ".env"
    values = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(name: str) -> Optional[str]:
    return os.getenv(name) or read_env_file().get(name)


def http_json(url: str, headers: Optional[dict] = None, timeout: int = 4) -> Optional[dict]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discord_headers() -> Optional[dict]:
    token = env_value("DISCORD_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bot {token}", "User-Agent": "LOKI THE SUN GODDesktop/1.0"}


def fetch_discord_channels(guild_id: int) -> tuple[list[dict], Optional[str]]:
    headers = discord_headers()
    if not headers:
        return [], "DISCORD_TOKEN is not configured."
    try:
        data = http_json(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, timeout=8)
        return data or [], None
    except Exception as exc:
        return [], str(exc)


def channel_name_map(channels: list[dict]) -> dict[str, str]:
    names = {}
    for channel in channels:
        channel_id = channel.get("id")
        if not channel_id:
            continue
        name = channel.get("name") or f"Channel {channel_id}"
        names[str(channel_id)] = name
    return names


def group_channels(channels: list[dict]) -> list[dict]:
    categories = {ch["id"]: ch.get("name", "Category") for ch in channels if ch.get("type") == 4}
    clusters: dict[str, dict] = {}
    for ch in channels:
        if ch.get("type") == 4:
            continue
        bucket = classify_channel_bucket(ch)
        parent_id = ch.get("parent_id")
        cluster_id = str(parent_id or bucket)
        cluster = clusters.setdefault(
            cluster_id,
            {
                "id": cluster_id,
                "label": categories.get(parent_id) or bucket.replace("_", " ").title(),
                "bucket": bucket,
                "channels": [],
            },
        )
        cluster["channels"].append(
            {
                "id": ch.get("id"),
                "name": ch.get("name", "channel"),
                "kind": channel_kind_label(ch.get("type")),
                "topic": ch.get("topic") or "",
                "position": ch.get("position", 0),
                "nsfw": bool(ch.get("nsfw")),
            }
        )

    ordered = []
    for cluster in clusters.values():
        cluster["channels"] = sorted(
            cluster["channels"], key=lambda item: (item["kind"], item["position"], item["name"])
        )
        ordered.append(cluster)
    return sorted(ordered, key=lambda item: (bucket_rank(item["bucket"]), item["label"].lower()))


def saved_channel_clusters(guild_id: int) -> list[dict]:
    cfg = (
        db_query(
            "SELECT log_channel, welcome_channel, starboard_channel FROM guild_config WHERE guild_id=?", (guild_id,)
        )
        or [{}]
    )[0]
    forms = db_query(
        "SELECT target_channel_id FROM forms WHERE guild_id=? AND target_channel_id IS NOT NULL", (guild_id,)
    )
    streams = db_query(
        "SELECT target_channel_id FROM stream_subs WHERE guild_id=? AND target_channel_id IS NOT NULL", (guild_id,)
    )
    stickies = db_query("SELECT channel_id FROM stickies WHERE guild_id=?", (guild_id,))

    buckets = [
        (
            "system",
            "Configured channels",
            [
                ("Log channel", cfg.get("log_channel")),
                ("Welcome channel", cfg.get("welcome_channel")),
                ("Starboard channel", cfg.get("starboard_channel")),
            ],
        ),
        (
            "forms",
            "Form delivery",
            [(f"Form target {idx + 1}", row.get("target_channel_id")) for idx, row in enumerate(forms)],
        ),
        (
            "streams",
            "Stream alerts",
            [(f"Stream target {idx + 1}", row.get("target_channel_id")) for idx, row in enumerate(streams)],
        ),
        ("text", "Sticky channels", [(f"Sticky {idx + 1}", row.get("channel_id")) for idx, row in enumerate(stickies)]),
    ]

    clusters = []
    for bucket, label, items in buckets:
        channels = []
        seen = set()
        for name, channel_id in items:
            if not channel_id or channel_id in seen:
                continue
            seen.add(channel_id)
            channels.append(
                {
                    "id": channel_id,
                    "name": name,
                    "kind": "Saved ID",
                    "topic": "Stored in LOKI THE SUN GOD configuration. Add DISCORD_TOKEN for live channel names and categories.",
                    "position": len(channels),
                    "nsfw": False,
                }
            )
        if channels:
            clusters.append({"id": f"saved-{bucket}", "label": label, "bucket": bucket, "channels": channels})
    return clusters


def classify_channel_bucket(channel: dict) -> str:
    channel_type = channel.get("type")
    name = (channel.get("name") or "").lower()
    if channel_type in {2, 13}:
        return "voice"
    if channel_type == 5:
        return "announcements"
    if any(token in name for token in ("side", "lounge", "hangout", "off-topic", "chat")):
        return "side_chat"
    if channel_type in {0, 11, 12, 15, 16}:
        return "text"
    return "other"


def channel_kind_label(channel_type: Optional[int]) -> str:
    return {
        0: "Text",
        2: "Voice",
        4: "Category",
        5: "Announcement",
        11: "Thread",
        12: "Private thread",
        13: "Stage",
        15: "Forum",
        16: "Media",
    }.get(channel_type, "Other")


def bucket_rank(bucket: str) -> int:
    order = {"text": 0, "announcements": 1, "voice": 2, "side_chat": 3, "other": 4}
    return order.get(bucket, 99)


def ai_doc_library(include_content: bool = False) -> list[dict]:
    return operator_surface.ai_doc_library(include_content=include_content)


def ollama_router_status() -> dict:
    return operator_surface.ollama_router_status()


def diagnostics_snapshot(mgr: ServiceManager) -> dict:
    return operator_surface.diagnostics_snapshot(
        service_statuses=[service.status() for service in mgr.services.values()],
        runtime_log_override=APP_LOG_PATH,
    )


# ─── Flask control API ────────────────────────────────────────────────────
def make_app(mgr: ServiceManager, cfg: dict) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(INDEX_HTML, dashboards=cfg.get("dashboards", []))

    @app.get("/icon.png")
    def app_icon():
        if ICON_PATH.exists():
            return send_file(ICON_PATH, mimetype="image/png", max_age=3600)
        return ("", 404)

    # ── Service control ─────────────────────────────────
    @app.get("/api/status")
    def api_status():
        return jsonify({"services": [s.status() for s in mgr.services.values()]})

    @app.post("/api/<sid>/<action>")
    def api_action(sid, action):
        s = mgr.services.get(sid)
        if not s:
            return jsonify({"error": "no such service"}), 404
        if action == "start":
            s.start()
        elif action == "stop":
            s.stop()
        elif action == "restart":
            s.restart()
        else:
            return jsonify({"error": "bad action"}), 400
        return jsonify(s.status())

    @app.get("/api/<sid>/logs")
    def api_logs(sid):
        s = mgr.services.get(sid)
        return ("\n".join(s.log), 200) if s else ("", 404)

    @app.get("/api/<sid>/stream")
    def api_stream(sid):
        s = mgr.services.get(sid)
        if not s:
            return "", 404
        q: queue.Queue = queue.Queue(maxsize=200)
        s.listeners.append(q)

        def gen():
            try:
                for line in list(s.log)[-200:]:
                    yield f"data: {line}\n\n"
                while True:
                    try:
                        yield f"data: {q.get(timeout=15)}\n\n"
                    except queue.Empty:
                        yield ": ping\n\n"
            finally:
                if q in s.listeners:
                    s.listeners.remove(q)

        return Response(gen(), mimetype="text/event-stream")

    # ── LOKI DB-backed config ──────────────────────────
    @app.get("/api/loki/guilds")
    def loki_guilds():
        return jsonify({"guilds": operator_surface.list_guilds()})

    @app.get("/api/loki/<int:guild_id>/config")
    def loki_guild_config(guild_id):
        snapshot = operator_surface.guild_config_snapshot(guild_id)
        return jsonify(
            {
                "config": snapshot["config"],
                "automod": snapshot["automod"],
                "stickies": snapshot["stickies"],
                "tags": snapshot["tags"],
                "forms": snapshot["forms"],
                "streams": snapshot["streams"],
                "channel_names": snapshot["channel_names"],
                "live_channel_lookup": snapshot["live_channel_lookup"],
                "live_channel_error": snapshot["live_channel_error"],
            }
        )

    @app.get("/api/loki/command-library")
    def loki_command_library():
        query = (request.args.get("q") or "").strip().lower()
        category = (request.args.get("category") or "").strip().lower()
        commands = operator_surface.command_library(query=query, category=category)
        return jsonify({"commands": commands})

    @app.get("/api/loki/<int:guild_id>/channels")
    def loki_guild_channels(guild_id):
        return jsonify(operator_surface.channel_cluster_snapshot(guild_id))

    @app.get("/api/loki/options")
    def loki_options():
        return jsonify(operator_surface.option_library())

    @app.get("/api/loki/ai-docs")
    def loki_ai_docs():
        include_content = request.headers.get("X-LOKI THE SUN GOD-AI") == "1" or request.args.get("machine") == "1"
        return jsonify(
            {
                "docs": operator_surface.ai_doc_library(include_content=include_content),
                "machine_mode": include_content,
            }
        )

    @app.get("/api/loki/ollama")
    def loki_ollama():
        return jsonify(operator_surface.ollama_router_status())

    @app.get("/api/diagnostics")
    def api_diagnostics():
        return jsonify(
            operator_surface.diagnostics_snapshot(
                service_statuses=[service.status() for service in mgr.services.values()],
                runtime_log_override=APP_LOG_PATH,
            )
        )

    @app.post("/api/loki/<int:guild_id>/config")
    def loki_guild_config_save(guild_id):
        snapshot = operator_surface.save_guild_config(guild_id, request.get_json(force=True))
        return jsonify({"ok": True, "config": snapshot["config"], "automod": snapshot["automod"]})

    @app.delete("/api/loki/<int:guild_id>/sticky/<int:channel_id>")
    def loki_sticky_delete(guild_id, channel_id):
        n = operator_surface.delete_sticky(guild_id, channel_id)
        return jsonify({"deleted": n})

    @app.get("/api/dashboards")
    def api_dashboards():
        cfg["dashboards"] = sanitize_dashboards(cfg.get("dashboards", []))
        return jsonify({"dashboards": cfg["dashboards"]})

    @app.get("/api/dashboard-status")
    def api_dashboard_status():
        return jsonify(operator_surface.dashboard_ops_status())

    @app.post("/api/backup/manual")
    def api_backup_manual():
        result = operator_surface.create_manual_backup()
        return jsonify(result), 200 if result.get("ok") else 400

    # ── Header-stripping proxy for iframe-hostile sites (e.g. Next.js with
    # X-Frame-Options: DENY or strict CSP frame-ancestors). Pass-through GET
    # only; rewrites Location header for redirects so the iframe stays inside
    # the proxy. Best-effort — heavy SPAs may still break due to relative URLs.
    STRIP_HEADERS = {
        "x-frame-options",
        "content-security-policy",
        "content-security-policy-report-only",
        "frame-options",
        "cross-origin-opener-policy",
        "cross-origin-embedder-policy",
    }

    @app.get("/proxy")
    def http_proxy():
        target = request.args.get("url", "").strip()
        if not target.startswith(("http://", "https://")):
            return ("bad url", 400)
        try:
            req = urllib.request.Request(
                target,
                headers={
                    "User-Agent": request.headers.get("User-Agent", "LOKI THE SUN GODDesktop/1.0"),
                    "Accept": request.headers.get("Accept", "*/*"),
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "text/html")
                # Drop framing headers
                headers = [(k, v) for k, v in r.getheaders() if k.lower() not in STRIP_HEADERS]
                # Rewrite redirect target through proxy so iframe stays put
                headers = [
                    (k, f"/proxy?url={urllib.parse.quote(v, safe='')}")
                    if k.lower() == "location" and v.startswith(("http://", "https://"))
                    else (k, v)
                    for k, v in headers
                ]
                return Response(body, status=r.status, headers=headers, content_type=ctype)
        except Exception as e:
            return (f"proxy error: {e}", 502)

    return app


def _i(v):
    try:
        return int(v) if v not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


# ─── Inline HTML (single-file shippable) ──────────────────────────────────
INDEX_HTML = r"""
<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8"><title>LOKI THE SUN GOD Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
<script>
tailwind.config={darkMode:'class',theme:{extend:{colors:{
blurple:{DEFAULT:'#5865F2',600:'#4752C4'},bart:'#f6c244',shirt:'#e24732',
ink:{950:'#0c0d10',900:'#15171b',800:'#1e2025',700:'#2b2d31',600:'#3f4147'},
mint:'#22c55e',amber:'#f59e0b',rose:'#ef4444'}}}};
</script>
<style>
body{background:#0c0d10;color:#dbdee1;font-family:Inter,system-ui,sans-serif}
.log{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;line-height:1.4}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:#3f4147;border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:#5b5e66}
[x-cloak]{display:none!important}
.brand-icon{width:30px;height:30px;border-radius:9px;object-fit:cover;box-shadow:0 0 0 1px rgba(246,194,68,.4),0 8px 22px rgba(0,0,0,.35)}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid #f6c244;outline-offset:2px}

/* ── Toggle switch ── */
.toggle{appearance:none;width:38px;height:22px;background:#3f4147;border-radius:11px;position:relative;cursor:pointer;transition:background .15s}
.toggle:checked{background:#5865F2}
.toggle::before{content:'';position:absolute;top:3px;left:3px;width:16px;height:16px;background:#fff;border-radius:50%;transition:transform .15s}
.toggle:checked::before{transform:translateX(16px)}

/* ── Polished native select (dark caret) ── */
select.sel{appearance:none;background-color:#15171b;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' fill='%2394a3b8' viewBox='0 0 16 16'><path d='M4 6l4 4 4-4'/></svg>");background-repeat:no-repeat;background-position:right .5rem center;background-size:14px;padding-right:1.75rem;border:1px solid #3f4147;border-radius:8px;color:#dbdee1;padding-left:.65rem;padding-top:.4rem;padding-bottom:.4rem;font-size:13px;cursor:pointer;transition:border-color .12s}
select.sel:hover{border-color:#5b5e66}
select.sel:focus{outline:none;border-color:#5865F2;box-shadow:0 0 0 3px rgba(88,101,242,.18)}
select.sel option{background:#15171b}

/* ── Button variants ── */
.btn{display:inline-flex;align-items:center;gap:.45rem;padding:.45rem .85rem;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;transition:all .12s;border:1px solid transparent;line-height:1}
.btn-primary{background:#5865F2;color:#fff}
.btn-primary:hover{background:#4752C4;box-shadow:0 4px 14px -4px rgba(88,101,242,.55)}
.btn-ghost{background:transparent;border-color:#3f4147;color:#dbdee1}
.btn-ghost:hover{background:#1e2025;border-color:#5b5e66}
.btn-mint{background:rgba(34,197,94,.12);color:#22c55e}
.btn-mint:hover{background:rgba(34,197,94,.22)}
.btn-rose{background:rgba(239,68,68,.12);color:#ef4444}
.btn-rose:hover{background:rgba(239,68,68,.22)}
.btn-amber{background:rgba(245,158,11,.12);color:#f59e0b}
.btn-amber:hover{background:rgba(245,158,11,.22)}
.btn-sm{padding:.3rem .6rem;font-size:12px}
.btn:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}

/* ── Segmented control ── */
.seg{display:inline-flex;background:#15171b;border:1px solid #2b2d31;border-radius:8px;padding:2px;gap:2px}
.seg button{padding:.3rem .65rem;font-size:12px;border-radius:6px;color:#94a3b8;background:transparent;cursor:pointer;border:0;transition:all .12s}
.seg button:hover{color:#dbdee1}
.seg button.on{background:#2b2d31;color:#fff}

/* ── Polished inputs ── */
input[type=text],input[type=number],input.in{background:#15171b;border:1px solid #3f4147;border-radius:8px;padding:.4rem .6rem;color:#dbdee1;font-size:13px;transition:border-color .12s,box-shadow .12s;width:100%}
input[type=text]:focus,input[type=number]:focus,input.in:focus{outline:none;border-color:#5865F2;box-shadow:0 0 0 3px rgba(88,101,242,.18)}

/* ── Card ── */
.card{background:rgba(21,23,27,.55);border:1px solid #2b2d31;border-radius:12px;backdrop-filter:blur(8px)}
.card:hover{border-color:#3f4147}
.card-hi{border-color:rgba(88,101,242,.5)}
.hero-card{background:radial-gradient(circle at top right, rgba(88,101,242,.22), transparent 34%),linear-gradient(135deg, rgba(21,23,27,.96), rgba(30,32,37,.92));border:1px solid rgba(88,101,242,.22);box-shadow:0 18px 40px rgba(0,0,0,.24)}
.soft-card{background:linear-gradient(180deg, rgba(21,23,27,.82), rgba(21,23,27,.58));border:1px solid rgba(63,65,71,.8);border-radius:16px;backdrop-filter:blur(10px)}
.metric-card{border:1px solid rgba(63,65,71,.8);border-radius:16px;padding:1rem;background:linear-gradient(180deg, rgba(21,23,27,.9), rgba(30,32,37,.6));min-height:146px}
.metric-list{max-height:150px;overflow:auto;margin-top:.85rem;padding-right:.15rem}
.metric-list li{display:flex;align-items:center;gap:.5rem;padding:.4rem .55rem;border-radius:10px;background:rgba(12,13,16,.32)}
.section-kicker{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#94a3b8}
.section-heading{font-size:1.1rem;font-weight:600;color:#fff}
.jump-nav{display:flex;flex-wrap:wrap;gap:.55rem}
.jump-btn{display:inline-flex;align-items:center;gap:.45rem;padding:.6rem .8rem;border-radius:12px;border:1px solid rgba(63,65,71,.8);background:rgba(12,13,16,.42);color:#cbd5e1;font-size:13px;transition:all .12s}
.jump-btn:hover{border-color:rgba(88,101,242,.55);background:rgba(88,101,242,.1);color:#fff}
.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.9rem}
.field-card{padding:.9rem;border-radius:14px;border:1px solid rgba(63,65,71,.72);background:rgba(12,13,16,.28)}
.field-label{display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8;margin-bottom:.4rem}
.toggle-row{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.8rem .95rem;border-radius:14px;border:1px solid rgba(63,65,71,.72);background:rgba(12,13,16,.28)}
.toggle-copy{display:flex;flex-direction:column;gap:.15rem}
.toggle-copy strong{font-size:14px;color:#fff;font-weight:600}
.toggle-copy span{font-size:12px;color:#94a3b8}
.resource-list{display:flex;flex-direction:column;gap:.55rem;max-height:260px;overflow:auto;padding-right:.15rem}
.resource-item{display:flex;align-items:center;gap:.7rem;padding:.65rem .75rem;border-radius:12px;background:rgba(12,13,16,.32);border:1px solid rgba(63,65,71,.52)}
.resource-item:hover{border-color:rgba(88,101,242,.4)}
.resource-badge{display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:34px;border-radius:10px;font-size:12px;font-weight:700;background:rgba(88,101,242,.14);color:#9aa5ff}
.mini-note{font-size:12px;color:#94a3b8}
.panel-shell{display:grid;gap:1rem}
.library-shell{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);gap:1rem}
.library-card{border:1px solid rgba(63,65,71,.8);border-radius:18px;background:linear-gradient(180deg, rgba(21,23,27,.92), rgba(17,19,24,.72));overflow:hidden}
.library-head{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1rem .85rem 1rem;border-bottom:1px solid rgba(63,65,71,.7)}
.library-scroll{max-height:520px;overflow:auto;padding:.9rem}
.command-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.8rem;padding:.9rem 1rem;border:1px solid rgba(63,65,71,.52);border-radius:14px;background:rgba(12,13,16,.28)}
.command-row:hover{border-color:rgba(88,101,242,.42);background:rgba(88,101,242,.05)}
.pill{display:inline-flex;align-items:center;gap:.35rem;padding:.25rem .55rem;border-radius:999px;font-size:11px;border:1px solid rgba(63,65,71,.75);background:rgba(12,13,16,.4);color:#cbd5e1}
.cluster-card{border:1px solid rgba(63,65,71,.62);border-radius:16px;background:rgba(12,13,16,.26);overflow:hidden}
.cluster-head{display:flex;align-items:center;justify-content:space-between;gap:.8rem;width:100%;padding:.9rem 1rem;background:transparent;border:0;color:inherit;text-align:left}
.cluster-head:hover{background:rgba(88,101,242,.05)}
.cluster-list{padding:0 1rem 1rem 1rem;display:flex;flex-direction:column;gap:.65rem}
.channel-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.75rem;padding:.75rem .9rem;border-radius:12px;border:1px solid rgba(63,65,71,.42);background:rgba(21,23,27,.65)}
.option-row{padding:.85rem .95rem;border:1px solid rgba(63,65,71,.56);border-radius:14px;background:rgba(12,13,16,.28)}
.diagnostic-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.8rem}
.diagnostic-tile{padding:.95rem;border-radius:14px;border:1px solid rgba(63,65,71,.7);background:rgba(12,13,16,.3)}
.empty-state{display:grid;place-items:center;min-height:180px;padding:1rem;text-align:center;color:#94a3b8;border:1px dashed rgba(63,65,71,.72);border-radius:16px;background:rgba(12,13,16,.18)}
.search-input{padding-left:2.3rem}
.search-wrap{position:relative}
.search-wrap i{position:absolute;left:.85rem;top:50%;transform:translateY(-50%);color:#64748b}
.field-select{margin-top:.65rem}
.card-actions{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.9rem}
@media (max-width:1100px){.library-shell{grid-template-columns:1fr}.library-scroll{max-height:unset}}

iframe{border:0;background:#0c0d10}
.iframe-wrap{position:relative}
.iframe-wrap.loading::after{content:'Loading…';position:absolute;inset:0;display:grid;place-items:center;color:#94a3b8;font-size:13px;background:#0c0d10}
</style>
</head>
<body class="min-h-screen" x-data="app()" x-init="init()">

<header class="sticky top-0 z-30 backdrop-blur bg-ink-900/85 border-b border-ink-700">
  <div class="max-w-[1400px] mx-auto px-4 h-12 flex items-center gap-1">
    <img src="/icon.png" alt="LOKI THE SUN GOD dashboard icon" class="brand-icon mr-2">
    <span class="font-semibold tracking-tight mr-4">LOKI THE SUN GOD Dashboard</span>

    <template x-for="t in tabs" :key="t.id">
      <button @click="tab = t.id; activeDash=null"
              :class="tab === t.id ? 'bg-ink-800 text-white' : 'text-slate-400 hover:bg-ink-800/60'"
              class="px-3 py-1.5 rounded-md text-sm inline-flex items-center gap-1.5">
        <i :class="`bi bi-${t.icon}`"></i><span x-text="t.label"></span>
      </button>
    </template>

    <div class="ml-auto flex items-center gap-2 text-xs text-slate-500">
      <span x-show="active" x-cloak>
        <span class="dot bg-mint align-middle"></span>
        <span x-text="active?.label" class="ml-1"></span>
      </span>
    </div>
  </section>
</header>

<!-- ───── Tab: Services ───── -->
<main x-show="tab === 'services'" x-cloak class="max-w-[1400px] mx-auto px-4 py-4 grid lg:grid-cols-[300px_1fr] gap-4">
  <aside class="space-y-2">
    <template x-for="s in services" :key="s.id">
      <div :class="active?.id === s.id ? 'border-blurple bg-ink-800/80' : 'border-ink-700 bg-ink-900/40 hover:border-ink-600'"
           class="rounded-xl border p-3 cursor-pointer transition" @click="select(s)">
        <div class="flex items-center gap-2">
          <span :class="s.running ? 'bg-mint' : 'bg-slate-600'" class="dot"></span>
          <span class="font-semibold flex-1 truncate" x-text="s.label"></span>
          <span class="text-xs text-slate-500" x-text="s.running ? 'PID '+s.pid : 'stopped'"></span>
        </div>
        <div class="text-xs text-slate-500 mt-1 flex gap-3">
          <span x-show="s.running" x-text="'up '+fmtSec(s.uptime)"></span>
          <span x-show="s.cpu !== undefined" x-text="(s.cpu||0).toFixed(1)+'% cpu'"></span>
          <span x-show="s.mem_mb" x-text="s.mem_mb+' MB'"></span>
          <span x-show="s.restarts" class="text-amber" x-text="'↻'+s.restarts"></span>
        </div>
        <div class="flex gap-1 mt-2" @click.stop>
          <button @click="act(s.id,'start')" :disabled="s.running"
                  :class="s.running ? 'opacity-40 cursor-not-allowed' : 'bg-mint/15 text-mint hover:bg-mint/25'"
                  class="flex-1 text-xs py-1 rounded">Start</button>
          <button @click="act(s.id,'stop')" :disabled="!s.running"
                  :class="!s.running ? 'opacity-40 cursor-not-allowed' : 'bg-rose/15 text-rose hover:bg-rose/25'"
                  class="flex-1 text-xs py-1 rounded">Stop</button>
          <button @click="act(s.id,'restart')"
                  class="flex-1 text-xs py-1 rounded bg-amber/15 text-amber hover:bg-amber/25">Restart</button>
        </div>
      </div>
    </template>
  </aside>

  <section class="rounded-xl border border-ink-700 bg-ink-900/40 flex flex-col h-[calc(100vh-110px)]">
    <div class="flex items-center gap-2 px-4 py-2 border-b border-ink-700">
      <span class="text-sm text-slate-400">Logs:</span>
      <span class="text-sm font-semibold" x-text="active?.label || '—'"></span>
      <button @click="$refs.log.textContent=''" class="ml-auto text-xs px-2 py-1 rounded border border-ink-600 hover:bg-ink-800">Clear</button>
      <label class="text-xs flex items-center gap-1">
        <input x-model="follow" type="checkbox" class="accent-blurple"> follow
      </label>
    </div>
    <pre x-ref="log" class="log flex-1 overflow-auto p-3 whitespace-pre-wrap"></pre>
  </section>
</main>

<!-- ───── Tab: LOKI THE SUN GOD ───── -->
<main x-show="tab === 'loki'" x-cloak class="max-w-[1400px] mx-auto px-4 py-4 space-y-4">
  <section class="hero-card rounded-2xl p-5 md:p-6">
    <div class="flex flex-col gap-5 xl:flex-row xl:items-start">
      <div class="flex-1 space-y-4">
        <div>
          <div class="section-kicker">LOKI THE SUN GOD Command Deck</div>
          <h2 class="text-2xl md:text-3xl font-semibold text-white mt-1">LOKI THE SUN GOD control center</h2>
          <p class="text-sm text-slate-300 mt-2 max-w-3xl">A cleaner operator surface for LOKI THE SUN GOD: command lookup, channel browsing, option explainers, AI-facing documentation, and local-model readiness all in one place.</p>
        </div>
        <div class="jump-nav">
          <button @click="jumpTo('loki-general')" class="jump-btn"><i class="bi bi-sliders2"></i> Server setup</button>
          <button @click="jumpTo('loki-automod')" class="jump-btn"><i class="bi bi-shield-check"></i> AutoMod</button>
          <button @click="jumpTo('loki-resources')" class="jump-btn"><i class="bi bi-grid-1x2"></i> Resources</button>
          <button @click="jumpTo('loki-commands')" class="jump-btn"><i class="bi bi-terminal"></i> Command library</button>
          <button @click="jumpTo('loki-slash')" class="jump-btn"><i class="bi bi-slash-circle"></i> Slash commands</button>
          <button @click="jumpTo('loki-channels')" class="jump-btn"><i class="bi bi-diagram-3"></i> Channel explorer</button>
          <button @click="jumpTo('loki-ai')" class="jump-btn"><i class="bi bi-cpu"></i> AI ops</button>
        </div>
      </div>
      <div class="soft-card p-4 w-full xl:w-[360px] shrink-0 space-y-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="section-kicker">Current guild</div>
            <div class="text-sm text-slate-300">Pick the server you want to tune.</div>
          </div>
          <span class="text-xs text-slate-500" x-text="saveStatus || 'Ready'"></span>
        </div>
        <div class="space-y-2">
          <label class="field-label !mb-0">Guild ID</label>
          <select x-model.number="guildId" @change="loadGuild" class="sel w-full">
            <template x-for="g in guilds" :key="g.guild_id">
              <option :value="g.guild_id" x-text="g.guild_id"></option>
            </template>
          </select>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="field-card py-3">
            <div class="text-[11px] uppercase tracking-wide text-slate-500">Prefix</div>
            <div class="text-lg font-semibold text-white mt-1" x-text="loki.config.prefix || '/'"></div>
          </div>
          <div class="field-card py-3">
            <div class="text-[11px] uppercase tracking-wide text-slate-500">Levels</div>
            <div class="text-lg font-semibold mt-1" :class="loki.config.level_enabled ? 'text-mint' : 'text-slate-400'" x-text="loki.config.level_enabled ? 'On' : 'Off'"></div>
          </div>
          <div class="field-card py-3">
            <div class="text-[11px] uppercase tracking-wide text-slate-500">Protections</div>
            <div class="text-lg font-semibold text-white mt-1" x-text="enabledAutomodCount()"></div>
          </div>
        </div>
        <div class="diagnostic-grid">
          <div class="diagnostic-tile">
            <div class="section-kicker">Commands</div>
            <div class="text-xl font-semibold text-white mt-1" x-text="commandLibrary.length"></div>
          </div>
          <div class="diagnostic-tile">
            <div class="section-kicker">Channels</div>
            <div class="text-xl font-semibold text-white mt-1" x-text="channelLibrary.total || 0"></div>
          </div>
          <div class="diagnostic-tile">
            <div class="section-kicker">AI docs</div>
            <div class="text-xl font-semibold text-white mt-1" x-text="aiDocs.length"></div>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button @click="saveGuild" class="btn btn-primary flex-1 justify-center">
            <i class="bi bi-save"></i> Save changes
          </button>
          <button @click="loadGuild" class="btn btn-ghost">
            <i class="bi bi-arrow-clockwise"></i> Refresh
          </button>
          <button @click="refreshDiagnostics" class="btn btn-ghost">
            <i class="bi bi-activity"></i> Diagnostics
          </button>
        </div>
      </div>
    </div>
  </section>

  <!-- General + AutoMod -->
  <div class="grid xl:grid-cols-[1.15fr_.85fr] gap-4 items-start">
    <section id="loki-general" class="soft-card p-5 space-y-4">
      <div>
        <div class="section-kicker">Server Setup</div>
        <h3 class="section-heading mt-1">General LOKI THE SUN GOD options</h3>
        <p class="mini-note mt-1">Core channels and engagement controls, laid out for faster scanning.</p>
        <p class="mini-note mt-2" x-text="channelLibrary.live ? 'Discovered channels are ready in the selectors below.' : (channelLibrary.error || 'Channel selectors will fill once live Discord access or saved LOKI THE SUN GOD channel IDs are available.')"></p>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" @click="openGuildPage('')"><i class="bi bi-box-arrow-up-right"></i> Open config page</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="field-card">
          <label class="field-label">Prefix</label>
          <input x-model="loki.config.prefix" maxlength="10" type="text">
        </div>
        <div class="field-card">
          <label class="field-label">Log channel</label>
          <input x-model="loki.config.log_channel" type="number">
          <div class="mini-note mt-2" x-text="resolvedConfigChannel('log_channel')"></div>
          <select class="sel w-full field-select" @change="applyChannelSelection('log_channel', $event.target.value)">
            <option value="">Pick a discovered channel</option>
            <template x-for="channel in channelOptions()" :key="`log-${channel.id}`">
              <option :value="channel.id" x-text="channel.label"></option>
            </template>
          </select>
        </div>
        <div class="field-card">
          <label class="field-label">Welcome channel</label>
          <input x-model="loki.config.welcome_channel" type="number">
          <div class="mini-note mt-2" x-text="resolvedConfigChannel('welcome_channel')"></div>
          <select class="sel w-full field-select" @change="applyChannelSelection('welcome_channel', $event.target.value)">
            <option value="">Pick a discovered channel</option>
            <template x-for="channel in channelOptions()" :key="`welcome-${channel.id}`">
              <option :value="channel.id" x-text="channel.label"></option>
            </template>
          </select>
        </div>
        <div class="field-card">
          <label class="field-label">Starboard channel</label>
          <input x-model="loki.config.starboard_channel" type="number">
          <div class="mini-note mt-2" x-text="resolvedConfigChannel('starboard_channel')"></div>
          <select class="sel w-full field-select" @change="applyChannelSelection('starboard_channel', $event.target.value)">
            <option value="">Pick a discovered channel</option>
            <template x-for="channel in channelOptions()" :key="`star-${channel.id}`">
              <option :value="channel.id" x-text="channel.label"></option>
            </template>
          </select>
        </div>
        <div class="field-card">
          <label class="field-label">Star threshold</label>
          <input x-model="loki.config.star_threshold" type="number" min="1" max="99">
        </div>
        <label class="toggle-row">
          <div class="toggle-copy">
            <strong>XP leveling</strong>
            <span>Reward activity and make progression visible.</span>
          </div>
          <input x-model="loki.config.level_enabled" type="checkbox" class="toggle">
        </label>
      </div>
    </section>

    <section id="loki-automod" class="soft-card p-5 space-y-4">
      <div>
        <div class="section-kicker">Protection</div>
        <h3 class="section-heading mt-1">AutoMod controls</h3>
        <p class="mini-note mt-1">Enable the protections you need and adjust the thresholds below.</p>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" @click="openGuildPage('')"><i class="bi bi-box-arrow-up-right"></i> Modify in dashboard</button>
        </div>
      </div>
      <template x-for="k in ['anti_invite','anti_spam','anti_caps','anti_mention']" :key="k">
        <label class="toggle-row">
          <div class="toggle-copy">
            <strong x-text="automodLabel(k)"></strong>
            <span x-text="automodHelp(k)"></span>
          </div>
          <input :value="loki.automod[k]" @change="loki.automod[k] = $event.target.checked ? 1 : 0"
                 type="checkbox" :checked="loki.automod[k]" class="toggle">
        </label>
      </template>
      <div class="form-grid">
        <div class="field-card">
          <label class="field-label">Max mentions</label>
          <input x-model="loki.automod.max_mentions" type="number">
        </div>
        <div class="field-card">
          <label class="field-label">Spam threshold</label>
          <input x-model="loki.automod.spam_threshold" type="number">
        </div>
        <div class="field-card">
          <label class="field-label">Caps percent</label>
          <input x-model="loki.automod.caps_percent" type="number">
        </div>
      </div>
    </section>
  </div>

  <!-- Tags + Stickies + Streams + Forms summaries -->
  <section id="loki-resources" class="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
    <div class="metric-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="section-kicker">Tags</div>
          <div class="text-3xl font-semibold text-white mt-1" x-text="loki.tags.length"></div>
          <div class="mini-note mt-1">Fast-access LOKI THE SUN GOD responses.</div>
        </div>
        <span class="resource-badge"><i class="bi bi-bookmark-star"></i></span>
      </div>
      <ul class="metric-list text-xs text-slate-300">
        <template x-if="!loki.tags.length">
          <li class="text-slate-500">No tags configured yet.</li>
        </template>
        <template x-for="t in loki.tags.slice(0,6)" :key="t.name">
          <li>
            <span class="truncate font-medium text-white" x-text="t.name"></span>
            <span class="ml-auto text-slate-500" x-text="`${t.uses} uses`"></span>
          </li>
        </template>
      </ul>
      <div class="card-actions">
        <button class="btn btn-ghost btn-sm" @click="openGuildPage('')"><i class="bi bi-box-arrow-up-right"></i> Manage tags</button>
      </div>
    </div>
    <div class="metric-card">
      <div class="section-kicker">Stickies</div>
      <div class="text-3xl font-semibold text-amber mt-1" x-text="loki.stickies.length"></div>
      <div class="mini-note mt-1">Pinned channel reminders.</div>
      <ul class="metric-list text-xs text-slate-300">
        <template x-if="!loki.stickies.length">
          <li class="text-slate-500">No sticky messages saved.</li>
        </template>
        <template x-for="s in loki.stickies.slice(0,6)" :key="s.channel_id">
          <li class="flex items-center gap-1">
            <span class="truncate text-white" x-text="resolvedResourceChannel(s.channel_id, s.channel_name)"></span>
            <button @click="deleteSticky(s.channel_id)" class="text-rose hover:text-rose/80 ml-auto"><i class="bi bi-trash"></i></button>
          </li>
        </template>
      </ul>
      <div class="card-actions">
        <button class="btn btn-ghost btn-sm" @click="openGuildPage('')"><i class="bi bi-box-arrow-up-right"></i> Modify stickies</button>
      </div>
    </div>
    <div class="metric-card">
      <div class="section-kicker">Streams</div>
      <div class="text-3xl font-semibold text-mint mt-1" x-text="loki.streams.length"></div>
      <div class="mini-note mt-1">Live integrations and status.</div>
      <ul class="metric-list text-xs text-slate-300">
        <template x-if="!loki.streams.length">
          <li class="text-slate-500">No streams connected.</li>
        </template>
        <template x-for="s in loki.streams.slice(0,6)" :key="s.id">
          <li>
            <span :class="s.last_status ? 'text-mint' : 'text-slate-500'">&#9679;</span>
            <span class="truncate text-white" x-text="`${s.platform}/${s.channel_name}`"></span>
            <span class="ml-auto text-slate-500" x-text="resolvedResourceChannel(s.target_channel_id, s.target_channel_name)"></span>
          </li>
        </template>
      </ul>
      <div class="card-actions">
        <button class="btn btn-ghost btn-sm" @click="openGuildPage('streams')"><i class="bi bi-box-arrow-up-right"></i> Edit streams</button>
      </div>
    </div>
    <div class="metric-card">
      <div class="section-kicker">Forms</div>
      <div class="text-3xl font-semibold text-rose mt-1" x-text="loki.forms.length"></div>
      <div class="mini-note mt-1">Submission flows ready to use.</div>
      <ul class="metric-list text-xs text-slate-300">
        <template x-if="!loki.forms.length">
          <li class="text-slate-500">No forms created.</li>
        </template>
        <template x-for="f in loki.forms.slice(0,6)" :key="f.name">
          <li>
            <span class="text-white" x-text="f.name"></span>
            <span class="ml-auto text-slate-500" x-text="resolvedResourceChannel(f.target_channel_id, f.target_channel_name)"></span>
          </li>
        </template>
      </ul>
      <div class="card-actions">
        <button class="btn btn-ghost btn-sm" @click="openGuildPage('forms')"><i class="bi bi-box-arrow-up-right"></i> Edit forms</button>
      </div>
    </div>
  </section>

  <section id="loki-commands" class="library-shell">
    <div class="library-card">
      <div class="library-head">
        <div>
          <div class="section-kicker">Command Library</div>
          <h3 class="section-heading mt-1">Searchable LOKI THE SUN GOD command catalog</h3>
          <p class="mini-note mt-1">Live-discovered from the cogs so you can scan what each command does, which permissions it needs, and which options it accepts.</p>
        </div>
        <span class="pill"><i class="bi bi-list-task"></i> <span x-text="filteredCommands().length"></span></span>
      </div>
      <div class="px-4 pb-3 flex flex-col gap-3 md:flex-row md:items-center">
        <div class="search-wrap flex-1">
          <i class="bi bi-search"></i>
          <input x-model="commandSearch" type="text" class="in search-input" placeholder="Search commands, options, permissions, or descriptions">
        </div>
        <select x-model="commandCategory" class="sel md:w-[220px]">
          <option value="">All categories</option>
          <template x-for="category in commandCategories()" :key="category">
            <option :value="category" x-text="category"></option>
          </template>
        </select>
        <button class="btn btn-ghost md:w-auto" @click="openGuildPage('commands')"><i class="bi bi-box-arrow-up-right"></i> Open dashboard library</button>
      </div>
      <div class="library-scroll space-y-3">
        <template x-if="!filteredCommands().length">
          <div class="empty-state">No commands match this search yet.</div>
        </template>
        <template x-for="cmd in filteredCommands()" :key="cmd.id">
          <div class="command-row" x-data="{ expanded: false }">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-white font-semibold" x-text="cmd.full_name"></span>
                <span class="pill" x-text="cmd.kind"></span>
                <span class="pill" x-text="cmd.category"></span>
                <span class="pill" x-show="cmd.option_count"><span x-text="`${cmd.option_count} options`"></span></span>
              </div>
              <p class="text-sm text-slate-300 mt-2" x-text="cmd.description"></p>
              <div class="flex flex-wrap gap-2 mt-3 text-xs text-slate-400">
                <span class="pill" x-show="cmd.aliases?.length">Aliases: <span x-text="cmd.aliases.join(', ')"></span></span>
                <span class="pill" x-show="cmd.permission_labels?.length">Needs: <span x-text="cmd.permission_labels.join(', ')"></span></span>
                <span class="pill">Source: <span x-text="cmd.file"></span></span>
              </div>
              <div class="mt-3 space-y-2" x-show="expanded && cmd.options?.length" x-cloak>
                <template x-for="option in cmd.options" :key="`${cmd.id}-${option.name}`">
                  <div class="rounded-xl border border-ink-700 bg-ink-900/50 px-3 py-3">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-white font-medium" x-text="option.name"></span>
                      <span class="pill" x-text="option.type"></span>
                      <span class="pill" x-text="option.required ? 'required' : 'optional'"></span>
                      <span class="pill" x-show="option.autocomplete">autocomplete</span>
                    </div>
                    <p class="text-sm text-slate-300 mt-2" x-text="option.description"></p>
                    <div class="flex flex-wrap gap-2 mt-2 text-xs text-slate-500">
                      <span class="pill" x-show="option.annotation">Signature: <span x-text="option.annotation"></span></span>
                      <span class="pill" x-show="option.default_display">Default: <span x-text="option.default_display"></span></span>
                      <span class="pill" x-show="option.choices?.length">Choices: <span x-text="option.choices.join(', ')"></span></span>
                    </div>
                  </div>
                </template>
              </div>
            </div>
            <div class="text-right text-xs text-slate-500 whitespace-nowrap space-y-2">
              <div>
                <div>Command</div>
                <div class="text-white font-mono mt-1" x-text="cmd.command"></div>
              </div>
              <button class="btn btn-ghost btn-sm" x-show="cmd.option_count" @click="expanded = !expanded">
                <span x-text="expanded ? 'Hide options' : `View ${cmd.option_count}`"></span>
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="library-card">
      <div class="library-head">
        <div>
          <div class="section-kicker">Option Guide</div>
          <h3 class="section-heading mt-1">What each option changes</h3>
        </div>
      </div>
      <div class="px-4 pb-3">
        <div class="search-wrap">
          <i class="bi bi-search"></i>
          <input x-model="optionSearch" type="text" class="in search-input" placeholder="Search options, effects, or examples">
        </div>
      </div>
      <div class="library-scroll space-y-3">
        <template x-if="!allOptions().length">
          <div class="empty-state">No options match this search yet.</div>
        </template>
        <template x-for="item in allOptions()" :key="item.id">
          <div class="option-row">
            <div class="flex items-center gap-2">
              <span class="text-white font-medium" x-text="item.label"></span>
              <span class="pill" x-text="item.type"></span>
            </div>
            <p class="text-sm text-slate-300 mt-2" x-text="item.effect"></p>
            <p class="text-xs text-slate-500 mt-2" x-show="item.example">Example: <span x-text="item.example"></span></p>
            <div class="card-actions">
              <button class="btn btn-ghost btn-sm" @click="openGuildPage(item.route || '')"><i class="bi bi-box-arrow-up-right"></i> Show and modify</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>

  <section id="loki-slash" class="library-card">
    <div class="library-head">
      <div>
        <div class="section-kicker">Slash Commands</div>
        <h3 class="section-heading mt-1">Complete "/" command list</h3>
        <p class="mini-note mt-1">Slash-capable commands with their option-level guidance so you can see what each "/" command expects at a glance.</p>
      </div>
      <span class="pill"><i class="bi bi-slash-circle"></i> <span x-text="slashCommands().length"></span></span>
    </div>
    <div class="px-4 pb-3 flex flex-col gap-3 md:flex-row md:items-center">
      <div class="search-wrap flex-1">
        <i class="bi bi-search"></i>
        <input x-model="slashSearch" type="text" class="in search-input" placeholder="Search slash commands, options, or descriptions">
      </div>
      <button class="btn btn-ghost btn-sm" @click="openGuildPage('commands')"><i class="bi bi-box-arrow-up-right"></i> Open dashboard library</button>
    </div>
    <div class="library-scroll space-y-3">
      <template x-if="!filteredSlashCommands().length">
        <div class="empty-state">No slash commands matched this search yet.</div>
      </template>
      <template x-for="cmd in filteredSlashCommands()" :key="`slash-${cmd.id}`">
        <div class="command-row" x-data="{ expanded: false }">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-white font-semibold" x-text="`/${cmd.full_name}`"></span>
              <span class="pill" x-text="cmd.kind"></span>
              <span class="pill" x-text="cmd.category"></span>
              <span class="pill" x-show="cmd.option_count"><span x-text="`${cmd.option_count} options`"></span></span>
            </div>
            <p class="text-sm text-slate-300 mt-2" x-text="cmd.description"></p>
            <div class="flex flex-wrap gap-2 mt-2 text-xs text-slate-500">
              <span class="pill" x-show="cmd.permission_labels?.length">Needs: <span x-text="cmd.permission_labels.join(', ')"></span></span>
              <span class="pill">Source: <span x-text="cmd.file"></span></span>
            </div>
            <div class="mt-3 space-y-2" x-show="expanded && cmd.options?.length" x-cloak>
              <template x-for="option in cmd.options" :key="`slash-${cmd.id}-${option.name}`">
                <div class="rounded-xl border border-ink-700 bg-ink-900/50 px-3 py-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-white font-medium" x-text="option.name"></span>
                    <span class="pill" x-text="option.type"></span>
                    <span class="pill" x-text="option.required ? 'required' : 'optional'"></span>
                    <span class="pill" x-show="option.autocomplete">autocomplete</span>
                  </div>
                  <p class="text-sm text-slate-300 mt-2" x-text="option.description"></p>
                  <div class="flex flex-wrap gap-2 mt-2 text-xs text-slate-500">
                    <span class="pill" x-show="option.annotation">Signature: <span x-text="option.annotation"></span></span>
                    <span class="pill" x-show="option.default_display">Default: <span x-text="option.default_display"></span></span>
                    <span class="pill" x-show="option.choices?.length">Choices: <span x-text="option.choices.join(', ')"></span></span>
                  </div>
                </div>
              </template>
            </div>
          </div>
          <div class="text-right text-xs text-slate-500 whitespace-nowrap">
            <button class="btn btn-ghost btn-sm" x-show="cmd.option_count" @click="expanded = !expanded">
              <span x-text="expanded ? 'Hide options' : `View ${cmd.option_count}`"></span>
            </button>
          </div>
        </div>
      </template>
    </div>
  </section>

  <section id="loki-channels" class="library-shell">
    <div class="library-card">
      <div class="library-head">
        <div>
          <div class="section-kicker">Channel Explorer</div>
          <h3 class="section-heading mt-1">Collapsible channel clusters</h3>
          <p class="mini-note mt-1">Browse text, voice, side chat, and announcement channels by category and open only the cluster you need.</p>
        </div>
        <span class="pill"><i class="bi bi-diagram-3"></i> <span x-text="channelLibrary.total || 0"></span></span>
      </div>
      <div class="px-4 pb-3 flex flex-col gap-3 md:flex-row md:items-center">
        <div class="search-wrap flex-1">
          <i class="bi bi-search"></i>
          <input x-model="channelSearch" type="text" class="in search-input" placeholder="Search channel names, topics, or kinds">
        </div>
        <button @click="toggleAllClusters" class="btn btn-ghost md:w-auto"><i class="bi bi-arrows-expand"></i> Toggle clusters</button>
      </div>
      <div class="library-scroll space-y-3">
        <template x-if="channelLibrary.error">
          <div class="empty-state" x-text="channelLibrary.error"></div>
        </template>
        <template x-if="!channelLibrary.error && !filteredChannelClusters().length">
          <div class="empty-state">No channels matched the current filter.</div>
        </template>
        <template x-for="cluster in filteredChannelClusters()" :key="cluster.id">
          <div class="cluster-card">
            <button class="cluster-head" @click="toggleCluster(cluster.id)">
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-white font-medium" x-text="cluster.label"></span>
                  <span class="pill" x-text="cluster.bucket.replace('_',' ')"></span>
                </div>
                <div class="text-xs text-slate-500 mt-1" x-text="`${cluster.channels.length} channels`"></div>
              </div>
              <i class="bi" :class="clusterOpen(cluster.id) ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
            </button>
            <div class="cluster-list" x-show="clusterOpen(cluster.id)">
              <template x-for="channel in cluster.channels" :key="channel.id">
                <div class="channel-row">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="text-white font-medium truncate" x-text="channel.name"></span>
                      <span class="pill" x-text="channel.kind"></span>
                      <span class="pill" x-show="channel.nsfw">NSFW</span>
                    </div>
                    <p class="text-xs text-slate-400 mt-2" x-show="channel.topic" x-text="channel.topic"></p>
                  </div>
                  <div class="text-right text-xs text-slate-500">
                    <div>ID</div>
                    <div class="font-mono text-slate-300 mt-1" x-text="channel.id"></div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="panel-shell">
      <div class="metric-card">
        <div class="section-kicker">Cluster notes</div>
        <div class="text-lg font-semibold text-white mt-1">What the buckets mean</div>
        <div class="space-y-3 mt-4 text-sm text-slate-300">
          <div class="option-row"><span class="text-white font-medium">Text</span><p class="mt-2">Standard chat surfaces, threads, forums, and media channels where members read and write.</p></div>
          <div class="option-row"><span class="text-white font-medium">Announcements</span><p class="mt-2">News-style channels that push important server updates outward.</p></div>
          <div class="option-row"><span class="text-white font-medium">Voice</span><p class="mt-2">Voice and stage spaces for live conversation or hosted sessions.</p></div>
          <div class="option-row"><span class="text-white font-medium">Side chat</span><p class="mt-2">Informal lounge or off-topic spaces detected by naming patterns so they are easier to isolate.</p></div>
        </div>
      </div>
    </div>
  </section>

  <section id="loki-ai" class="library-shell">
    <div class="library-card">
      <div class="library-head">
        <div>
          <div class="section-kicker">AI Docs Library</div>
          <h3 class="section-heading mt-1">Machine-facing documentation shelf</h3>
          <p class="mini-note mt-1">The UI shows summaries only, while full content stays available to AI readers through the local API.</p>
        </div>
        <span class="pill"><i class="bi bi-journal-code"></i> <span x-text="aiDocs.length"></span></span>
      </div>
      <div class="px-4 pb-3">
        <div class="search-wrap">
          <i class="bi bi-search"></i>
          <input x-model="aiDocSearch" type="text" class="in search-input" placeholder="Search AI docs by name, path, or summary">
        </div>
      </div>
      <div class="library-scroll space-y-3">
        <template x-if="!filteredAiDocs().length">
          <div class="empty-state">No AI docs indexed yet.</div>
        </template>
        <template x-for="doc in filteredAiDocs()" :key="doc.file">
          <div class="option-row">
            <div class="flex items-center justify-between gap-3">
              <span class="text-white font-medium" x-text="doc.name"></span>
              <span class="pill" x-text="doc.file"></span>
            </div>
            <p class="text-sm text-slate-300 mt-2" x-text="doc.summary"></p>
            <p class="text-xs text-slate-500 mt-2"><span x-text="formatBytes(doc.bytes)"></span> indexed for AI readers</p>
          </div>
        </template>
      </div>
    </div>

    <div class="panel-shell">
      <div class="library-card">
        <div class="library-head">
          <div>
            <div class="section-kicker">Local Model Ops</div>
            <h3 class="section-heading mt-1">Ollama and 9router readiness</h3>
          </div>
        </div>
        <div class="library-scroll space-y-4">
          <div class="diagnostic-grid">
            <div class="diagnostic-tile">
              <div class="section-kicker">Ollama</div>
              <div class="text-lg font-semibold mt-1" :class="ollama.ollama_up ? 'text-mint' : 'text-rose'" x-text="ollama.ollama_up ? 'Online' : 'Offline'"></div>
            </div>
            <div class="diagnostic-tile">
              <div class="section-kicker">9router</div>
              <div class="text-lg font-semibold mt-1" :class="ollama.router_up ? 'text-mint' : 'text-rose'" x-text="ollama.router_up ? 'Online' : 'Offline'"></div>
            </div>
            <div class="diagnostic-tile">
              <div class="section-kicker">Codex route</div>
              <div class="text-sm font-semibold text-white mt-1 truncate" x-text="ollama.codex_settings?.ANTHROPIC_BASE_URL || 'Not set'"></div>
            </div>
          </div>
          <div>
            <div class="text-sm text-white font-medium">Installed Ollama models</div>
            <div class="flex flex-wrap gap-2 mt-3">
              <template x-if="!ollama.ollama_models?.length"><span class="pill">No local models found</span></template>
              <template x-for="model in (ollama.ollama_models || [])" :key="model"><span class="pill" x-text="model"></span></template>
            </div>
          </div>
          <div>
            <div class="text-sm text-white font-medium">Router-exposed models</div>
            <div class="flex flex-wrap gap-2 mt-3">
              <template x-if="!ollama.router_models?.length"><span class="pill">No router models exposed</span></template>
              <template x-for="model in (ollama.router_models || []).slice(0,16)" :key="model"><span class="pill" x-text="model"></span></template>
            </div>
          </div>
          <div class="option-row">
            <div class="text-white font-medium">What this enables</div>
            <p class="text-sm text-slate-300 mt-2">When Ollama and 9router are available, the app can steer AI workflows toward local-first models and keep Codex aliases pointed at stable routed names instead of raw provider strings.</p>
          </div>
          <div class="option-row">
            <div class="text-white font-medium">Local Ollama setup options</div>
            <div class="space-y-3 mt-3 text-sm text-slate-300">
              <p><strong class="text-white">Option 1:</strong> install Ollama and pull a light local model such as <code>ollama pull qwen2.5-coder:7b</code> or <code>ollama pull llama3.2:3b</code>.</p>
              <p><strong class="text-white">Option 2:</strong> keep Ollama local-only and use the model directly from the desktop for offline-first AI tasks.</p>
              <p><strong class="text-white">Option 3:</strong> run 9router on <code>http://localhost:20128</code> so Codex-style aliases can hand off between local Ollama and cloud providers.</p>
              <p><strong class="text-white">Option 4:</strong> set Codex routing env values to point at 9router:
              <code>ANTHROPIC_BASE_URL=http://localhost:20128/v1</code>,
              <code>ANTHROPIC_AUTH_TOKEN=sk_9router</code>.</p>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="pill">1. <code>ollama list</code></span>
              <span class="pill">2. <code>ollama pull qwen2.5-coder:7b</code></span>
              <span class="pill">3. <code>npm.cmd run dev</code> in 9router</span>
            </div>
          </div>
        </div>
      </div>

      <div class="library-card">
        <div class="library-head">
          <div>
            <div class="section-kicker">Startup Diagnostics</div>
            <h3 class="section-heading mt-1">Project readiness snapshot</h3>
          </div>
        </div>
        <div class="library-scroll space-y-3">
          <div class="diagnostic-grid">
            <div class="diagnostic-tile">
              <div class="section-kicker">Database</div>
              <div class="text-lg font-semibold mt-1" :class="diagnostics.database_present ? 'text-mint' : 'text-rose'" x-text="diagnostics.database_present ? 'Present' : 'Missing'"></div>
            </div>
            <div class="diagnostic-tile">
              <div class="section-kicker">Discord token</div>
              <div class="text-lg font-semibold mt-1" :class="diagnostics.env?.DISCORD_TOKEN ? 'text-mint' : 'text-rose'" x-text="diagnostics.env?.DISCORD_TOKEN ? 'Set' : 'Missing'"></div>
            </div>
            <div class="diagnostic-tile">
              <div class="section-kicker">Command count</div>
              <div class="text-lg font-semibold text-white mt-1" x-text="diagnostics.command_count || 0"></div>
            </div>
          </div>
          <template x-for="svc in diagnostics.services || []" :key="svc.id">
            <div class="option-row">
              <div class="flex items-center justify-between gap-3">
                <span class="text-white font-medium" x-text="svc.label"></span>
                <span class="pill" :class="svc.running ? 'text-mint' : 'text-slate-400'" x-text="svc.running ? 'running' : 'stopped'"></span>
              </div>
              <p class="text-xs text-slate-400 mt-2" x-text="svc.cmd"></p>
            </div>
          </template>
        </div>
      </div>
    </div>
  </section>
</main>

<!-- ───── Tab: Dashboards ───── -->
<main x-show="tab === 'dashboards'" x-cloak class="max-w-[1400px] mx-auto px-4 py-4 space-y-4">

  <!-- Toolbar -->
  <div x-show="!activeDash" class="flex items-center gap-3">
    <h2 class="text-xl font-semibold text-white">Dashboards</h2>
    <span class="text-xs text-slate-500" x-text="dashboards.length + ' configured'"></span>
    <div class="ml-auto flex items-center gap-2">
      <span class="text-xs text-slate-400">Default open:</span>
      <div class="seg">
        <button :class="defaultOpen==='window'?'on':''" @click="defaultOpen='window'" title="Separate native window — works for any site">Window</button>
        <button :class="defaultOpen==='embed'?'on':''"  @click="defaultOpen='embed'"  title="Iframe inside this panel via header-stripping proxy">Embed</button>
        <button :class="defaultOpen==='browser'?'on':''" @click="defaultOpen='browser'" title="System default browser">Browser</button>
      </div>
    </div>
  </div>

  <section x-show="!activeDash" class="grid md:grid-cols-3 gap-3">
    <div class="metric-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="section-kicker">Local AI Assistant</div>
          <div class="text-2xl font-semibold mt-1"
               :class="dashboardOps.ai_assistant.state === 'ready' ? 'text-mint' : (dashboardOps.ai_assistant.state === 'degraded' ? 'text-amber' : 'text-rose')"
               x-text="dashboardOps.ai_assistant.state === 'ready' ? 'Ready' : (dashboardOps.ai_assistant.state === 'degraded' ? 'Degraded' : 'Offline')"></div>
          <div class="mini-note mt-1" x-text="dashboardOps.ai_assistant.summary || 'Checking local AI route…'"></div>
        </div>
        <span class="resource-badge"><i class="bi bi-cpu"></i></span>
      </div>
      <div class="space-y-2 mt-4 text-sm text-slate-300">
        <div class="flex items-center justify-between gap-3">
          <span>Preferred backend</span>
          <span class="pill" x-text="dashboardOps.ai_assistant.preferred_backend || 'none'"></span>
        </div>
        <div class="flex items-center justify-between gap-3">
          <span>Available models</span>
          <span class="text-white font-medium" x-text="dashboardOps.ai_assistant.models_available || 0"></span>
        </div>
        <div class="text-xs text-slate-500 break-all" x-text="dashboardOps.ai_assistant.route_url || 'Not set'"></div>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" @click="openExternal('https://platform.openai.com/api-keys')">
            <i class="bi bi-key"></i> OpenAI API keys
          </button>
          <button class="btn btn-ghost btn-sm" @click="openExternal('http://localhost:5000/ops/ai')">
            <i class="bi bi-sliders"></i> AI settings
          </button>
        </div>
      </div>
    </div>

    <div class="metric-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="section-kicker">Backup Status</div>
          <div class="text-2xl font-semibold mt-1"
               :class="dashboardOps.backup.state === 'ready' ? 'text-mint' : (dashboardOps.backup.state === 'watch' ? 'text-amber' : 'text-rose')"
               x-text="dashboardOps.backup.state === 'ready' ? 'Protected' : (dashboardOps.backup.state === 'watch' ? 'Needs backup' : 'Missing DB')"></div>
          <div class="mini-note mt-1" x-text="dashboardOps.backup.summary || 'Checking backup artifacts…'"></div>
        </div>
        <span class="resource-badge"><i class="bi bi-life-preserver"></i></span>
      </div>
      <div class="space-y-2 mt-4 text-sm text-slate-300">
        <div class="flex items-center justify-between gap-3">
          <span>Backup artifacts</span>
          <span class="text-white font-medium" x-text="dashboardOps.backup.backup_count || 0"></span>
        </div>
        <div class="flex items-center justify-between gap-3">
          <span>Latest age</span>
          <span class="text-white font-medium" x-text="formatAgeSeconds(dashboardOps.backup.backup_age_seconds)"></span>
        </div>
        <div class="text-xs text-slate-500 break-all" x-text="dashboardOps.backup.latest_backup?.display_path || 'No backup file detected yet'"></div>
        <div class="card-actions">
          <button class="btn btn-amber btn-sm" @click="runManualBackup()" :disabled="backupActionStatus === 'Backing up…'">
            <i class="bi bi-database-up"></i> Back up now
          </button>
          <span class="text-xs text-slate-400" x-text="backupActionStatus"></span>
        </div>
      </div>
    </div>

    <div class="metric-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="section-kicker">Router Status</div>
          <div class="text-2xl font-semibold mt-1"
               :class="dashboardOps.router.up ? 'text-mint' : 'text-rose'"
               x-text="dashboardOps.router.up ? 'Online' : 'Offline'"></div>
          <div class="mini-note mt-1" x-text="dashboardOps.router.summary || 'Checking 9router…'"></div>
        </div>
        <span class="resource-badge"><i class="bi bi-diagram-3"></i></span>
      </div>
      <div class="space-y-2 mt-4 text-sm text-slate-300">
        <div class="flex items-center justify-between gap-3">
          <span>Exposed models</span>
          <span class="text-white font-medium" x-text="dashboardOps.router.model_count || 0"></span>
        </div>
        <div class="text-xs text-slate-500 break-all" x-text="dashboardOps.router.base_url || 'http://127.0.0.1:20128/v1'"></div>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" @click="openDashboardById('router9')"><i class="bi bi-box-arrow-up-right"></i> Open router</button>
        </div>
      </div>
    </div>
  </section>

  <!-- Cards -->
  <div x-show="!activeDash" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
    <template x-for="d in dashboards" :key="d.id">
      <div class="card hover:card-hi transition p-4 flex flex-col gap-3">
        <div class="flex items-center gap-3">
          <span :class="`bg-${d.color}/15 text-${d.color}`" class="w-10 h-10 rounded-lg grid place-items-center text-lg shrink-0">
            <i :class="`bi bi-${d.icon}`"></i>
          </span>
          <div class="min-w-0 flex-1">
            <div class="font-semibold truncate" x-text="d.label"></div>
            <div class="text-xs text-slate-500 truncate font-mono" x-text="d.url"></div>
          </div>
          <span :class="dashStatus[d.id] === 'up' ? 'bg-mint' : (dashStatus[d.id] === 'down' ? 'bg-rose' : 'bg-slate-600')"
                class="dot shrink-0" :title="dashStatus[d.id] || 'unknown'"></span>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary btn-sm flex-1" @click="openDash(d, defaultOpen)">
            <i class="bi" :class="defaultOpen==='window' ? 'bi-window' : (defaultOpen==='embed' ? 'bi-layout-text-window-reverse' : 'bi-globe')"></i>
            <span class="capitalize" x-text="defaultOpen"></span>
          </button>
          <button class="btn btn-ghost btn-sm" @click="openDash(d,'window')" title="Open in new app window"><i class="bi bi-window"></i></button>
          <button class="btn btn-ghost btn-sm" @click="openDash(d,'embed')"  title="Embed inside (proxy)"><i class="bi bi-layout-text-window-reverse"></i></button>
          <button class="btn btn-ghost btn-sm" @click="openDash(d,'browser')" title="Open in system browser"><i class="bi bi-box-arrow-up-right"></i></button>
        </div>
      </div>
    </template>
  </div>

  <!-- Embed view -->
  <div x-show="activeDash" x-cloak class="card overflow-hidden flex flex-col h-[calc(100vh-110px)]">
    <div class="flex items-center gap-2 px-3 py-2 border-b border-ink-700">
      <button @click="closeDash()" class="btn btn-ghost btn-sm" title="Back to grid"><i class="bi bi-arrow-left"></i></button>
      <span :class="`bg-${activeDash?.color}/15 text-${activeDash?.color}`" class="w-7 h-7 rounded grid place-items-center">
        <i :class="`bi bi-${activeDash?.icon}`"></i>
      </span>
      <span class="font-semibold text-sm" x-text="activeDash?.label"></span>
      <span class="text-xs text-slate-500 font-mono truncate hidden md:inline" x-text="activeDash?.url"></span>
      <div class="ml-auto flex items-center gap-1">
        <button class="btn btn-ghost btn-sm" @click="reloadFrame()" title="Reload"><i class="bi bi-arrow-clockwise"></i></button>
        <button class="btn btn-ghost btn-sm" @click="openDash(activeDash,'window')" title="Pop out to native window"><i class="bi bi-window"></i></button>
        <button class="btn btn-ghost btn-sm" @click="openDash(activeDash,'browser')" title="Browser"><i class="bi bi-box-arrow-up-right"></i></button>
      </div>
    </div>
    <div class="iframe-wrap flex-1" :class="frameLoading ? 'loading' : ''">
      <iframe x-ref="frame" :src="frameSrc" class="w-full h-full"
              @load="frameLoading=false"></iframe>
    </div>
  </div>
</main>

<script>
function app() {
  return {
    tabs: [
      {id:'services',  label:'Services',   icon:'cpu'},
      {id:'loki',     label:'LOKI THE SUN GOD',    icon:'robot'},
      {id:'dashboards',label:'Dashboards', icon:'window-stack'},
    ],
    tab: 'services',
    services: [],
    active: null,
    follow: true,
    evt: null,

    guilds: [],
    guildId: null,
    loki: { config:{}, automod:{}, tags:[], stickies:[], streams:[], forms:[] },
    channelNames: {},
    saveStatus: '',
    commandLibrary: [],
    commandSearch: '',
    commandCategory: '',
    slashSearch: '',
    optionLibrary: { general: [], automod: [] },
    optionSearch: '',
    channelLibrary: { clusters: [], total: 0, error: '' },
    channelSearch: '',
    expandedClusters: {},
    aiDocs: [],
    aiDocSearch: '',
    ollama: { ollama_models: [], router_models: [], codex_settings: {} },
    diagnostics: { env: {}, services: [] },
    dashboardOps: {
      ai_assistant: { state: 'offline', summary: '', preferred_backend: 'none', models_available: 0, route_url: '' },
      backup: { state: 'watch', summary: '', backup_count: 0, backup_age_seconds: null, latest_backup: null },
      router: { up: false, model_count: 0, base_url: '', summary: '' },
    },
    backupActionStatus: '',

    dashboards: [],
    activeDash: null,
    defaultOpen: 'window',  // window | embed | browser
    frameSrc: '',
    frameLoading: false,
    dashStatus: {},  // id -> 'up' | 'down'

    init() {
      this.refresh();
      setInterval(() => { if (this.tab === 'services') this.refresh(); }, 2500);
      this.loadDashboards().then(() => this.pingDashes());
      this.loadDashboardOps();
      setInterval(() => {
        if (this.tab === 'dashboards') {
          this.pingDashes();
          this.loadDashboardOps();
        }
      }, 8000);
      this.loadGuilds();
      this.loadCommandLibrary();
      this.loadOptionLibrary();
      this.loadAiDocs();
      this.loadOllama();
      this.refreshDiagnostics();
      try { this.defaultOpen = localStorage.getItem('cc.defaultOpen') || 'window'; } catch(_){}
      this.$watch('defaultOpen', v => { try { localStorage.setItem('cc.defaultOpen', v); } catch(_){} });
    },
    async refresh() {
      const r = await fetch('/api/status'); const d = await r.json();
      this.services = d.services;
      if (!this.active && d.services[0]) this.select(d.services[0]);
      else if (this.active) this.active = d.services.find(s => s.id === this.active.id) || this.active;
    },
    select(s) {
      this.active = s;
      this.$refs.log.textContent = '';
      if (this.evt) this.evt.close();
      this.evt = new EventSource(`/api/${s.id}/stream`);
      this.evt.onmessage = (e) => {
        const log = this.$refs.log;
        log.textContent += e.data + '\n';
        if (this.follow) log.scrollTop = log.scrollHeight;
      };
    },
    async act(sid, action) {
      await fetch(`/api/${sid}/${action}`, {method:'POST'});
      this.refresh();
    },

    async loadDashboards() {
      const r = await fetch('/api/dashboards'); const d = await r.json();
      this.dashboards = d.dashboards;
    },
    async loadDashboardOps() {
      const r = await fetch('/api/dashboard-status');
      this.dashboardOps = await r.json();
    },
    async runManualBackup() {
      this.backupActionStatus = 'Backing up…';
      try {
        const r = await fetch('/api/backup/manual', { method:'POST' });
        const d = await r.json();
        if (d.status) this.dashboardOps.backup = d.status;
        this.backupActionStatus = d.ok ? 'Backup complete' : (d.error || 'Backup failed');
      } catch (e) {
        this.backupActionStatus = `Backup failed: ${e}`;
      }
      setTimeout(() => this.backupActionStatus = '', 5000);
    },
    async pingDashes() {
      // best-effort liveness — opaque (no-cors) just checks reachability
      for (const d of this.dashboards) {
        try {
          await fetch(d.url, { mode:'no-cors', cache:'no-store' });
          this.dashStatus[d.id] = 'up';
        } catch(_) {
          this.dashStatus[d.id] = 'down';
        }
      }
    },
    openDash(d, mode) {
      mode = mode || this.defaultOpen;
      if (mode === 'browser') {
        if (window.pywebview && window.pywebview.api?.open_external) {
          window.pywebview.api.open_external(d.url);
        } else {
          window.open(d.url, '_blank');
        }
        return;
      }
      if (mode === 'window') {
        if (window.pywebview && window.pywebview.api?.open_window) {
          window.pywebview.api.open_window(d.url, d.label);
        } else {
          window.open(d.url, '_blank');
        }
        return;
      }
      // embed via header-stripping proxy
      this.activeDash = d;
      this.frameLoading = true;
      this.frameSrc = '/proxy?url=' + encodeURIComponent(d.url);
    },
    openDashboardById(id) {
      const dash = this.dashboards.find(item => item.id === id);
      if (!dash) return;
      this.openDash(dash, this.defaultOpen);
    },
    openExternal(url) {
      if (window.pywebview && window.pywebview.api?.open_external) {
        window.pywebview.api.open_external(url);
      } else {
        window.open(url, '_blank');
      }
    },
    closeDash() { this.activeDash = null; this.frameSrc = ''; },
    reloadFrame() {
      if (!this.activeDash) return;
      this.frameLoading = true;
      const u = '/proxy?url=' + encodeURIComponent(this.activeDash.url) + '&_=' + Date.now();
      this.frameSrc = u;
    },
    openGuildPage(path = '') {
      if (!this.guildId) return;
      const suffix = path ? `/${path}` : '';
      const url = `http://127.0.0.1:5000/guild/${this.guildId}${suffix}`;
      const label = path ? `LOKI THE SUN GOD ${path}` : 'LOKI THE SUN GOD config';
      if (window.pywebview && window.pywebview.api?.open_window) {
        window.pywebview.api.open_window(url, label);
      } else {
        window.open(url, '_blank');
      }
    },

    async loadGuilds() {
      const r = await fetch('/api/loki/guilds'); const d = await r.json();
      this.guilds = d.guilds || [];
      if (this.guilds.length && !this.guildId) {
        this.guildId = this.guilds[0].guild_id;
        this.loadGuild();
      }
    },
    async loadGuild() {
      if (!this.guildId) return;
      const r = await fetch(`/api/loki/${this.guildId}/config`); const d = await r.json();
      this.loki = {
        config: d.config || {}, automod: d.automod || {},
        tags: d.tags || [], stickies: d.stickies || [],
        streams: d.streams || [], forms: d.forms || [],
      };
      this.channelNames = d.channel_names || {};
      this.loadChannels();
    },
    async saveGuild() {
      this.saveStatus = 'Saving…';
      const body = { ...this.loki.config, automod: this.loki.automod };
      const r = await fetch(`/api/loki/${this.guildId}/config`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)});
      const d = await r.json();
      this.saveStatus = d.ok ? `Saved ${new Date().toLocaleTimeString()}` : 'Save failed';
      setTimeout(() => this.saveStatus = '', 4000);
    },
    async deleteSticky(channel_id) {
      await fetch(`/api/loki/${this.guildId}/sticky/${channel_id}`, {method:'DELETE'});
      this.loadGuild();
    },
    async loadCommandLibrary() {
      const r = await fetch('/api/loki/command-library'); const d = await r.json();
      this.commandLibrary = d.commands || [];
    },
    async loadOptionLibrary() {
      const r = await fetch('/api/loki/options'); this.optionLibrary = await r.json();
    },
    async loadChannels() {
      if (!this.guildId) return;
      const r = await fetch(`/api/loki/${this.guildId}/channels`); const d = await r.json();
      this.channelLibrary = d || { clusters: [], total: 0, error: '' };
      this.expandedClusters = Object.fromEntries((this.channelLibrary.clusters || []).map(c => [c.id, true]));
    },
    async loadAiDocs() {
      const r = await fetch('/api/loki/ai-docs'); const d = await r.json();
      this.aiDocs = d.docs || [];
    },
    async loadOllama() {
      const r = await fetch('/api/loki/ollama'); this.ollama = await r.json();
    },
    async refreshDiagnostics() {
      const r = await fetch('/api/diagnostics'); this.diagnostics = await r.json();
    },
    jumpTo(id) {
      document.getElementById(id)?.scrollIntoView({ behavior:'smooth', block:'start' });
    },
    enabledAutomodCount() {
      return ['anti_invite','anti_spam','anti_caps','anti_mention']
        .filter(k => Number(this.loki.automod?.[k] || 0) > 0).length;
    },
    automodLabel(key) {
      return {
        anti_invite: 'Invite blocking',
        anti_spam: 'Spam guard',
        anti_caps: 'Caps guard',
        anti_mention: 'Mention guard',
      }[key] || key;
    },
    automodHelp(key) {
      return {
        anti_invite: 'Stops unsolicited server invite links.',
        anti_spam: 'Catches repeated or flood-style messages.',
        anti_caps: 'Calms down excessive all-caps posting.',
        anti_mention: 'Limits ping abuse and mention bombs.',
      }[key] || '';
    },
    commandCategories() {
      return [...new Set(this.commandLibrary.map(item => item.category))];
    },
    filteredCommands() {
      const query = (this.commandSearch || '').toLowerCase().trim();
      return this.commandLibrary.filter(item => {
        const categoryOk = !this.commandCategory || item.category === this.commandCategory;
        const queryOk = !query || (item.search || '').includes(query);
        return categoryOk && queryOk;
      });
    },
    slashCommands() {
      return this.commandLibrary.filter(item => item.slash_enabled);
    },
    filteredSlashCommands() {
      const query = (this.slashSearch || '').toLowerCase().trim();
      if (!query) return this.slashCommands();
      return this.slashCommands().filter(item => (item.search || '').includes(query));
    },
    allOptions() {
      const query = (this.optionSearch || '').toLowerCase().trim();
      const items = [...(this.optionLibrary.general || []), ...(this.optionLibrary.automod || [])];
      if (!query) return items;
      return items.filter(item => `${item.label} ${item.effect} ${item.type} ${item.example || ''}`.toLowerCase().includes(query));
    },
    filteredChannelClusters() {
      const query = (this.channelSearch || '').toLowerCase().trim();
      if (!query) return this.channelLibrary.clusters || [];
      return (this.channelLibrary.clusters || [])
        .map(cluster => ({
          ...cluster,
          channels: cluster.channels.filter(channel =>
            `${channel.name} ${channel.kind} ${channel.topic || ''}`.toLowerCase().includes(query))
        }))
        .filter(cluster => cluster.label.toLowerCase().includes(query) || cluster.channels.length);
    },
    channelOptions() {
      const seen = new Set();
      const options = [];
      for (const cluster of (this.channelLibrary.clusters || [])) {
        for (const channel of (cluster.channels || [])) {
          if (!channel.id || seen.has(channel.id)) continue;
          seen.add(channel.id);
          options.push({
            id: channel.id,
            label: `${cluster.label} - ${channel.name} (${channel.kind})`,
          });
        }
      }
      return options;
    },
    applyChannelSelection(field, value) {
      this.loki.config[field] = value ? Number(value) : '';
    },
    resolvedConfigChannel(field) {
      const value = this.loki.config?.[field];
      if (!value) return 'Not set';
      const current = this.channelNames?.[field];
      if (current) return `#${current}`;
      const match = this.channelOptions().find(channel => String(channel.id) === String(value));
      return match ? match.label : `Channel ${value}`;
    },
    resolvedResourceChannel(id, name = '') {
      if (name) return `#${name}`;
      const match = this.channelOptions().find(channel => String(channel.id) === String(id));
      return match ? match.label : `Channel ${id}`;
    },
    toggleCluster(id) {
      this.expandedClusters[id] = !this.clusterOpen(id);
    },
    clusterOpen(id) {
      return this.expandedClusters[id] !== false;
    },
    toggleAllClusters() {
      const anyClosed = (this.channelLibrary.clusters || []).some(cluster => !this.clusterOpen(cluster.id));
      for (const cluster of (this.channelLibrary.clusters || [])) this.expandedClusters[cluster.id] = anyClosed;
    },
    formatBytes(size) {
      if (!size) return '0 B';
      const units = ['B', 'KB', 'MB'];
      let value = size;
      let unit = 0;
      while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
      }
      return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
    },
    formatAgeSeconds(value) {
      if (value === null || value === undefined || value === '') return 'Unknown';
      const seconds = Number(value);
      if (!Number.isFinite(seconds) || seconds < 0) return 'Unknown';
      if (seconds < 60) return `${Math.floor(seconds)}s ago`;
      if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
      if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
      return `${Math.floor(seconds / 86400)}d ago`;
    },
    filteredAiDocs() {
      const query = (this.aiDocSearch || '').toLowerCase().trim();
      if (!query) return this.aiDocs;
      return this.aiDocs.filter(doc => `${doc.name} ${doc.file} ${doc.summary}`.toLowerCase().includes(query));
    },

    fmtSec(s) {
      if (s < 60) return s + 's';
      if (s < 3600) return Math.floor(s/60) + 'm';
      return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
    },
  };
}
</script>
</body>
</html>
"""


# ─── pywebview window + tray ──────────────────────────────────────────────
def run_flask(app: Flask, port: int):
    import logging

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


def setup_tray(window, mgr: ServiceManager):
    try:
        import pystray
        from PIL import Image
    except Exception:
        return
    img = Image.open(ICON_PATH) if ICON_PATH.exists() else Image.new("RGB", (64, 64), (88, 101, 242))

    def show(_=None, __=None):
        try:
            window.show()
        except Exception:
            pass

    def hide(_=None, __=None):
        try:
            window.hide()
        except Exception:
            pass

    def quit_(icon, _=None):
        mgr.stop_all()
        icon.stop()
        try:
            window.destroy()
        except Exception:
            pass
        try:
            sys.exit(0)
        except SystemExit:
            pass
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Show", show, default=True),
        pystray.MenuItem("Hide", hide),
        pystray.MenuItem("Quit", quit_),
    )
    icon = pystray.Icon("loki", img, "LOKI THE SUN GOD Dashboard", menu)
    threading.Thread(target=icon.run, daemon=True).start()


class JsApi:
    """Bridge exposed to the in-page JavaScript via pywebview.

    Use it to spawn separate native windows for dashboards that refuse to
    embed in an iframe (X-Frame-Options / strict CSP). One window per URL,
    reused on subsequent calls.
    """

    def __init__(self):
        self._windows: dict[str, "webview.Window"] = {}

    def open_window(self, url: str, label: str = "Dashboard"):
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": "bad url"}
        # Reuse existing window for same url
        existing = self._windows.get(url)
        if existing:
            try:
                existing.show()
                return {"ok": True, "reused": True}
            except Exception:
                self._windows.pop(url, None)
        try:
            w = webview.create_window(
                label,
                url,
                width=1200,
                height=820,
                background_color="#0c0d10",
                text_select=True,
                min_size=(700, 500),
            )
            self._windows[url] = w
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_external(self, url: str):
        """Open URL in user's default system browser."""
        try:
            import webbrowser

            webbrowser.open(url, new=2)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def acquire_single_instance_lock(lock_port: int) -> bool:
    global SINGLE_INSTANCE_SOCKET
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
        SINGLE_INSTANCE_SOCKET = sock
        return True
    except OSError:
        try:
            sock.close()
        except OSError:
            pass
        return False


def run_bot_mode():
    configure_workspace_environment()
    print(
        "LOKI THE SUN GOD runtime "
        f"workspace={WORKSPACE_ROOT} env_path={os.environ.get('LOKI_ENV_PATH', '')} "
        f"env_exists={(WORKSPACE_ROOT / '.env').exists()}",
        flush=True,
    )
    import bot as bot_module

    asyncio.run(bot_module.main())


def run_dashboard_mode():
    configure_workspace_environment()
    import dashboard_app as dashboard_module

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "5000"))
    debug = os.getenv("DASHBOARD_DEBUG", "false").lower() == "true"
    try:
        with dashboard_module.app.app_context():
            dashboard_module._ensure_streams_table()
    except Exception as e:
        print(f"WARN: stream table bootstrap: {e}")
    print(f"Dashboard running on http://{host}:{port}")
    dashboard_module.app.run(host=host, port=port, debug=debug)


def runtime_info_snapshot() -> dict:
    return {
        "install_dir": str(INSTALL_DIR),
        "workspace_root": str(WORKSPACE_ROOT),
        "env_path": os.environ.get("LOKI_ENV_PATH", ""),
        "env_exists": (WORKSPACE_ROOT / ".env").exists(),
        "discord_token_configured": bool(env_value("DISCORD_TOKEN")),
        "db_path": os.environ.get("LOKI_DB_PATH", ""),
        "command_root": os.environ.get("LOKI_COMMAND_ROOT", ""),
        "docs_path": os.environ.get("LOKI_DOCS_PATH", ""),
        "runtime_log_path": os.environ.get("LOKI_RUNTIME_LOG_PATH", ""),
    }


def print_runtime_info():
    configure_workspace_environment()
    print(json.dumps(runtime_info_snapshot(), indent=2), flush=True)


def print_bot_cog_info():
    configure_workspace_environment()
    import bot as bot_module

    names = bot_module.discover_cog_names()
    print(json.dumps({"count": len(names), "names": names}, indent=2), flush=True)


def main():
    configure_workspace_environment()
    cfg = load_config()
    if not acquire_single_instance_lock(int(cfg.get("app_lock_port", 7332))):
        print("LOKI THE SUN GOD Dashboard is already running. Exiting.")
        return
    mgr = ServiceManager(cfg)
    mgr.auto_start()

    app = make_app(mgr, cfg)
    port = int(cfg.get("control_port", 7331))
    threading.Thread(target=run_flask, args=(app, port), daemon=True).start()

    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=0.25).read()
            break
        except Exception:
            time.sleep(0.1)

    js_api = JsApi()
    win = webview.create_window(
        "LOKI THE SUN GOD Dashboard",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=820,
        background_color="#0c0d10",
        text_select=True,
        min_size=(900, 600),
        js_api=js_api,
    )
    win.events.loaded += lambda: setup_tray(win, mgr)
    win.events.closed += lambda: mgr.stop_all()

    try:
        webview.start(gui="edgechromium" if os.name == "nt" else None)
    finally:
        mgr.stop_all()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run-bot":
        run_bot_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--run-dashboard":
        run_dashboard_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--runtime-info":
        print_runtime_info()
    elif len(sys.argv) > 1 and sys.argv[1] == "--bot-cog-info":
        print_bot_cog_info()
    else:
        main()
