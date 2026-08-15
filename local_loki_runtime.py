"""Local LOKI runtime with a loopback health surface.

The default mode only opens the Discord gateway and reports Discord's native
connection/heartbeat state.  Full LOKI cogs are opt-in with ``--mode full``.
No provider, Hermes gateway, cron job, or public listener is started here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from utils import runtime_paths, service_stop

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 9101
TRUTHY = {"1", "true", "yes", "on"}
LOG = logging.getLogger("loki.local-runtime")


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _probe_json(url: str, timeout: float = 0.8) -> tuple[bool, dict[str, Any] | None, str | None]:
    if not _loopback_url(url):
        return False, None, "non_loopback_url_blocked"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "LOKI-local-runtime/1"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback-only guard above
            payload = json.loads(response.read().decode("utf-8"))
        return True, payload if isinstance(payload, dict) else None, None
    except HTTPError as exc:
        return False, None, f"http_{exc.code}"
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False, None, "unreachable_or_invalid_response"


def _ollama_tags_url(env: Mapping[str, str]) -> str:
    base = (env.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    return f"{base}/tags" if base.endswith("/api") else f"{base}/api/tags"


def _default_council_config() -> Path:
    return ROOT.parent.parent / "Agentic Improv" / "config" / "hermes-tarot-agent-council.yaml"


def component_readiness(env: Mapping[str, str] | None = None, *, probe_network: bool = True) -> dict[str, Any]:
    """Return redacted, read-only readiness for the requested local collaborators."""

    values = env or os.environ
    hermes_path = values.get("LOKI_HERMES_PATH") or shutil.which("hermes")
    if not hermes_path:
        known = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
        hermes_path = str(known) if known.exists() else None

    council_path = Path(values.get("LOKI_AGENT_COUNCIL_CONFIG") or _default_council_config())
    council_text = council_path.read_text(encoding="utf-8") if council_path.is_file() else ""
    council_ready = (
        'must_route_through: "THE FOOL"' in council_text
        and "human_ok_per_interaction_batch" in council_text
    )

    components: dict[str, Any] = {
        "hermes": {
            "state": "available_advisory" if hermes_path else "unavailable",
            "path_present": bool(hermes_path),
            "gateway_started": False,
            "cron_started": False,
            "mutation_authority": False,
        },
        "agents_council": {
            "state": "available_advisory" if council_ready else "unavailable_or_unverified",
            "config_present": council_path.is_file(),
            "human_batch_gate": council_ready,
            "mutation_authority": False,
        },
        "ollama": {
            "state": "not_probed",
            "local_only": True,
            "model_count": None,
        },
        "tarot_router": {
            "state": "disabled_by_default",
            "enabled": False,
            "cloud_provider_fallback": False,
            "mutation_authority": False,
        },
    }

    if probe_network:
        ollama_ok, ollama_payload, ollama_error = _probe_json(_ollama_tags_url(values))
        models = ollama_payload.get("models") if ollama_payload else None
        components["ollama"].update(
            state="available_local" if ollama_ok else "unavailable",
            model_count=len(models) if isinstance(models, list) else 0 if ollama_ok else None,
            error=ollama_error,
        )

        tarot_url = values.get("LOKI_TAROT_ROUTER_HEALTH_URL") or "http://127.0.0.1:8642/healthz"
        tarot_ok, _, tarot_error = _probe_json(tarot_url)
        components["tarot_router"].update(
            state="available_but_disabled" if tarot_ok else "disabled_or_unavailable",
            local_endpoint=_loopback_url(tarot_url),
            error=tarot_error,
        )

    return components


@dataclass
class RuntimeState:
    mode: str
    token_configured: bool
    components: dict[str, Any]
    started_at: str = field(default_factory=utc_now)
    discord_connected: bool = False
    discord_ready: bool = False
    discord_resumed: bool = False
    discord_latency_ms: float | None = None
    bot_user: str | None = None
    last_event: str | None = None
    last_event_at: str | None = None
    last_error: str | None = None
    stopped: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def event(self, name: str, **fields: Any) -> None:
        with self._lock:
            self.last_event = name
            self.last_event_at = utc_now()
            for key, value in fields.items():
                setattr(self, key, value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            ready = self.token_configured and self.discord_connected and self.discord_ready and not self.stopped
            return {
                "schema": "loki-local-heartbeat/v1",
                "ok": ready,
                "state": "ready" if ready else "starting_or_blocked",
                "mode": self.mode,
                "token_configured": self.token_configured,
                "discord": {
                    "connected": self.discord_connected,
                    "ready": self.discord_ready,
                    "resumed": self.discord_resumed,
                    "latency_ms": self.discord_latency_ms,
                    "bot_user": self.bot_user,
                    "last_event": self.last_event,
                    "last_event_at": self.last_event_at,
                },
                "components": self.components,
                "provider_policy": {
                    "local_ollama_allowed": True,
                    "tarot_router_enabled": False,
                    "cloud_provider_fallback": False,
                    "paid_routes_enabled": False,
                },
                "started_at": self.started_at,
                "last_error": self.last_error,
            }


class HealthHandler(BaseHTTPRequestHandler):
    server: "HealthServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] not in {"/healthz", "/heartbeat", "/api/health"}:
            self.send_error(404)
            return
        payload = json.dumps(self.server.state.snapshot(), separators=(",", ":")).encode("utf-8")
        self.send_response(200 if self.server.state.snapshot()["ok"] else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class HealthServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, host: str, port: int, state: RuntimeState):
        super().__init__((host, port), HealthHandler)
        self.state = state


def _load_dotenv() -> None:
    runtime_paths.load_app_dotenv()


def _watch_discord_service_stop(client: Any) -> asyncio.Event:
    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()

    async def close_client() -> None:
        try:
            await client.close()
        except Exception:
            return

    def request_stop() -> None:
        def dispatch() -> None:
            stop_requested.set()
            asyncio.create_task(close_client())

        loop.call_soon_threadsafe(dispatch)

    service_stop.start_service_stop_watcher(request_stop)
    return stop_requested


async def _run_discord(mode: str, token: str, state: RuntimeState) -> None:
    import discord

    if mode == "heartbeat":
        intents = discord.Intents.none()

        class HeartbeatClient(discord.Client):
            async def on_connect(self) -> None:
                state.event("on_connect", discord_connected=True)

            async def on_ready(self) -> None:
                state.event(
                    "on_ready",
                    discord_connected=True,
                    discord_ready=True,
                    discord_resumed=False,
                    discord_latency_ms=round(self.latency * 1000, 2),
                    bot_user=str(self.user) if self.user else None,
                )
                LOG.info("Discord heartbeat client ready as %s", self.user)

            async def on_resumed(self) -> None:
                state.event("on_resumed", discord_connected=True, discord_ready=True, discord_resumed=True)

            async def on_disconnect(self) -> None:
                state.event("on_disconnect", discord_connected=False, discord_ready=False)

        client: discord.Client = HeartbeatClient(intents=intents)
    else:
        from bot import LokiBot

        class ManagedLokiBot(LokiBot):
            async def on_connect(self) -> None:
                state.event("on_connect", discord_connected=True)

            async def on_ready(self) -> None:
                await super().on_ready()
                state.event(
                    "on_ready",
                    discord_connected=True,
                    discord_ready=True,
                    discord_resumed=False,
                    discord_latency_ms=round(self.latency * 1000, 2),
                    bot_user=str(self.user) if self.user else None,
                )
                LOG.info("Full LOKI runtime ready as %s", self.user)

            async def on_resumed(self) -> None:
                state.event("on_resumed", discord_connected=True, discord_ready=True, discord_resumed=True)

            async def on_disconnect(self) -> None:
                state.event("on_disconnect", discord_connected=False, discord_ready=False)

        client = ManagedLokiBot()

    stop_requested = _watch_discord_service_stop(client)
    try:
        await client.start(token)
    except Exception as exc:
        if stop_requested.is_set():
            return
        state.last_error = type(exc).__name__
        raise
    finally:
        if not client.is_closed():
            await client.close()


def preflight() -> dict[str, Any]:
    _load_dotenv()
    state = RuntimeState(
        mode=os.getenv("LOKI_LOCAL_RUNTIME_MODE", "heartbeat"),
        token_configured=bool((os.getenv("DISCORD_TOKEN") or "").strip()),
        components=component_readiness(probe_network=False),
    )
    return state.snapshot()


async def run(args: argparse.Namespace) -> int:
    _load_dotenv()
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    state = RuntimeState(
        mode=args.mode,
        token_configured=bool(token),
        components=component_readiness(),
    )
    if args.mode == "full" and not truthy(os.getenv("LOKI_LOCAL_ALLOW_FULL")):
        state.last_error = "full mode requires LOKI_LOCAL_ALLOW_FULL=true"
        print(json.dumps(state.snapshot(), indent=2, sort_keys=True))
        return 3
    if not token:
        state.last_error = "DISCORD_TOKEN not configured; refusing to start the gateway"
        print(json.dumps(state.snapshot(), indent=2, sort_keys=True))
        return 2

    server = HealthServer(args.host, args.port, state)
    server_thread = threading.Thread(target=server.serve_forever, name="loki-health", daemon=True)
    server_thread.start()
    LOG.info("Loopback health surface listening at http://%s:%s/healthz", args.host, args.port)
    try:
        await _run_discord(args.mode, token, state)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        LOG.error("LOKI Discord runtime stopped with an error (%s)", type(error).__name__)
        return 1
    finally:
        state.stopped = True
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LOKI locally with a loopback Discord heartbeat surface.")
    parser.add_argument("--mode", choices=("heartbeat", "full"), default="heartbeat")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOKI_LOCAL_HEALTH_PORT", DEFAULT_PORT)))
    parser.add_argument("--preflight", action="store_true", help="Print redacted local readiness and exit.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = parse_args()
    if args.preflight:
        print(json.dumps(preflight(), indent=2, sort_keys=True))
        return 0
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
