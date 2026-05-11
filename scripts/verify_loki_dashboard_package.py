from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_HEALTH_FIELDS = {
    "ok",
    "database_ok",
    "database_backend",
    "database",
    "db_path",
    "oauth_ready",
    "local_bridge_available",
}
LOKI_ENV_KEYS = {
    "LOKI_APP_ROOT",
    "LOKI_ENV_PATH",
    "LOKI_DB_PATH",
    "LOKI_COMMAND_ROOT",
    "LOKI_DOCS_PATH",
    "LOKI_AI_DOCS_PATH",
    "LOKI_RUNTIME_LOG_PATH",
    "DATABASE_URL",
    "DISCORD_TOKEN",
}


def equivalent_runtime_path(actual: object, expected: Path) -> bool:
    actual_text = str(actual or "")
    expected_paths = {str(expected.resolve())}
    if os.name != "nt":
        try:
            result = subprocess.run(
                ["wslpath", "-w", str(expected.resolve())],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            result = None
        if result and result.returncode == 0 and result.stdout.strip():
            expected_paths.add(result.stdout.strip())

    def normalize_path(path: str) -> str:
        return path.replace("/", "\\").rstrip("\\").casefold()

    return normalize_path(actual_text) in {normalize_path(path) for path in expected_paths}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_health(port: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/healthz"
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = str(exc)
            time.sleep(0.35)
    raise RuntimeError(f"Timed out waiting for packaged dashboard health at {url}: {last_error}")


def process_output_tail(proc: subprocess.Popen, max_lines: int = 30) -> str:
    if not proc.stdout:
        return ""
    try:
        output = proc.stdout.read() or ""
    except Exception:
        return ""
    return "\n".join(output.splitlines()[-max_lines:])


def stop_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def package_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in LOKI_ENV_KEYS:
        env.pop(key, None)
    env.update(overrides)
    return env


def prepare_install_dir(source_exe: Path, install_dir: Path) -> Path:
    packaged_exe = install_dir / source_exe.name
    shutil.copy2(source_exe, packaged_exe)
    config = {
        "workspace_root": str(ROOT),
        "services": [],
        "dashboards": [],
        "control_port": 7331,
        "app_lock_port": 7332,
        "test_guild_id": "1463393482306486387",
    }
    (install_dir / "desktop_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return packaged_exe


def read_runtime_info(exe: Path, install_dir: Path) -> dict:
    return read_json_command(exe, install_dir, "--runtime-info")


def read_bot_cog_info(exe: Path, install_dir: Path) -> dict:
    return read_json_command(exe, install_dir, "--bot-cog-info")


def read_json_command(exe: Path, install_dir: Path, mode: str) -> dict:
    result = subprocess.run(
        [str(exe), mode],
        cwd=install_dir,
        env=package_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr).strip()
        raise RuntimeError(f"Packaged {mode} failed with exit code {result.returncode}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Packaged {mode} did not return JSON: {result.stdout!r}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the packaged LOKI THE SUN GOD dashboard executable.")
    parser.add_argument(
        "--exe",
        type=Path,
        default=ROOT / "dist" / "LOKI-THE-SUN-GOD-Dashboard.exe",
        help="Path to LOKI-THE-SUN-GOD-Dashboard.exe.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for /healthz.")
    args = parser.parse_args()

    exe = args.exe.resolve()
    if not exe.exists():
        print(f"[FAIL] Packaged dashboard executable does not exist: {exe}")
        return 1

    with tempfile.TemporaryDirectory(prefix="loki-dashboard-install-", ignore_cleanup_errors=True) as tmp:
        install_dir = Path(tmp)
        packaged_exe = prepare_install_dir(exe, install_dir)
        runtime_info = read_runtime_info(packaged_exe, install_dir)
        expected_env_path = ROOT / ".env"
        if not equivalent_runtime_path(runtime_info.get("env_path"), expected_env_path):
            print("[FAIL] Packaged runtime did not resolve the workspace .env path.")
            print(json.dumps(runtime_info, indent=2, sort_keys=True))
            return 1
        if runtime_info.get("env_exists") is not True or runtime_info.get("discord_token_configured") is not True:
            print("[FAIL] Packaged runtime could not read the workspace .env without copying secrets.")
            print(json.dumps(runtime_info, indent=2, sort_keys=True))
            return 1
        cog_info = read_bot_cog_info(packaged_exe, install_dir)
        if cog_info.get("count", 0) < 1 or "relay" not in set(cog_info.get("names") or []):
            print("[FAIL] Packaged bot did not discover the expected cogs.")
            print(json.dumps(cog_info, indent=2, sort_keys=True))
            return 1

        port = find_free_port()
        env = package_env(
            DASHBOARD_HOST="127.0.0.1",
            DASHBOARD_PORT=str(port),
            DASHBOARD_DEBUG="false",
        )
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        verified = False
        proc = subprocess.Popen(
            [str(packaged_exe), "--run-dashboard"],
            cwd=install_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        try:
            health = read_health(port, args.timeout)
            missing = sorted(REQUIRED_HEALTH_FIELDS - set(health))
            if missing:
                print(f"[FAIL] Packaged /healthz is missing fields: {', '.join(missing)}")
                print(json.dumps(health, indent=2, sort_keys=True))
                return 1
            if health.get("ok") is not True or health.get("database_ok") is not True:
                print("[FAIL] Packaged /healthz reported an unhealthy dashboard.")
                print(json.dumps(health, indent=2, sort_keys=True))
                return 1
            if health.get("database_backend") not in {"sqlite", "postgres"}:
                print(f"[FAIL] Unexpected database backend: {health.get('database_backend')!r}")
                return 1
            if not equivalent_runtime_path(health.get("db_path"), ROOT / "data" / "bot.db"):
                print("[FAIL] Packaged dashboard did not use the workspace database path.")
                print(json.dumps(health, indent=2, sort_keys=True))
                return 1
            print(
                f"[PASS] Packaged dashboard health verified on port {port} with backend {health['database_backend']}."
            )
            verified = True
            return 0
        finally:
            stop_process_tree(proc)
            if not verified and proc.returncode not in (0, None):
                tail = process_output_tail(proc)
                if tail:
                    print(tail, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
