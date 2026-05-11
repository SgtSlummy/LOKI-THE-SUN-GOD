from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ChatHandler(BaseHTTPRequestHandler):
    status = 200
    last_request: dict | None = None

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        ChatHandler.last_request = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        if ChatHandler.status >= 400:
            payload = {"error": {"message": "mock provider failure"}}
            self._json(ChatHandler.status, payload)
            return
        self._json(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Mock LOKI THE SUN GOD answer",
                        }
                    }
                ]
            },
        )

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/v1"


def _assert_ai_command_guarded() -> None:
    tree = ast.parse((ROOT / "cogs" / "ai.py").read_text(encoding="utf-8"))
    ask_node = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask"
    )
    decorators = [ast.unparse(decorator) for decorator in ask_node.decorator_list]
    if not any("has_permissions" in decorator and "manage_guild=True" in decorator for decorator in decorators):
        raise AssertionError("/ask must stay gated by Manage Server permission.")
    if not any("cooldown" in decorator for decorator in decorators):
        raise AssertionError("/ask must keep a user cooldown.")


async def _run_client_smoke(base_url: str) -> None:
    from utils.llm_client import LLMConfigError, LLMProviderError, ask_loki_llm, discord_safe_chunks

    old_env = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "LOKI_LLM_MODEL")}
    try:
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            await ask_loki_llm("hello")
        except LLMConfigError:
            pass
        else:
            raise AssertionError("Missing OPENAI_API_KEY did not fail.")

        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ["LOKI_LLM_MODEL"] = "gpt-5.5"
        long_prompt = "word " * 1000
        answer = await ask_loki_llm(long_prompt)
        if answer != "Mock LOKI THE SUN GOD answer":
            raise AssertionError(f"Unexpected mock answer: {answer}")
        request = ChatHandler.last_request or {}
        if request.get("path") != "/v1/chat/completions":
            raise AssertionError(f"Unexpected chat path: {request.get('path')}")
        if request.get("authorization") != "Bearer sk-test":
            raise AssertionError("Authorization header was not sent.")
        body = request.get("body") or {}
        if body.get("model") != "gpt-5.5":
            raise AssertionError("Configured model was not sent.")
        user_message = body.get("messages", [])[-1].get("content", "")
        if len(user_message) > 1800:
            raise AssertionError("Long prompt was not truncated.")
        if any(len(chunk) > 1900 for chunk in discord_safe_chunks("x" * 5000)):
            raise AssertionError("Discord-safe chunks exceeded the message limit.")

        ChatHandler.status = 500
        try:
            await ask_loki_llm("provider should fail")
        except LLMProviderError:
            pass
        else:
            raise AssertionError("Provider HTTP error did not fail.")
    finally:
        ChatHandler.status = 200
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    _assert_ai_command_guarded()
    server, base_url = _start_server()
    try:
        asyncio.run(_run_client_smoke(base_url))
    finally:
        server.shutdown()
    print("LLM smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
