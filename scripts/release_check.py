from __future__ import annotations

import argparse
import ast
import importlib
import os
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _maybe_reexec_from_venv() -> None:
    if os.environ.get("LOKI_RELEASE_CHECK_NO_VENV"):
        return
    if sys.prefix != sys.base_prefix:
        return

    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not venv_python.exists():
        return
    if Path(sys.executable).absolute() == venv_python.absolute():
        return
    check = subprocess.run(
        [str(venv_python), "-c", "import dotenv"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if check.returncode != 0:
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


_maybe_reexec_from_venv()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv = importlib.import_module("dotenv").load_dotenv
load_dotenv(ROOT / ".env")
TRUTHY = {"1", "true", "yes", "on"}


def compile_sources() -> tuple[bool, str]:
    skipped_dirs = {"build", "dist", "__pycache__", "_tmp", ".venv", "venv"}
    candidates = []
    for path in ROOT.rglob("*.py"):
        if any(part in skipped_dirs for part in path.parts):
            continue
        if path.name.endswith((".bak.py", ".trim.py")):
            continue
        candidates.append(path)

    for path in candidates:
        py_compile.compile(str(path), doraise=True)
    return True, f"Compiled {len(candidates)} Python files."


def environment_report(strict: bool) -> tuple[bool, str]:
    required = {
        "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN", ""),
        "DISCORD_CLIENT_ID": os.getenv("DISCORD_CLIENT_ID", ""),
        "DISCORD_CLIENT_SECRET": os.getenv("DISCORD_CLIENT_SECRET", ""),
        "REDIRECT_URI": os.getenv("REDIRECT_URI", ""),
        "DASHBOARD_SECRET_KEY": os.getenv("DASHBOARD_SECRET_KEY", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if strict and missing:
        return False, "Missing required env: " + ", ".join(missing)
    if missing:
        return True, "Env warnings: missing " + ", ".join(missing)
    return True, "Required environment values are present."


def database_report() -> tuple[bool, str]:
    from utils import db as shared_db

    shared_db.init_sync()
    if shared_db.using_postgres():
        return True, "Database ready through DATABASE_URL."
    db_path = shared_db.current_db_path()
    return db_path.exists(), f"Database ready at {db_path}"


def database_smoke_report() -> tuple[bool, str]:
    script = ROOT / "scripts" / "db_smoke_test.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    detail = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        return False, detail or f"Database smoke test failed with code {result.returncode}."
    return True, detail.splitlines()[-1] if detail else "Database smoke tests passed."


def catalog_report() -> tuple[bool, str]:
    from utils.command_catalog import parse_command_catalog

    catalog = parse_command_catalog(ROOT)
    slash = [item for item in catalog if item.get("slash_enabled")]
    missing = [item["full_name"] for item in slash if item.get("description") == "No description in source yet."]
    required = {
        "automod mentions",
        "automod spamthreshold",
        "ar test",
        "suggestion server",
        "welcome preview",
        "rr add",
        "ticket status",
    }
    absent = sorted(required - {item["full_name"] for item in catalog})
    if not slash:
        return False, "No slash-capable commands were discovered."
    if missing:
        return False, f"{len(missing)} slash commands are still missing descriptions."
    if absent:
        return False, "Catalog is missing expected commands: " + ", ".join(absent)
    return True, f"Catalog ready with {len(catalog)} commands and {len(slash)} slash-capable entries."


def slash_signature_report() -> tuple[bool, str]:
    unsupported: list[str] = []
    for path in sorted((ROOT / "cogs").glob("*.py")):
        if path.name.endswith((".bak", ".trim.bak", ".bak.py", ".trim.py")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorator_names = []
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                decorator_names.append(_decorator_name(target))
            if not any(
                name in {"commands.hybrid_command", "commands.hybrid_group"} or name.endswith(".command")
                for name in decorator_names
            ):
                continue
            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                if arg.arg in {"self", "ctx", "interaction"} or arg.annotation is None:
                    continue
                if _annotation_name(arg.annotation).endswith("discord.Message"):
                    unsupported.append(f"{path.name}:{node.name}:{arg.arg}")
    if unsupported:
        return False, "Hybrid/slash command signatures still use discord.Message: " + ", ".join(unsupported[:10])
    return True, "Hybrid and slash command signatures use supported parameter shapes."


def relay_report() -> tuple[bool, str]:
    import cogs.relay  # noqa: F401

    enabled = os.getenv("RELAY_ENABLED", "false").lower() in TRUTHY
    allow_local_sqlite = os.getenv("ALLOW_LOCAL_SQLITE_RELAY", "false").lower() in TRUTHY
    if not enabled:
        return True, "Relay cog imports; relay is disabled by environment."
    if not os.getenv("DATABASE_URL", "").strip():
        if not allow_local_sqlite:
            return False, "Relay enabled but DATABASE_URL is missing; relay workers must share one dedupe database."
    missing = [name for name in ("RELAY_GUILD_ID",) if not os.getenv(name, "").strip()]
    has_targets = bool(
        os.getenv("RELAY_TARGET_CHANNEL_IDS", "").strip() or os.getenv("RELAY_TARGET_CHANNEL_NAMES", "").strip()
    )
    if not has_targets:
        missing.append("RELAY_TARGET_CHANNEL_IDS or RELAY_TARGET_CHANNEL_NAMES")
    if missing:
        return False, "Relay enabled but missing " + ", ".join(missing)
    relay_log = ROOT / "data" / "relay.log"
    if relay_log.exists():
        recent_log = relay_log.read_text(encoding="utf-8", errors="replace")[-16000:]
        target_ids = [
            channel_id.strip()
            for channel_id in os.getenv("RELAY_TARGET_CHANNEL_IDS", "").split(",")
            if channel_id.strip()
        ]
        relayed_count = recent_log.count("relayed message to")
        target_hits = sum(1 for channel_id in target_ids if channel_id in recent_log)
        if relayed_count >= 2 and (not target_ids or target_hits >= min(2, len(target_ids))):
            if allow_local_sqlite and not os.getenv("DATABASE_URL", "").strip():
                return True, "Relay config valid with local SQLite override; recent two-way relay evidence is present."
            return True, "Relay config valid and recent two-way relay evidence is present."
        if "ready guild=" in recent_log:
            if allow_local_sqlite and not os.getenv("DATABASE_URL", "").strip():
                return True, "Relay config valid with local SQLite override and readiness log is present."
            return True, "Relay config valid and readiness log is present."
    if allow_local_sqlite and not os.getenv("DATABASE_URL", "").strip():
        return True, "Relay config valid with local SQLite override; no recent readiness log found in data/relay.log."
    return True, "Relay config valid; no recent readiness log found in data/relay.log."


def outbound_guard_report() -> tuple[bool, str]:
    from utils.outbound_post_guard import run_self_check

    run_self_check()
    return True, "Outbound guard enforces lease fence, channel-scoped dedupe, DB fail-closed sends, and audit rows."


def worker_singleton_report() -> tuple[bool, str]:
    from utils.worker_singleton import run_self_check

    run_self_check()
    return True, "Worker singleton refuses local duplicates, supports takeover, and fences stale owners."


def _decorator_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _decorator_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _annotation_name(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def dashboard_report() -> tuple[bool, str]:
    import dashboard_app

    with dashboard_app.app.test_client() as client:
        health = client.get("/healthz")
        if health.status_code != 200:
            return False, f"Dashboard healthz failed with {health.status_code}."
        landing = client.get("/")
        if landing.status_code != 200:
            return False, f"Dashboard landing page failed with {landing.status_code}."
        callback = client.get("/callback")
        if callback.status_code not in (302, 303):
            return False, f"Dashboard callback guard failed with {callback.status_code}."
        with client.session_transaction() as session:
            session["user"] = {"id": "release-check", "username": "Release Check"}
            session["guilds"] = [{"id": "1", "name": "Release Check Guild", "icon": None, "permissions": str(0x8)}]
            session["token"] = "release-check"
            session["_csrf_token"] = "release-check-token"
        try:
            dashboard_app.db_exec(
                "DELETE FROM event_reminders WHERE event_id IN (SELECT id FROM events WHERE guild_id=1)"
            )
            dashboard_app.db_exec(
                "DELETE FROM event_reposts WHERE event_id IN (SELECT id FROM events WHERE guild_id=1)"
            )
            dashboard_app.db_exec("DELETE FROM events WHERE guild_id=1")
            dashboard_app.db_exec(
                "INSERT INTO events"
                "(guild_id, channel_id, message_id, title, description, starts_at, host_id, color, location) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    1,
                    0,
                    0,
                    "Release Check Event",
                    "Verifies event rendering with saved rows.",
                    1893456000,
                    0,
                    0x57F287,
                    "Dashboard",
                ),
            )
            for path in (
                "/guilds",
                "/guild/1",
                "/guild/1/forms",
                "/guild/1/streams",
                "/guild/1/tickets",
                "/guild/1/commands",
            ):
                response = client.get(path)
                if response.status_code != 200:
                    return False, f"Dashboard route {path} failed with {response.status_code}."
            events_response = client.get("/guild/1/events")
            if events_response.status_code != 200:
                return False, f"Dashboard route /guild/1/events failed with {events_response.status_code}."
        finally:
            dashboard_app.db_exec(
                "DELETE FROM event_reminders WHERE event_id IN (SELECT id FROM events WHERE guild_id=1)"
            )
            dashboard_app.db_exec(
                "DELETE FROM event_reposts WHERE event_id IN (SELECT id FROM events WHERE guild_id=1)"
            )
            dashboard_app.db_exec("DELETE FROM events WHERE guild_id=1")
    return True, "Dashboard public and authenticated routes are healthy in-process."


def desktop_report() -> tuple[bool, str]:
    import desktop_app

    cfg = desktop_app.load_config()
    mgr = desktop_app.ServiceManager(cfg)
    app = desktop_app.make_app(mgr, cfg)
    with app.test_client() as client:
        status = client.get("/api/status")
        commands = client.get("/api/loki/command-library")
        diagnostics = client.get("/api/diagnostics")
        dashboards = client.get("/api/dashboards")
        if status.status_code != 200:
            return False, f"Desktop /api/status failed with {status.status_code}."
        if commands.status_code != 200:
            return False, f"Desktop command library failed with {commands.status_code}."
        if diagnostics.status_code != 200:
            return False, f"Desktop diagnostics failed with {diagnostics.status_code}."
        if dashboards.status_code != 200:
            return False, f"Desktop dashboards failed with {dashboards.status_code}."
        dashboard_items = (dashboards.get_json() or {}).get("dashboards", [])
        dashboard_ids = {item.get("id") for item in dashboard_items}
        if "loki_cr" in dashboard_ids:
            return False, "Desktop dashboards still expose the legacy 9router Claude card."
        if "mee6_dashboard" not in dashboard_ids:
            return False, "Desktop dashboards are missing the MEE6 dashboard card."
        for item in dashboard_items:
            label = str(item.get("label") or "").lower().replace("·", "-")
            url = str(item.get("url") or "").lower()
            if ("9router" in label and "claude" in label) or "/dashboard/claude-router" in url:
                return False, "Desktop dashboards still expose a Claude-router card."
        command_total = len((commands.get_json() or {}).get("commands", []))
    return True, f"Desktop operator API is healthy with {command_total} indexed commands."


def mcp_report() -> tuple[bool, str]:
    script = ROOT / "scripts" / "mcp_smoke_test.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr).strip()
        return False, detail or f"MCP smoke test failed with code {result.returncode}."
    detail = (result.stdout.strip() or result.stderr.strip() or "loki_mcp smoke test passed").splitlines()[-1]
    return True, detail


def llm_report() -> tuple[bool, str]:
    script = ROOT / "scripts" / "llm_smoke_test.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    detail = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        return False, detail or f"LLM smoke test failed with code {result.returncode}."
    return True, detail.splitlines()[-1] if detail else "LLM smoke test passed."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LOKI THE SUN GOD release preflight checks.")
    parser.add_argument("--strict-env", action="store_true", help="Fail if required environment values are missing.")
    args = parser.parse_args()

    checks = [
        ("Compile", compile_sources),
        ("Environment", lambda: environment_report(args.strict_env)),
        ("Database", database_report),
        ("DB Smoke", database_smoke_report),
        ("Catalog", catalog_report),
        ("Slash Signatures", slash_signature_report),
        ("Relay", relay_report),
        ("Outbound Guard", outbound_guard_report),
        ("Worker Singleton", worker_singleton_report),
        ("Dashboard", dashboard_report),
        ("Desktop", desktop_report),
        ("MCP", mcp_report),
        ("LLM", llm_report),
    ]

    failed = False
    for label, check in checks:
        try:
            ok, detail = check()
        except Exception as exc:
            ok = False
            detail = f"{type(exc).__name__}: {exc}"
        prefix = "PASS" if ok else "FAIL"
        print(f"[{prefix}] {label}: {detail}")
        if not ok:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
