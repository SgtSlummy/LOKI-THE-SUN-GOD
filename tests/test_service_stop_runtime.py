from __future__ import annotations

import asyncio
import logging
import threading
import urllib.error
import urllib.request

import requests

from utils import service_stop


def test_service_stop_watcher_dispatches_callback_without_output(capsys):
    callback_called = threading.Event()
    waited_names: list[str] = []

    def wait_for_signal(event_name: str, _timeout_ms: int | None = None) -> bool:
        waited_names.append(event_name)
        return True

    watcher = service_stop.start_service_stop_watcher(
        callback_called.set,
        event_name="Local\\LokiTHESunGodBot-unit-test",
        wait_for_signal=wait_for_signal,
    )

    assert watcher is not None
    watcher.join(timeout=2)
    assert callback_called.is_set()
    assert waited_names == ["Local\\LokiTHESunGodBot-unit-test"]
    assert capsys.readouterr() == ("", "")


def test_discord_service_stop_schedules_async_client_close(monkeypatch):
    import local_loki_runtime

    callbacks = []

    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    def fake_watcher(callback, **_kwargs):
        callbacks.append(callback)
        return None

    monkeypatch.setattr(service_stop, "start_service_stop_watcher", fake_watcher)
    client = FakeClient()

    async def scenario():
        requested = local_loki_runtime._watch_discord_service_stop(client)
        callbacks[0]()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return requested

    requested = asyncio.run(scenario())

    assert requested.is_set()
    assert client.closed is True


def test_dashboard_service_access_log_removes_oauth_query_values(caplog):
    import dashboard_app

    code_sentinel = "OAUTH_CODE_MUST_NOT_APPEAR"
    state_sentinel = "OAUTH_STATE_MUST_NOT_APPEAR"
    server = dashboard_app.create_dashboard_service_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    caplog.set_level(logging.INFO, logger="werkzeug")
    thread.start()
    try:
        url = (
            f"http://127.0.0.1:{server.server_port}/callback"
            f"?code={code_sentinel}&state={state_sentinel}"
        )
        try:
            urllib.request.urlopen(url, timeout=2)
        except urllib.error.HTTPError:
            pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert code_sentinel not in caplog.text
    assert state_sentinel not in caplog.text
    assert "GET /callback HTTP" in caplog.text


def test_dashboard_service_watcher_shuts_server_then_closes(monkeypatch):
    import dashboard_app

    events: list[str] = []
    serving = threading.Event()
    stopped = threading.Event()
    watcher_threads: list[threading.Thread] = []

    class FakeServer:
        def serve_forever(self):
            events.append("serve")
            serving.set()
            assert stopped.wait(timeout=2)

        def shutdown(self):
            events.append("shutdown")
            stopped.set()

        def server_close(self):
            events.append("close")

    server = FakeServer()
    monkeypatch.setattr(dashboard_app, "create_dashboard_service_server", lambda _host, _port: server)

    def start_watcher(callback):
        watcher = threading.Thread(target=lambda: (serving.wait(timeout=2), callback()))
        watcher.start()
        watcher_threads.append(watcher)
        return watcher

    monkeypatch.setattr(service_stop, "start_service_stop_watcher", start_watcher)

    dashboard_app.run_dashboard_service("127.0.0.1", 5000)
    for watcher in watcher_threads:
        watcher.join(timeout=2)

    assert events == ["serve", "shutdown", "close"]


def test_oauth_callback_logs_exception_type_not_exception_text(monkeypatch, caplog):
    import dashboard_app

    exception_sentinel = "OAUTH_EXCEPTION_TEXT_MUST_NOT_APPEAR"
    monkeypatch.setattr(dashboard_app, "CLIENT_ID", "client-id")
    monkeypatch.setattr(dashboard_app, "CLIENT_SECRET", "configured-client-secret")

    def fail_exchange(*_args, **_kwargs):
        raise requests.RequestException(exception_sentinel)

    monkeypatch.setattr(dashboard_app.requests, "post", fail_exchange)
    caplog.set_level(logging.WARNING, logger=dashboard_app.app.logger.name)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["oauth_state"] = "expected-state"

    response = client.get("/callback?code=oauth-code&state=expected-state")

    assert response.status_code == 302
    assert "RequestException" in caplog.text
    assert exception_sentinel not in caplog.text
