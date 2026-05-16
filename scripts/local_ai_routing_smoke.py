from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class OllamaTagsHandler(BaseHTTPRequestHandler):
    models = [
        {"name": "llama3.2:3b"},
        {"name": "qwen2.5-coder:7b"},
        {"name": "dolphin3:8b"},
    ]

    def do_GET(self) -> None:
        if self.path == "/api/tags":
            body = {"models": self.models}
            payload = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.end_headers()


    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_ollama_fixture() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaTagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> int:
    old_env = {key: os.environ.get(key) for key in os.environ if key.startswith("LOKI_") or key == "DATA_DIR"}
    server, ollama_host = _start_ollama_fixture()
    try:
        with tempfile.TemporaryDirectory(prefix="loki-ai-routing-") as tmp:
            tmp_path = Path(tmp)
            router_env_path = tmp_path / "9router" / ".env"
            router_data_dir = tmp_path / "9router-data"
            router_env_path.parent.mkdir(parents=True, exist_ok=True)
            router_env_path.write_text(f"DATA_DIR={router_data_dir}\n", encoding="utf-8")
            os.environ.update(
                {
                    "LOKI_ENV_PATH": str(tmp_path / ".env"),
                    "LOKI_CODEX_SETTINGS_PATH": str(tmp_path / "codex-settings.json"),
                    "LOKI_ROUTER_REPO_PATH": str(tmp_path / "9router"),
                    "LOKI_ROUTER_ENV_PATH": str(router_env_path),
                    "DATA_DIR": str(router_data_dir),
                }
            )

            from utils import operator_surface

            status = operator_surface.ollama_router_status(ollama_host=ollama_host)
            if not status["ollama_up"]:
                raise AssertionError("Mock Ollama server was not detected as online.")
            if status["preferred_local_model"] != "dolphin3:8b":
                raise AssertionError(f"Unexpected selected model: {status['preferred_local_model']}")
            if status["local_model_source"] != "preferred" or not status["local_model_ready"]:
                raise AssertionError("Preferred local model status was not marked ready.")

            original_models = OllamaTagsHandler.models
            try:
                OllamaTagsHandler.models = [{"name": "qwen2.5-coder:7b"}]
                fallback_status = operator_surface.ollama_router_status(ollama_host=ollama_host)
            finally:
                OllamaTagsHandler.models = original_models
            if fallback_status["preferred_local_model"] != "qwen2.5-coder:7b":
                raise AssertionError("qwen2.5-coder:7b should remain the fallback when dolphin3:8b is absent.")

            result = operator_surface.configure_9router_local_model(ollama_host, status["preferred_local_model"])
            router_db = Path(result["db_path"])
            data = json.loads(router_db.read_text(encoding="utf-8"))
            expected_route = "ollama-local/dolphin3:8b"
            if data["modelAliases"].get("local-default") != expected_route:
                raise AssertionError("9router local-default alias was not written.")
            connection = next(
                item for item in data["providerConnections"] if item.get("provider") == "ollama-local"
            )
            if connection["providerSpecificData"].get("baseUrl") != ollama_host:
                raise AssertionError("9router Ollama base URL was not preserved.")
            if connection["providerSpecificData"].get("enabledModels") != ["dolphin3:8b"]:
                raise AssertionError("9router enabled model list was not written.")
            custom_model_ids = {
                item.get("id")
                for item in data["customModels"]
                if item.get("providerAlias") == "ollama-local" and item.get("type", "llm") == "llm"
            }
            if "dolphin3:8b" not in custom_model_ids:
                raise AssertionError("9router custom model list is missing the local model.")

            offline = operator_surface.ollama_router_status(ollama_host="http://127.0.0.1:9")
            if offline["ollama_up"] or offline["local_model_ready"]:
                raise AssertionError("Offline Ollama should produce a degraded local model state.")
            if "ollama pull dolphin3:8b" not in offline["local_model_setup_hint"]:
                raise AssertionError("Offline Ollama state did not include the setup hint.")

        print("local AI routing smoke test passed")
        return 0
    finally:
        server.shutdown()
        for key in list(os.environ):
            if key.startswith("LOKI_") or key == "DATA_DIR":
                if key in old_env and old_env[key] is not None:
                    os.environ[key] = old_env[key]
                elif key not in old_env or old_env[key] is None:
                    os.environ.pop(key, None)


if __name__ == "__main__":
    raise SystemExit(main())
