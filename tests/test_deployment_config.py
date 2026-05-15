from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_RAILWAY = ROOT / "railway.toml"
NIXPACKS = ROOT / "nixpacks.toml"
PROCFILE = ROOT / "Procfile"
ACTIVITY_BRIDGE_RAILWAY = ROOT / "services" / "activity-bridge" / "railway.toml"


def test_root_railway_config_uses_nixpacks_with_restart_policy() -> None:
    config = _read_toml(ROOT_RAILWAY)

    assert config["build"]["builder"] == "NIXPACKS"
    assert config["deploy"]["restartPolicyType"] == "ON_FAILURE"
    assert config["deploy"]["restartPolicyMaxRetries"] == 10
    assert "startCommand" not in config["deploy"], "root start command is centralized in nixpacks.toml"


def test_nixpacks_config_builds_python_venv_and_uses_operator_start_command() -> None:
    config = _read_toml(NIXPACKS)

    assert "python312" in config["phases"]["setup"]["nixPkgs"]

    install_cmd = " && ".join(config["phases"]["install"]["cmds"])
    assert "test -f requirements.txt" in install_cmd
    assert "python -m venv --copies /opt/venv" in install_cmd
    assert "pip install -r requirements.txt" in install_cmd

    start_cmd = config["start"]["cmd"]
    assert ". /opt/venv/bin/activate" in start_cmd
    assert "${LOKI_START_COMMAND:-" in start_cmd
    assert "gunicorn dashboard_app:app" in start_cmd
    assert "${PORT:-8080}" in start_cmd


def test_procfile_exposes_independent_web_and_worker_processes() -> None:
    processes = _read_procfile(PROCFILE)

    assert processes == {
        "web": "gunicorn dashboard_app:app --bind 0.0.0.0:$PORT",
        "worker": "python -m bot",
    }


def test_activity_bridge_railway_config_stays_separate_node_service() -> None:
    config = _read_toml(ACTIVITY_BRIDGE_RAILWAY)

    assert config["build"]["builder"] == "RAILPACK"
    assert config["build"]["buildCommand"] == "npm run build"
    assert config["deploy"]["startCommand"] == "npm run start"
    assert config["deploy"]["restartPolicyType"] == "ON_FAILURE"
    assert config["deploy"]["restartPolicyMaxRetries"] == 10


def _read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _read_procfile(path: Path) -> dict[str, str]:
    processes: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, command = line.partition(":")
        assert separator, f"{path.relative_to(ROOT)}:{line_number} is missing ':'"
        processes[name.strip()] = command.strip()
    return processes


if __name__ == "__main__":
    test_root_railway_config_uses_nixpacks_with_restart_policy()
    test_nixpacks_config_builds_python_venv_and_uses_operator_start_command()
    test_procfile_exposes_independent_web_and_worker_processes()
    test_activity_bridge_railway_config_stays_separate_node_service()
    print("deployment config contracts passed")
