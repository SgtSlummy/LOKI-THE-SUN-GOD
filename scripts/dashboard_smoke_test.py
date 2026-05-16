from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GUILD_ID = 123456789012345678
CSRF_TOKEN = "dashboard-smoke-csrf"


def _prepare_environment(tmp_path: Path) -> None:
    router_env = tmp_path / "9router" / ".env"
    router_env.parent.mkdir(parents=True, exist_ok=True)
    router_env.write_text(f"DATA_DIR={tmp_path / '9router-data'}\n", encoding="utf-8")
    os.environ.pop("DATABASE_URL", None)
    os.environ.update(
        {
            "LOKI_APP_ROOT": str(ROOT),
            "LOKI_DB_PATH": str(tmp_path / "bot.db"),
            "LOKI_ENV_PATH": str(tmp_path / ".env"),
            "LOKI_CODEX_SETTINGS_PATH": str(tmp_path / "codex-settings.json"),
            "LOKI_ROUTER_REPO_PATH": str(tmp_path / "9router"),
            "LOKI_ROUTER_ENV_PATH": str(router_env),
            "LOKI_MEMPALACE_ROOT": str(tmp_path / "mempalace"),
            "LOKI_MEMPALACE_CONFIG_PATH": str(tmp_path / "mempalace" / "config.json"),
            "LOKI_MEMPALACE_FALLBACK_PATH": str(tmp_path / "mempalace-memory.md"),
            "LOKI_RUNTIME_LOG_PATH": str(tmp_path / "desktop_runtime.log"),
            "LOKI_DESKTOP_CONFIG_PATH": str(tmp_path / "desktop_config.json"),
            "LOKI_DOCS_PATH": str(ROOT / "docs"),
            "LOKI_AI_DOCS_PATH": str(ROOT / "docs" / "ai_library"),
            "DASHBOARD_SECRET_KEY": "dashboard-smoke-secret",
            "DISCORD_CLIENT_ID": "dashboard-smoke-client",
            "DISCORD_CLIENT_SECRET": "dashboard-smoke-secret",
            "REDIRECT_URI": "http://127.0.0.1:5000/callback",
            "DISCORD_TOKEN": "",
        }
    )
    (tmp_path / ".env").write_text("DISCORD_TOKEN=\nOLLAMA_HOST=http://127.0.0.1:11434\n", encoding="utf-8")
    (tmp_path / "desktop_runtime.log").write_text("dashboard smoke boot\n", encoding="utf-8")


def _seed_database() -> None:
    from utils import db as shared_db

    shared_db.init_sync()
    now = int(time.time())
    shared_db.save_guild_config_sync(
        GUILD_ID,
        {
            "prefix": "!",
            "log_channel": 111111111111111111,
            "welcome_channel": 222222222222222222,
            "welcome_msg": "Welcome to LOKI THE SUN GOD HQ!",
            "goodbye_msg": "Later, {user}",
            "starboard_channel": 333333333333333333,
            "star_threshold": 4,
            "level_enabled": 1,
        },
    )
    shared_db.save_automod_rules_sync(
        GUILD_ID,
        {
            "anti_invite": 1,
            "anti_spam": 1,
            "anti_caps": 0,
            "anti_mention": 1,
            "bad_words": "spoiler,badword",
            "max_mentions": 4,
            "spam_threshold": 6,
            "caps_percent": 80,
        },
    )
    shared_db.sync_exec(
        "INSERT OR IGNORE INTO forms(guild_id, name, title, fields, target_channel_id, button_label) "
        "VALUES(?,?,?,?,?,?)",
        (
            GUILD_ID,
            "appeal",
            "Ban Appeal",
            json.dumps([{"label": "Why should staff approve?", "style": "long", "required": True}]),
            666666666666666666,
            "Appeal",
        ),
    )
    shared_db.sync_exec(
        "INSERT INTO form_responses(guild_id, form_name, user_id, responses, submitted_at, status) "
        "VALUES(?,?,?,?,?,?)",
        (GUILD_ID, "appeal", 444444444444444444, json.dumps({"Reason": "Smoke"}), now, "pending"),
    )
    shared_db.sync_exec(
        "INSERT OR IGNORE INTO stream_subs(guild_id, platform, channel_name, target_channel_id, mention_role_id) "
        "VALUES(?,?,?,?,?)",
        (GUILD_ID, "twitch", "lokilive", 888888888888888888, None),
    )
    shared_db.sync_exec(
        "INSERT INTO tickets(guild_id, channel_id, opener_id, status, opened_at, reason) VALUES(?,?,?,?,?,?)",
        (GUILD_ID, 999999999999999999, 444444444444444444, "open", now, "Smoke ticket"),
    )
    shared_db.sync_exec(
        "INSERT INTO warnings(guild_id, user_id, mod_id, reason, created_at) VALUES(?,?,?,?,?)",
        (GUILD_ID, 444444444444444444, 555555555555555555, "Smoke warning", now),
    )


