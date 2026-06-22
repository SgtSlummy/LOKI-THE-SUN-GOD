from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError


def load_env(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def run_command(args: list[str], timeout: int) -> tuple[int, str]:
    proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def query_ollama(prompt: str, model: str, timeout: int) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib_request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("response") or "")


class LokiHermesBridge(BaseHTTPRequestHandler):
    server_version = "LokiHermesBridge/1.0"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/healthz":
            self._send_json(200, {
                "ok": True,
                "service": "loki-hermes-bridge",
                "primary_provider": os.getenv("HERMES_PRIMARY_PROVIDER", "openai-codex"),
                "primary_model": os.getenv("HERMES_PRIMARY_MODEL", "gpt-5.5"),
                "backup_provider": os.getenv("HERMES_BACKUP_PROVIDER", "ollama"),
                "backup_model": os.getenv("HERMES_BACKUP_MODEL", "llama3.2:3b"),
                "obsidian_vault": os.getenv("LOKI_HERMES_OBSIDIAN_VAULT", ""),
            })
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/faust/run":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = self.handle_faust_run(payload)
            self._send_json(200, result)
        except Exception as exc:  # defensive bridge: surface errors to Loki instead of crashing
            self._send_json(500, {"ok": False, "text": f"Loki Hermes Bridge failed: {type(exc).__name__}: {exc}"})

    def handle_faust_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or "").strip()
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        execute = bool(payload.get("execute"))
        target_component = str(payload.get("target_component") or "")
        timeout = int(os.getenv("FAUST_AGI_TIMEOUT_SECONDS", "300"))
        vault = os.getenv("LOKI_HERMES_OBSIDIAN_VAULT", "")
        install_aide = Path(os.getenv("LOKI_INSTALL_AIDE_PROMPT", ""))
        aide_text = install_aide.read_text(encoding="utf-8") if install_aide.exists() else ""
        system_context = f"""
You are the autonomous Loki Hermes Windows node.
Primary model: OpenAI gpt-5.5 via Hermes/openai-codex.
Backup local LLM: Ollama {os.getenv('HERMES_BACKUP_MODEL', 'llama3.2:3b')}.
Cron/offline tasks should prefer Ollama; high-stakes reasoning should prefer gpt-5.5.
Obsidian vault for durable local notes: {vault}.
Request source context: {json.dumps(context, sort_keys=True)}.
Execute requested: {execute}. Target component: {target_component}.
If execute is true, only modify local Loki/Hermes node code/config when the calling Discord user is an admin already authorized by Loki.
Never reveal secrets. Summarize files changed, tests run, and next steps.
{aide_text}
""".strip()
        full_prompt = f"{system_context}\n\nUser request:\n{prompt}"

        provider = os.getenv("HERMES_PRIMARY_PROVIDER", "openai-codex")
        model = os.getenv("HERMES_PRIMARY_MODEL", "gpt-5.5")
        # Effective primary command includes: --provider openai-codex --model gpt-5.5
        hermes_args = ["hermes", "chat", "-q", full_prompt, "--provider", provider, "--model", model, "--quiet"]
        code, output = run_command(hermes_args, timeout=timeout)
        fallback_used = False
        if code != 0 or not output:
            fallback_used = True
            backup_model = os.getenv("HERMES_BACKUP_MODEL", "llama3.2:3b")
            try:
                output = query_ollama(full_prompt, backup_model, timeout=min(timeout, 120))
            except (URLError, TimeoutError, subprocess.SubprocessError) as exc:
                output = f"Primary Hermes call failed and Ollama fallback failed: {exc}"

        run_id = f"loki-hermes-{int(time.time())}"
        return {
            "ok": True,
            "run_id": run_id,
            "text": output or "Loki Hermes Bridge completed without text output.",
            "fallback_used": fallback_used,
            "continue_unprompted": False,
        }

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="Faust-compatible bridge from Loki Discord bot to Hermes Agent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOKI_HERMES_BRIDGE_PORT", "8765")))
    parser.add_argument("--env", default=None)
    args = parser.parse_args()
    load_env(args.env)
    os.environ.setdefault("LOKI_INSTALL_AIDE_PROMPT", str(Path(args.env or ".").resolve().parent / "config" / "install-aide-1bit.md"))
    server = ThreadingHTTPServer((args.host, args.port), LokiHermesBridge)
    print(f"Loki Hermes Bridge listening on http://{args.host}:{args.port}/api/faust/run", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
