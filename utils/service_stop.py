from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping

try:
    import win32api
    import win32con
    import win32event
except ImportError:  # pragma: no cover - Ubuntu CI
    win32api = None
    win32con = None
    win32event = None


STOP_EVENT_ENV = "LOKI_SERVICE_STOP_EVENT"
PYWIN32_AVAILABLE = all(module is not None for module in (win32api, win32con, win32event))


def configured_stop_event(environment: Mapping[str, str] | None = None) -> str | None:
    values = os.environ if environment is None else environment
    event_name = values.get(STOP_EVENT_ENV, "").strip()
    return event_name or None


def wait_for_named_event(event_name: str, timeout_ms: int | None = None) -> bool:
    if not PYWIN32_AVAILABLE:
        return False
    timeout = win32event.INFINITE if timeout_ms is None else timeout_ms
    handle = win32event.OpenEvent(win32con.SYNCHRONIZE, False, event_name)
    try:
        return win32event.WaitForSingleObject(handle, timeout) == win32event.WAIT_OBJECT_0
    finally:
        win32api.CloseHandle(handle)


def wait_for_service_stop(timeout_ms: int | None = None) -> bool:
    event_name = configured_stop_event()
    if event_name is None:
        return False
    return wait_for_named_event(event_name, timeout_ms)


def start_service_stop_watcher(
    callback: Callable[[], None],
    *,
    event_name: str | None = None,
    wait_for_signal: Callable[[str, int | None], bool] = wait_for_named_event,
) -> threading.Thread | None:
    configured = event_name or configured_stop_event()
    if configured is None:
        return None

    def watch() -> None:
        try:
            if wait_for_signal(configured, None):
                callback()
        except Exception:
            return

    watcher = threading.Thread(target=watch, name="loki-service-stop", daemon=True)
    watcher.start()
    return watcher