def _login(client) -> None:
    with client.session_transaction() as session:
        session.clear()
        session["user"] = {"id": "dashboard-smoke", "username": "Dashboard Smoke"}
        session["_csrf_token"] = CSRF_TOKEN
        session["guilds"] = [
            {
                "id": str(GUILD_ID),
                "name": "LOKI THE SUN GOD Smoke Guild",
                "icon": None,
                "permissions": str(0x8),
            }
        ]


def _get_ok(client, path: str) -> None:
    response = client.get(path)
    if response.status_code != 200:
        raise AssertionError(f"GET {path} returned {response.status_code}")


def _post_ok(client, path: str, data: dict[str, object]) -> None:
    payload = {"csrf_token": CSRF_TOKEN, **data}
    response = client.post(path, data=payload, follow_redirects=True)
    if response.status_code != 200:
        raise AssertionError(f"POST {path} returned {response.status_code}")


def _assert_server_side_dashboard_session(client, session_id: str) -> None:
    from utils import db as shared_db

    row = shared_db.sync_one(
        "SELECT user_json, guilds_json FROM dashboard_sessions WHERE session_id = ?",
        (session_id,),
    )
    if not row:
        raise AssertionError("Dashboard local connect did not persist a server-side session row.")

    guilds = json.loads(row["guilds_json"])
    if not any(str(guild.get("id")) == str(GUILD_ID) for guild in guilds):
        raise AssertionError("Server-side dashboard session is missing the smoke guild grant.")

    response = client.get("/guilds")
    if response.status_code != 200:
        raise AssertionError(f"Server-side dashboard session could not load /guilds: {response.status_code}")
    expected_guild_name = f"LOKI THE SUN GOD Guild {GUILD_ID}".encode()
    if expected_guild_name not in response.data:
        raise AssertionError("Server-side dashboard session did not render the smoke guild.")

    with client.session_transaction() as session:
        if "guilds" in session:
            raise AssertionError("Server-side dashboard session round trip repopulated client-side guild grants.")


