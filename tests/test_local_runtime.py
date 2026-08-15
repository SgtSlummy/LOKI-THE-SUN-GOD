import importlib.util
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from utils import credential_store, runtime_paths

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "local_loki_runtime.py"
DISCORD_TOKEN_NAME = "DISCORD_" + "TOKEN"


def load_runtime_module():
    spec = importlib.util.spec_from_file_location("local_loki_runtime", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preflight_is_redacted_and_fail_closed_without_token(tmp_path, monkeypatch):
    isolated_env = tmp_path / "isolated.env"
    isolated_env.write_text("# intentionally empty\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("LOKI_ENV_PATH", str(isolated_env))
    monkeypatch.setattr(credential_store, "load_credentials", lambda: {})

    payload = load_runtime_module().preflight()

    assert payload["ok"] is False
    assert payload["token_configured"] is False
    assert payload["provider_policy"]["cloud_provider_fallback"] is False
    assert "DISCORD_TOKEN" not in json.dumps(payload)


def test_preflight_reports_local_council_gate(tmp_path, monkeypatch):
    config = tmp_path / "council.yaml"
    config.write_text(
        'mutation_gate:\n  must_route_through: "THE FOOL"\n'
        'approval_style: "human_ok_per_interaction_batch"\n',
        encoding="utf-8",
    )
    isolated_env = tmp_path / "isolated.env"
    isolated_env.write_text("# intentionally empty\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("LOKI_AGENT_COUNCIL_CONFIG", str(config))
    monkeypatch.setenv("LOKI_ENV_PATH", str(isolated_env))
    monkeypatch.setattr(credential_store, "load_credentials", lambda: {})

    payload = load_runtime_module().preflight()

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


def test_runtime_config_precedence_is_credential_then_process_then_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / "lokithesungod.env"
    env_path.write_text(
        f"{DISCORD_TOKEN_NAME}=dotenv-value\nOPENAI_API_KEY=dotenv-openai\nDATABASE_URL=dotenv-database\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LOKI_ENV_PATH", str(env_path))
    monkeypatch.setenv("DISCORD_TOKEN", "process-value")
    monkeypatch.setenv("OPENAI_API_KEY", "process-openai")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        credential_store,
        "load_credentials",
        lambda: {"DISCORD_TOKEN": "credential-value"},
    )

    runtime = load_runtime_module()
    try:
        runtime._load_dotenv()

        assert os.environ["DISCORD_TOKEN"] == "credential-value"
        assert os.environ["OPENAI_API_KEY"] == "process-openai"
        assert os.environ["DATABASE_URL"] == "dotenv-database"
    finally:
        os.environ.pop("DATABASE_URL", None)


def test_legacy_override_argument_cannot_replace_process_environment(tmp_path, monkeypatch):
    env_path = tmp_path / "lokithesungod.env"
    env_path.write_text(f"{DISCORD_TOKEN_NAME}=dotenv-value\n", encoding="utf-8")
    monkeypatch.setenv("LOKI_ENV_PATH", str(env_path))
    monkeypatch.setenv("DISCORD_TOKEN", "process-value")
    monkeypatch.setattr(credential_store, "load_credentials", lambda: {})

    loaded = runtime_paths.load_app_dotenv(override=True)

    assert loaded == env_path
    assert os.environ["DISCORD_TOKEN"] == "process-value"


def test_credential_failure_preserves_other_managed_and_fallback_values(tmp_path, monkeypatch, caplog):
    env_path = tmp_path / "lokithesungod.env"
    env_path.write_text("DATABASE_URL=dotenv-database\n", encoding="utf-8")
    monkeypatch.setenv("LOKI_ENV_PATH", str(env_path))
    monkeypatch.setenv("DISCORD_TOKEN", "process-value")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(credential_store, "win32cred", object())

    def read_credential(name):
        if name == "DISCORD_TOKEN":
            raise PermissionError("sensitive-exception-text")
        if name == "OPENAI_API_KEY":
            return "managed-openai"
        return None

    monkeypatch.setattr(credential_store, "read_credential", read_credential)

    try:
        runtime_paths.load_app_dotenv()

        assert os.environ["DISCORD_TOKEN"] == "process-value"
        assert os.environ["DATABASE_URL"] == "dotenv-database"
        assert os.environ["OPENAI_API_KEY"] == "managed-openai"
        assert "DISCORD_TOKEN" in caplog.text
        assert "PermissionError" in caplog.text
        assert "sensitive-exception-text" not in caplog.text
        messages = [record.getMessage() for record in caplog.records if record.name == credential_store.__name__]
        assert messages == ["Credential Manager read failed for DISCORD_TOKEN (PermissionError)"]
    finally:
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("OPENAI_API_KEY", None)


def test_windows_stable_config_precedes_development_dotenv(tmp_path, monkeypatch):
    if os.name != "nt":
        return
    program_data = tmp_path / "ProgramData"
    stable = program_data / "Loki" / "config" / "lokithesungod.env"
    app_root = tmp_path / "app"
    stable.parent.mkdir(parents=True)
    app_root.mkdir()
    stable.write_text(f"{DISCORD_TOKEN_NAME}=stable-value\n", encoding="utf-8")
    (app_root / ".env").write_text(f"{DISCORD_TOKEN_NAME}=development-value\n", encoding="utf-8")
    monkeypatch.delenv("LOKI_ENV_PATH", raising=False)
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(program_data))
    monkeypatch.setenv("LOKI_APP_ROOT", str(app_root))
    monkeypatch.setattr(credential_store, "load_credentials", lambda: {})

    try:
        loaded = runtime_paths.load_app_dotenv()

        assert loaded == stable
        assert os.environ["DISCORD_TOKEN"] == "stable-value"
    finally:
        os.environ.pop("DISCORD_TOKEN", None)
