from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dashboard_smoke_test import GUILD_ID, _prepare_environment, _seed_database  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_dashboard(base_url: str, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard exited early with code {process.returncode}.")
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError(f"Dashboard did not become healthy at {base_url}.")


def _wait_for_url(url: str, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError(f"Server did not become healthy at {url}.")


def _start_desktop_server(port: int, env: dict[str, str]) -> subprocess.Popen:
    code = (
        "import os, desktop_app; "
        "cfg=desktop_app.load_config(); "
        "mgr=desktop_app.ServiceManager(cfg); "
        "app=desktop_app.make_app(mgr,cfg); "
        "app.run(host='127.0.0.1', port=int(os.environ['DESKTOP_TEST_PORT']), threaded=True, use_reloader=False)"
    )
    desktop_env = {**env, "DESKTOP_TEST_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=desktop_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _assert_nonempty_body(page, path: str) -> str:
    body_text = page.locator("body").inner_text(timeout=5000).strip()
    if body_text == "":
        raise AssertionError(f"Page rendered empty: {path}")
    return body_text


def _run_browser(base_url: str, desktop_url: str, screenshot_dir: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Python Playwright is not installed. Run `.venv/bin/python -m pip install -r requirements-dev.txt`."
        ) from exc

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            lines = str(exc).splitlines()
            detail = next((line.strip() for line in lines if "error while loading shared libraries" in line), lines[0])
            raise RuntimeError(
                f"Chromium could not launch ({detail}). Install native browser libraries with "
                "`.venv/bin/python -m playwright install-deps chromium`, then rerun this smoke."
            ) from None
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        page.goto(base_url, wait_until="domcontentloaded")
        page.get_by_role("link", name="Connect local LOKI THE SUN GOD").click()
        page.wait_for_url("**/guilds")
        page.get_by_role("link", name="Open dashboard").first.click()
        page.wait_for_url(f"**/guild/{GUILD_ID}")

        for tab in ("General", "AutoMod", "Welcome", "Levels", "Logging"):
            page.get_by_role("button", name=tab).click()
        page.screenshot(path=screenshot_dir / "dashboard-desktop.png", full_page=True)

        sidebar_links = [
            ("Commands", f"/guild/{GUILD_ID}/commands"),
            ("Mixer", f"/guild/{GUILD_ID}/mixer"),
            ("NPC", f"/guild/{GUILD_ID}/npc"),
            ("Embed builder", f"/guild/{GUILD_ID}/embed"),
            ("Forms", f"/guild/{GUILD_ID}/forms"),
            ("Tickets", f"/guild/{GUILD_ID}/tickets"),
            ("Events", f"/guild/{GUILD_ID}/events"),
            ("Activities", f"/guild/{GUILD_ID}/activities-control"),
            ("Streams", f"/guild/{GUILD_ID}/streams"),
            ("Developer", f"/guild/{GUILD_ID}/developer"),
            ("Audit log", f"/guild/{GUILD_ID}/audit"),
            ("AI and router", "/ops/ai"),
        ]
        for label, path in sidebar_links:
            page.goto(f"{base_url}/guild/{GUILD_ID}", wait_until="domcontentloaded")
            page.locator("aside").get_by_role("link", name=label).click()
            page.wait_for_url(f"**{path}")
            _assert_nonempty_body(page, path)

        pages = [
            f"/guild/{GUILD_ID}/events",
            f"/guild/{GUILD_ID}/forms",
            f"/guild/{GUILD_ID}/forms/appeal/edit",
            f"/guild/{GUILD_ID}/forms/appeal/responses",
            f"/guild/{GUILD_ID}/streams",
            f"/guild/{GUILD_ID}/tickets",
            f"/guild/{GUILD_ID}/commands",
            f"/guild/{GUILD_ID}/embed",
            f"/guild/{GUILD_ID}/audit",
            "/ops/ai",
            "/ops/research",
        ]
        for path in pages:
            page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            _assert_nonempty_body(page, path)

        page.goto(f"{base_url}/ops/ai", wait_until="domcontentloaded")
        page.get_by_role("link", name="Research lab").click()
        page.wait_for_url("**/ops/research")
        research_text = _assert_nonempty_body(page, "/ops/research")
        for required in ("LOKI research lab", "No production hot-edit path"):
            if required not in research_text:
                raise AssertionError(f"Research lab is missing {required!r}.")

        page.goto(f"{base_url}/ops/ai", wait_until="domcontentloaded")
        page.get_by_label("Ollama host").nth(0).fill("http://127.0.0.1:11434")
        preferred_model = page.get_by_label("Preferred local model")
        if preferred_model.evaluate("element => element.tagName.toLowerCase()") == "input":
            preferred_model.fill("qwen2.5-coder:7b")
        page.get_by_role("button", name="Save local model routing").click()
        page.wait_for_load_state("domcontentloaded")
        if "Local model route saved" not in page.locator("body").inner_text():
            raise AssertionError("Local model settings did not save through the browser.")

        page.set_viewport_size({"width": 390, "height": 900})
        page.goto(f"{base_url}/guild/{GUILD_ID}", wait_until="domcontentloaded")
        page.screenshot(path=screenshot_dir / "dashboard-mobile.png", full_page=True)

        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(desktop_url, wait_until="domcontentloaded")
        page.get_by_role("button", name="Dashboards").click()
        page.get_by_role("button", name="Embed").click()
        page.get_by_text("MEE6 Dashboard").wait_for(timeout=10000)
        desktop_text = page.locator("body").inner_text(timeout=5000)
        for required in ("LOKI Dashboard", "9router", "MEE6 Dashboard", "Discord Developer Portal", "Back up now"):
            if required not in desktop_text:
                raise AssertionError(f"Desktop dashboard is missing {required!r}.")
        for forbidden in ("9router - Claude", "9router · Claude", "loki_cr", "/dashboard/claude-router"):
            if forbidden in desktop_text:
                raise AssertionError(f"Desktop dashboard still renders legacy item {forbidden!r}.")

        page.get_by_role("button", name="Back up now").click()
        page.get_by_text("Backup complete").wait_for(timeout=10000)
        if "Protected" not in page.locator("body").inner_text(timeout=5000):
            raise AssertionError("Manual backup did not update the desktop status card.")

        page.get_by_role("button", name="LOKI THE SUN GOD").click()
        page.get_by_placeholder("Search channel names, topics, or kinds").fill("games")
        page.get_by_role("button", name="Toggle clusters").click()
        page.get_by_role("button", name="Toggle clusters").click()
        desktop_text = page.locator("body").inner_text(timeout=5000)
        if "HTTP Error 404" in desktop_text:
            raise AssertionError("Channel explorer rendered a raw HTTP 404.")

        page.get_by_role("button", name="Dashboards").click()
        for label in ("LOKI Dashboard", "9router", "MEE6 Dashboard", "Discord Developer Portal"):
            card = page.locator("div.card", has_text=label).first
            card.get_by_role("button").first.click()
            page.get_by_title("Back to grid").click()
        page.screenshot(path=screenshot_dir / "desktop-dashboards.png", full_page=True)
        browser.close()

    if console_errors:
        raise AssertionError("Browser console errors:\n" + "\n".join(console_errors[:20]))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="loki-playwright-smoke-") as tmp:
        tmp_path = Path(tmp)
        _prepare_environment(tmp_path)
        _seed_database()
        port = _free_port()
        desktop_port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        desktop_url = f"http://127.0.0.1:{desktop_port}"
        env = os.environ.copy()
        env.update({"DASHBOARD_HOST": "127.0.0.1", "DASHBOARD_PORT": str(port), "PYTHONUNBUFFERED": "1"})
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "dashboard_app.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        desktop_process = _start_desktop_server(desktop_port, env)
        try:
            _wait_for_dashboard(base_url, process)
            _wait_for_url(desktop_url, desktop_process)
            _run_browser(base_url, desktop_url, ROOT / "output" / "playwright")
        finally:
            for child in (process, desktop_process):
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

    print("dashboard Playwright smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
