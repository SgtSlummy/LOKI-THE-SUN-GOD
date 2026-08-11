import importlib.util
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "local_loki_runtime.py"


def load_runtime_module():
    spec = importlib.util.spec_from_file_location("local_loki_runtime", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preflight_is_redacted_and_fail_closed_without_token(tmp_path):
    env = os.environ.copy()
    env.pop("DISCORD_TOKEN", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(RUNTIME), "--preflight"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["token_configured"] is False
    assert payload["provider_policy"]["cloud_provider_fallback"] is False
    assert "DISCORD_TOKEN" not in result.stdout


def test_preflight_reports_local_council_gate(tmp_path):
    config = tmp_path / "council.yaml"
    config.write_text(
        'mutation_gate:\n  must_route_through: "THE FOOL"\n'
        'approval_style: "human_ok_per_interaction_batch"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("DISCORD_TOKEN", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["LOKI_AGENT_COUNCIL_CONFIG"] = str(config)
    result = subprocess.run(
        [sys.executable, str(RUNTIME), "--preflight"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["components"]["agents_council"]["human_batch_gate"] is True
    assert payload["components"]["agents_council"]["mutation_authority"] is False


def test_health_surface_is_503_until_discord_is_ready():
    runtime = load_runtime_module()
    state = runtime.RuntimeState(
        mode="heartbeat",
        token_configured=True,
        components=runtime.component_readiness(probe_network=False),
    )
    server = runtime.HealthServer("127.0.0.1", 0, state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/healthz"
    try:
        try:
            urllib.request.urlopen(url, timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 503
        else:
            raise AssertionError("health must fail closed before Discord is ready")

        state.event(
            "on_ready",
            discord_connected=True,
            discord_ready=True,
            discord_latency_ms=12.5,
            bot_user="Loki#0001",
        )
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.load(response)
        assert payload["ok"] is True
        assert payload["discord"]["latency_ms"] == 12.5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