def _first_id(query: str, params: tuple = ()) -> int:
    from utils import db as shared_db

    row = shared_db.sync_one(query, params)
    if not row:
        raise AssertionError(f"No row found for query: {query}")
    return int(row[0])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="loki-dashboard-smoke-") as tmp:
        tmp_path = Path(tmp)
        _prepare_environment(tmp_path)
        _seed_database()

        platform.system = lambda: "Windows"

        import dashboard_app
        from utils import operator_surface

        operator_surface.mempalace_status_snapshot = lambda: {
            "ready": False,
            "summary": "MemPalace smoke snapshot disabled for deterministic dashboard tests.",
            "wings": [],
            "topic_wings": [],
        }

        client = dashboard_app.app.test_client()
        _get_ok(client, "/")
        _get_ok(client, "/healthz")
        _get_ok(client, "/brand/icon.svg")
        connect = client.get("/dev/connect-loki", follow_redirects=False)
        if connect.status_code not in (302, 303):
            raise AssertionError(f"Local connect returned {connect.status_code}")
        with client.session_transaction() as session:
            if "token" in session or "guilds" in session:
                raise AssertionError("Dashboard local connect stored token or guild grants in the client session.")
            dashboard_session_id = session.get("dashboard_session_id")
            if not dashboard_session_id:
                raise AssertionError("Dashboard local connect did not create a server-side session id.")
        _assert_server_side_dashboard_session(client, str(dashboard_session_id))
        _login(client)

        for path in (
            "/guilds",
            "/ops/ai",
            "/ops/research",
            f"/guild/{GUILD_ID}",
            f"/guild/{GUILD_ID}/events",
            f"/guild/{GUILD_ID}/forms",
            f"/guild/{GUILD_ID}/forms/appeal/edit",
            f"/guild/{GUILD_ID}/forms/appeal/responses",
            f"/guild/{GUILD_ID}/streams",
            f"/guild/{GUILD_ID}/tickets",
            f"/guild/{GUILD_ID}/commands",
            f"/guild/{GUILD_ID}/mixer",
            f"/guild/{GUILD_ID}/npc",
            f"/guild/{GUILD_ID}/activities-control",
            f"/guild/{GUILD_ID}/developer",
            f"/guild/{GUILD_ID}/embed",
            f"/guild/{GUILD_ID}/audit",
            f"/api/guild/{GUILD_ID}/audit.json",
            f"/api/guild/{GUILD_ID}/audit.json?format=csv",
            f"/api/guild/{GUILD_ID}/forms/appeal/submissions.json",
            f"/api/guild/{GUILD_ID}/forms/appeal/submissions.json?format=csv",
            f"/api/guild/{GUILD_ID}/tickets/export.json",
            f"/api/guild/{GUILD_ID}/tickets/export.json?format=csv",
        ):
            _get_ok(client, path)

        ai_page = client.get("/ops/ai")
        if ai_page.status_code != 200:
            raise AssertionError(f"AI router page failed: {ai_page.status_code}")
        if operator_surface.REMOTE_9ROUTER_RESEARCH_URL.encode() not in ai_page.data:
            raise AssertionError("AI router page did not render the hosted Dolphin research dashboard link.")
        if b'rel="noopener noreferrer"' not in ai_page.data:
            raise AssertionError("External 9router research link did not include rel=noopener noreferrer.")

        _post_ok(
            client,
            "/ops/ai/app-env/save",
            {
                "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:11434/v1",
                "OLLAMA_HOST": "http://127.0.0.1:11434",
                "LOKI_LLM_MODEL": "gpt-5.5",
            },
        )
        _post_ok(
            client,
            "/ops/ai/codex/save",
            {
                "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:11434/v1",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "qwen2.5-coder:7b",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "qwen2.5-coder:7b",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "qwen2.5-coder:7b",
            },
        )
        local_route = client.post(
            "/ops/ai/local-model/save",
            data={
                "csrf_token": CSRF_TOKEN,
                "OLLAMA_HOST": "http://127.0.0.1:11434",
                "PREFERRED_LOCAL_MODEL": "qwen2.5-coder:7b",
                "CONFIGURE_9ROUTER": "on",
            },
            follow_redirects=True,
        )
        if local_route.status_code != 200 or b"Local model route saved" not in local_route.data:
            raise AssertionError("Local model route save did not render its success status.")
        _post_ok(
            client,
            "/ops/ai/router/save",
            {
                "PORT": "20128",
                "BASE_URL": "http://localhost:20128",
                "CLOUD_URL": "https://9router.com",
                "NEXT_PUBLIC_BASE_URL": "http://localhost:20128",
                "NEXT_PUBLIC_CLOUD_URL": "https://9router.com",
                "DATA_DIR": str(tmp_path / "9router-data"),
                "OBSERVABILITY_ENABLED": "on",
            },
        )
        _post_ok(
            client,
            "/ops/ai/router/save",
            {
                "PORT": "20128",
                "BASE_URL": "http://localhost:20128",
                "CLOUD_URL": "",
                "NEXT_PUBLIC_BASE_URL": "http://localhost:20128",
                "NEXT_PUBLIC_CLOUD_URL": "",
                "DATA_DIR": str(tmp_path / "9router-data"),
                "OBSERVABILITY_ENABLED": "on",
            },
        )
        router_env = operator_surface.read_env_file_at(operator_surface.router_env_path())
        if router_env.get("CLOUD_URL") != "https://9router.com":
            raise AssertionError("Blank CLOUD_URL should fall back to the runtime-safe 9router origin.")
        if router_env.get("NEXT_PUBLIC_CLOUD_URL") != "https://9router.com":
            raise AssertionError("Blank NEXT_PUBLIC_CLOUD_URL should fall back to the runtime-safe 9router origin.")
        _post_ok(
            client,
            "/ops/ai/memory/save",
            {
                "palace_path": str(tmp_path / "mempalace"),
                "collection_name": "dashboard-smoke",
                "topic_wings": "operations\nloki",
            },
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/save",
            {
                "prefix": "?",
                "starboard_channel": "333333333333333333",
                "star_threshold": "5",
                "mute_role": "777777777777777777",
                "anti_invite": "on",
                "anti_spam": "on",
                "max_mentions": "5",
                "spam_threshold": "7",
                "caps_percent": "75",
                "bad_words": "spoiler",
                "welcome_channel": "222222222222222222",
                "welcome_msg": "Welcome, {user}",
                "goodbye_msg": "Goodbye, {user}",
                "log_channel": "111111111111111111",
                "level_enabled": "on",
            },
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/events/create",
            {
                "title": "Smoke Event",
                "description": "Dashboard smoke event",
                "location": "Dashboard",
                "starts_at": "2031-01-01T12:00",
                "color": "#57F287",
            },
        )
        event_id = _first_id("SELECT id FROM events WHERE guild_id=? ORDER BY id DESC LIMIT 1", (GUILD_ID,))
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/events/{event_id}/save",
            {
                "title": "Smoke Event Updated",
                "description": "Dashboard smoke event updated",
                "location": "Dashboard",
                "starts_at": "2031-01-02T12:00",
                "color": "#F6C244",
                "reminder_offset": "10m",
            },
        )
        _post_ok(client, f"/guild/{GUILD_ID}/events/{event_id}/delete", {})

        _post_ok(
            client,
            f"/guild/{GUILD_ID}/mixer/save",
            {
                "volume": "0",
                "eq_preset": "Podcast",
                "request_channel_id": "222222222222222222",
                "dj_role_id": "777777777777777777",
                "mixer_locked": "on",
            },
        )
        mixer_html = client.get(f"/guild/{GUILD_ID}/mixer").data.decode("utf-8", errors="replace")
        if 'name="volume" type="number" min="0" max="150" value="0"' not in mixer_html:
            raise AssertionError("Mixer volume 0 did not round-trip through the dashboard.")
        if "Bot bridge unavailable" not in mixer_html:
            raise AssertionError("Mixer deck controls did not expose their disabled state.")
        invalid_mixer = client.post(
            f"/guild/{GUILD_ID}/mixer/save",
            data={"csrf_token": CSRF_TOKEN, "volume": "loud", "eq_preset": "Nightcore"},
            follow_redirects=True,
        )
        if invalid_mixer.status_code != 200 or b"valid LOKI equalizer preset" not in invalid_mixer.data:
            raise AssertionError("Invalid mixer save was not rejected cleanly.")

        _post_ok(
            client,
            f"/guild/{GUILD_ID}/npc/save",
            {
                "enabled": "on",
                "persona_json": json.dumps(
                    {
                        "summary": "A threshold guardian with solar wit.",
                        "backstory": "Uses public-domain Loki motifs as roleplay.",
                        "voice_rules": ["Respect public context.", "Respect admin gates."],
                    }
                ),
                "channel_allowlist": "222222222222222222",
                "web_crawl_enabled": "",
                "auto_post_channel_id": "",
            },
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/activities-control/create",
            {
                "title": "Smoke Quest",
                "activity_type": "portal",
                "status": "planned",
            },
        )
        activities_html = client.get(f"/guild/{GUILD_ID}/activities-control").data.decode("utf-8", errors="replace")
        if "Activity stream rooms" not in activities_html:
            raise AssertionError("Activity bridge dashboard panel did not render.")

        for action, payload in (
            ("disable", {"command": "welcome preview"}),
            ("enable", {"command": "welcome preview"}),
            ("ignore", {"channel_id": "123"}),
            ("unignore", {"channel_id": "123"}),
            ("add_mod_role", {"role_id": "456"}),
            ("remove_mod_role", {"role_id": "456"}),
        ):
            _post_ok(client, f"/guild/{GUILD_ID}/commands/save", {"action": action, **payload})

        _post_ok(
            client,
            f"/guild/{GUILD_ID}/streams/add",
            {
                "platform": "tiktok",
                "channel_name": "lokismoke",
                "target_channel_id": "888888888888888888",
                "mention_role_id": "",
            },
        )
        stream_id = _first_id(
            "SELECT id FROM stream_subs WHERE guild_id=? AND channel_name=?",
            (GUILD_ID, "lokismoke"),
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/streams/{stream_id}/save",
            {
                "platform": "kick",
                "channel_name": "lokismoke",
                "target_channel_id": "888888888888888888",
                "mention_role_id": "456",
            },
        )
        _post_ok(client, f"/guild/{GUILD_ID}/streams/delete", {"id": str(stream_id)})

        _post_ok(client, f"/guild/{GUILD_ID}/forms/create", {"name": "smokeform", "title": "Smoke Form"})
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/forms/smokeform/save",
            {
                "title": "Smoke Form",
                "button_label": "Apply",
                "target_channel_id": "666666666666666666",
                "fields_json": json.dumps([{"label": "Reason", "style": "long", "required": True}]),
            },
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/tickets/save",
            {
                "tickets_category_id": "111",
                "tickets_log_channel": "222",
                "tickets_staff_role": "333",
            },
        )
        response_id = _first_id(
            "SELECT id FROM form_responses WHERE guild_id=? AND form_name=? ORDER BY id LIMIT 1",
            (GUILD_ID, "appeal"),
        )
        _post_ok(
            client,
            f"/guild/{GUILD_ID}/forms/appeal/responses/{response_id}/decide",
            {"decision": "approved", "note": "Smoke approved"},
        )

        embed = client.post(
            f"/guild/{GUILD_ID}/embed/send",
            json={"channel_id": "123", "content": "Smoke", "embed": {"title": "Smoke"}},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )
        body = embed.get_json() or {}
        if embed.status_code != 400 or "DISCORD_TOKEN" not in body.get("error", ""):
            raise AssertionError(f"Embed send token validation failed: {embed.status_code} {body}")

        import desktop_app

        desktop_cfg = desktop_app.load_config()
        desktop_client = desktop_app.make_app(desktop_app.ServiceManager(desktop_cfg), desktop_cfg).test_client()
        dashboards = desktop_client.get("/api/dashboards")
        dashboard_items = (dashboards.get_json() or {}).get("dashboards", [])
        dashboard_ids = {item.get("id") for item in dashboard_items}
        if "mee6_dashboard" not in dashboard_ids:
            raise AssertionError("Desktop dashboards did not include MEE6.")
        router_item = next((item for item in dashboard_items if item.get("id") == "router9"), None)
        if not router_item or router_item.get("url") != operator_surface.REMOTE_9ROUTER_RESEARCH_URL:
            raise AssertionError(f"Desktop 9router dashboard did not point at Dolphin research: {router_item}")
        for item in dashboard_items:
            label = str(item.get("label") or "").lower().replace("·", "-")
            url = str(item.get("url") or "").lower()
            if item.get("id") == "loki_cr" or ("9router" in label and "claude" in label) or "/claude-router" in url:
                raise AssertionError(f"Legacy Claude dashboard survived: {item}")

        original_fetch = operator_surface.fetch_discord_channels
        try:
            operator_surface.fetch_discord_channels = lambda _guild_id: ([], "HTTP Error 404: Not Found")
            channel_response = desktop_client.get(f"/api/loki/{GUILD_ID}/channels")
        finally:
            operator_surface.fetch_discord_channels = original_fetch
        channel_payload = channel_response.get_json() or {}
        if "HTTP Error 404" in str(channel_payload.get("error")):
            raise AssertionError("Channel explorer exposed a raw HTTP 404.")
        if not channel_payload.get("clusters"):
            raise AssertionError("Channel explorer did not preserve fallback clusters after Discord 404.")

        backup_response = desktop_client.post("/api/backup/manual")
        backup_payload = backup_response.get_json() or {}
        if backup_response.status_code != 200 or not backup_payload.get("ok"):
            raise AssertionError(f"Manual backup failed: {backup_response.status_code} {backup_payload}")
        backup_file = Path((backup_payload.get("backup") or {}).get("path", ""))
        if not backup_file.exists():
            raise AssertionError(f"Manual backup file was not created: {backup_file}")
        if (backup_payload.get("status") or {}).get("state") != "ready":
            raise AssertionError("Manual backup did not update backup status to ready.")

    print("dashboard smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
