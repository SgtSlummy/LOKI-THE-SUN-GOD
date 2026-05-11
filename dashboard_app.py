"""
Loki Web Dashboard
========================
Separate process from bot. Shares the same SQLite DB.

Start: python dashboard/app.py
Requires: DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, REDIRECT_URI, DASHBOARD_SECRET_KEY in .env

OAuth2 scopes: identify guilds
"""

import json
import os
import secrets
import time
from collections import Counter
from datetime import datetime
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import Flask, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for

from utils import runtime_paths

runtime_paths.load_app_dotenv()

from utils import db as shared_db
from utils import operator_surface
from utils.command_catalog import parse_command_catalog
from utils.dashboard_theme import DASHBOARD_BRAND, css_variables

shared_db.init_sync()

app = Flask(__name__, template_folder=str(runtime_paths.bundle_path("templates")))
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET_KEY", "")
if not DASHBOARD_SECRET:
    public_url = os.getenv("DASHBOARD_PUBLIC_URL", "")
    if public_url.startswith("https://") or os.getenv("RAILWAY_ENVIRONMENT"):
        raise RuntimeError("DASHBOARD_SECRET_KEY is required for hosted LOKI dashboard deployments.")
    DASHBOARD_SECRET = "local-dev-secret-change-me"
    print("WARN: DASHBOARD_SECRET_KEY missing; using local development secret. Set this before deployment.")
app.secret_key = DASHBOARD_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

DB_LABEL = shared_db.current_database_label()
COMMAND_ROOT = runtime_paths.bundle_root()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:5000/callback")
API_BASE = "https://discord.com/api/v10"
OAUTH_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = f"{API_BASE}/oauth2/token"
SCOPES = "identify guilds"
HTTP_TIMEOUT = (5, 20)
STRUCTURE_TTL_SECONDS = 60
_GUILD_STRUCTURE_CACHE: dict[int, tuple[float, dict[str, object]]] = {}

if REDIRECT_URI.startswith("https://"):
    app.config["SESSION_COOKIE_SECURE"] = True


def oauth_ready() -> bool:
    return all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI])


def missing_oauth_fields() -> list[str]:
    missing = []
    if not CLIENT_ID:
        missing.append("DISCORD_CLIENT_ID")
    if not CLIENT_SECRET:
        missing.append("DISCORD_CLIENT_SECRET")
    if not REDIRECT_URI:
        missing.append("REDIRECT_URI")
    if os.getenv("DASHBOARD_SECRET_KEY", "") == "":
        missing.append("DASHBOARD_SECRET_KEY")
    return missing


def bot_token() -> str:
    env_token = os.getenv("DISCORD_TOKEN", "").strip()
    if env_token:
        return env_token

    for candidate in runtime_paths.env_candidates():
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DISCORD_TOKEN":
                return value.strip().strip('"').strip("'")
    return ""


def _ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = _ensure_csrf_token
app.jinja_env.globals["dashboard_brand"] = DASHBOARD_BRAND
app.jinja_env.globals["dashboard_css_variables"] = css_variables


# ─── DB helpers ──────────────────────────────────────────────────────────────


def get_db():
    return None


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def db_one(sql, params=()):
    return shared_db.sync_one(sql, params)


def db_all(sql, params=()):
    return shared_db.sync_all(sql, params)


def db_exec(sql, params=()):
    return shared_db.sync_exec(sql, params)


# ─── Auth helpers ────────────────────────────────────────────────────────────


@app.before_request
def csrf_protect():
    if request.method != "POST":
        return None
    expected = session.get("_csrf_token")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if expected and supplied and secrets.compare_digest(expected, supplied):
        return None
    _ensure_csrf_token()
    if request.is_json:
        return jsonify({"ok": False, "error": "CSRF token missing or invalid"}), 400
    flash("Your session expired. Reload the page and try again.", "danger")
    return redirect(request.referrer or url_for("index"))


def discord_request(token, endpoint):
    r = requests.get(
        f"{API_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def is_local_request() -> bool:
    return request.remote_addr in ("127.0.0.1", "::1", None)


def local_loki_guilds():
    rows = db_all("SELECT guild_id, prefix FROM guild_config ORDER BY guild_id")
    if not rows:
        return []
    guilds = []
    for row in rows:
        guilds.append(
            {
                "id": str(row["guild_id"]),
                "name": f"LOKI THE SUN GOD Guild {row['guild_id']}",
                "icon": None,
                "permissions": str(0x8),
                "prefix": row["prefix"],
            }
        )
    return guilds


def _channel_label(channel_id: int | None, channel_map: dict[str, str]) -> str:
    if not channel_id:
        return "-"
    return channel_map.get(str(channel_id), f"#{channel_id}")


def _role_label(role_id: int | None, role_map: dict[str, str]) -> str:
    if not role_id:
        return "-"
    return role_map.get(str(role_id), f"@{role_id}")


def _guild_structure(guild_id: int) -> dict[str, object]:
    cached = _GUILD_STRUCTURE_CACHE.get(guild_id)
    now = time.time()
    if cached and now - cached[0] < STRUCTURE_TTL_SECONDS:
        return cached[1]

    raw_channels: list[dict[str, object]] = []
    channels: list[dict[str, object]] = []
    categories: list[dict[str, object]] = []
    roles: list[dict[str, object]] = []
    if bot_token():
        try:
            channel_response = _bot_get(f"/guilds/{guild_id}/channels")
            if channel_response.ok:
                raw_channels = [
                    {"id": int(channel["id"]), "name": channel["name"], "type": channel["type"]}
                    for channel in channel_response.json()
                ]
                channels = [channel for channel in raw_channels if channel.get("type") in (0, 5)]
                categories = [channel for channel in raw_channels if channel.get("type") == 4]
                channels.sort(key=lambda channel: str(channel["name"]).lower())
                categories.sort(key=lambda channel: str(channel["name"]).lower())
        except requests.RequestException:
            raw_channels = []
            channels = []
            categories = []

        try:
            role_response = _bot_get(f"/guilds/{guild_id}/roles")
            if role_response.ok:
                roles = [
                    {"id": int(role["id"]), "name": role["name"]}
                    for role in role_response.json()
                    if role.get("name") != "@everyone"
                ]
                roles.sort(key=lambda role: str(role["name"]).lower())
        except requests.RequestException:
            roles = []

    structure = {
        "channel_choices": channels,
        "category_choices": categories,
        "role_choices": roles,
        "channel_map": {str(channel["id"]): f"#{channel['name']}" for channel in channels},
        "category_map": {str(channel["id"]): channel["name"] for channel in categories},
        "role_map": {str(role["id"]): f"@{role['name']}" for role in roles},
    }
    _GUILD_STRUCTURE_CACHE[guild_id] = (now, structure)
    return structure


def _guild_template_context(guild_id: int) -> dict[str, object]:
    return _guild_structure(guild_id)


def _normalize_setting_text(value: str | None) -> str:
    return (value or "").strip()


def _secret_update(form_key: str) -> str | None:
    raw = request.form.get(form_key)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _multiline_tokens(value: str | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in (value or "").replace(",", "\n").splitlines():
        token = raw.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _looks_like_root_path(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    return normalized in {"/", ".", "~"} or (
        len(normalized) in {2, 3} and normalized[1:2] == ":" and normalized.endswith("/")
    )


def _event_datetime_input(unix_ts: int | None) -> str:
    if not unix_ts:
        return ""
    return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%dT%H:%M")


def _parse_event_datetime(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


def ops_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        owner_id = os.getenv("OWNER_ID", "").strip()
        user_id = str(session.get("user", {}).get("id", ""))
        if is_local_request() or (owner_id and user_id == owner_id):
            return f(*args, **kwargs)
        flash("AI/router operations require the bot owner or a local operator session.", "danger")
        return redirect(url_for("guilds"))

    return decorated


def guild_admin_required(f):
    @wraps(f)
    def decorated(guild_id, *args, **kwargs):
        guilds = session.get("guilds", [])
        MANAGE_GUILD = 0x20
        guild = next((g for g in guilds if str(g["id"]) == str(guild_id)), None)
        if not guild:
            flash("Server not found or access denied.", "danger")
            return redirect(url_for("guilds"))
        perms = int(guild.get("permissions", 0))
        if not (perms & MANAGE_GUILD) and not (perms & 0x8):
            flash("You need Manage Server permission.", "danger")
            return redirect(url_for("guilds"))
        return f(guild_id, *args, **kwargs)

    return decorated


# ─── Routes ──────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("guilds"))
    return render_template(
        "index.html",
        local_bridge_available=is_local_request(),
        oauth_ready=oauth_ready(),
        missing_oauth=missing_oauth_fields(),
    )


@app.route("/healthz")
def healthz():
    try:
        db_one("SELECT 1")
        db_ok = True
    except Exception as exc:
        return jsonify(
            {
                "ok": False,
                "database_ok": False,
                "oauth_ready": oauth_ready(),
                "missing_oauth": missing_oauth_fields(),
                "database_backend": shared_db.database_backend(),
                "database": DB_LABEL,
                "error": str(exc),
            }
        ), 500
    return jsonify(
        {
            "ok": True,
            "database_ok": db_ok,
            "oauth_ready": oauth_ready(),
            "missing_oauth": missing_oauth_fields(),
            "local_bridge_available": is_local_request(),
            "database_backend": shared_db.database_backend(),
            "database": DB_LABEL,
            "db_path": DB_LABEL,
        }
    )


@app.route("/brand/icon.svg")
def brand_icon():
    icon_path = runtime_paths.bundle_path("assets", "loki-dashboard-icon.svg")
    if not icon_path.exists():
        return "", 404
    return send_file(icon_path, mimetype="image/svg+xml", max_age=3600)


@app.route("/login")
def login():
    if not oauth_ready():
        flash(
            "Discord OAuth is not configured yet. Set DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, "
            "REDIRECT_URI, and DASHBOARD_SECRET_KEY.",
            "danger",
        )
        return redirect(url_for("index"))
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return redirect(f"{OAUTH_URL}?" + urlencode(params))


@app.route("/callback")
def callback():
    if not oauth_ready():
        flash("Discord OAuth is not configured for this dashboard.", "danger")
        return redirect(url_for("index"))
    error = request.args.get("error")
    if error:
        flash(f"OAuth error: {error}", "danger")
        return redirect(url_for("index"))
    expected_state = session.get("oauth_state")
    supplied_state = request.args.get("state")
    if not expected_state or not supplied_state or supplied_state != expected_state:
        flash("State mismatch.", "danger")
        return redirect(url_for("index"))
    code = request.args.get("code")
    if not code:
        flash("OAuth code missing.", "danger")
        return redirect(url_for("index"))
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    try:
        r = requests.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        tokens = r.json()
        access_token = tokens["access_token"]
        user = discord_request(access_token, "/users/@me")
        guilds = discord_request(access_token, "/users/@me/guilds")
    except (requests.RequestException, KeyError, ValueError) as exc:
        app.logger.warning("OAuth callback failed: %s", exc)
        flash("Discord OAuth exchange failed.", "danger")
        return redirect(url_for("index"))
    session["user"] = user
    session["token"] = access_token
    session["guilds"] = guilds
    return redirect(url_for("guilds"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dev/connect-loki")
def connect_loki():
    if not is_local_request():
        flash("Local LOKI THE SUN GOD bridge is only available from this machine.", "danger")
        return redirect(url_for("index"))
    guilds = local_loki_guilds()
    if not guilds:
        flash("No LOKI THE SUN GOD guild data found in the local database.", "danger")
        return redirect(url_for("index"))
    session["user"] = {"id": "local-loki-admin", "username": "Local LOKI THE SUN GOD Admin"}
    session["token"] = "local-loki"
    session["guilds"] = guilds
    flash("Connected dashboard to the local LOKI THE SUN GOD database.", "success")
    return redirect(url_for("guilds"))


@app.route("/guilds")
@login_required
def guilds():
    MANAGE_GUILD = 0x20
    admin_guilds = [
        g
        for g in session.get("guilds", [])
        if (int(g.get("permissions", 0)) & MANAGE_GUILD) or (int(g.get("permissions", 0)) & 0x8)
    ]
    # Check which guilds have bot installed
    bot_guild_ids = {str(row[0]) for row in db_all("SELECT guild_id FROM guild_config")}
    for guild in admin_guilds:
        guild["bot_installed"] = str(guild["id"]) in bot_guild_ids
    return render_template(
        "guilds.html",
        guilds=admin_guilds,
        user=session["user"],
        client_id=CLIENT_ID,
        local_bridge_available=is_local_request(),
    )


@app.route("/ops/ai")
@login_required
@ops_admin_required
def ai_ops():
    snapshot = operator_surface.ai_router_snapshot()
    return render_template("ai_router.html", ai=snapshot, user=session["user"])


@app.route("/ops/ai/app-env/save", methods=["POST"])
@login_required
@ops_admin_required
def ai_ops_save_app_env():
    updates = {
        "OPENAI_BASE_URL": _normalize_setting_text(request.form.get("OPENAI_BASE_URL")),
        "OPENROUTER_BASE_URL": _normalize_setting_text(request.form.get("OPENROUTER_BASE_URL"))
        or "https://openrouter.ai/api/v1",
        "ANTHROPIC_BASE_URL": _normalize_setting_text(request.form.get("ANTHROPIC_BASE_URL")),
        "OLLAMA_HOST": _normalize_setting_text(request.form.get("OLLAMA_HOST")) or "http://127.0.0.1:11434",
        "LOKI_LLM_MODEL": _normalize_setting_text(request.form.get("LOKI_LLM_MODEL")) or "gpt-5.5",
    }
    for field in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        secret_value = _secret_update(field)
        if secret_value is not None:
            updates[field] = secret_value
    operator_surface.save_app_ai_env(updates)
    flash("App AI environment settings saved.", "success")
    return redirect(url_for("ai_ops"))


@app.route("/ops/ai/codex/save", methods=["POST"])
@login_required
@ops_admin_required
def ai_ops_save_codex():
    updates = {
        "ANTHROPIC_BASE_URL": _normalize_setting_text(request.form.get("ANTHROPIC_BASE_URL")),
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": _normalize_setting_text(request.form.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")),
        "ANTHROPIC_DEFAULT_SONNET_MODEL": _normalize_setting_text(request.form.get("ANTHROPIC_DEFAULT_SONNET_MODEL")),
        "ANTHROPIC_DEFAULT_OPUS_MODEL": _normalize_setting_text(request.form.get("ANTHROPIC_DEFAULT_OPUS_MODEL")),
        "OPENAI_BASE_URL": _normalize_setting_text(request.form.get("OPENAI_BASE_URL")),
    }
    for field in ("ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"):
        secret_value = _secret_update(field)
        if secret_value is not None:
            updates[field] = secret_value
    operator_surface.write_codex_settings_env(updates)
    flash("Codex routing settings saved.", "success")
    return redirect(url_for("ai_ops"))


@app.route("/ops/ai/local-model/save", methods=["POST"])
@login_required
@ops_admin_required
def ai_ops_save_local_model():
    ollama_host = operator_surface.normalize_ollama_host(request.form.get("OLLAMA_HOST"))
    selected_model = _normalize_setting_text(request.form.get("PREFERRED_LOCAL_MODEL"))
    status = operator_surface.ollama_router_status(ollama_host=ollama_host)
    if not selected_model:
        selected_model = status.get("preferred_local_model") or ""

    local_base_url = operator_surface.ollama_openai_base_url(ollama_host)
    operator_surface.save_app_ai_env(
        {
            "OLLAMA_HOST": ollama_host,
            "OPENAI_BASE_URL": local_base_url,
            "ANTHROPIC_BASE_URL": local_base_url,
        }
    )
    codex_updates = {
        "OPENAI_BASE_URL": local_base_url,
        "ANTHROPIC_BASE_URL": local_base_url,
    }
    if selected_model:
        codex_updates.update(
            {
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": selected_model,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": selected_model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": selected_model,
            }
        )
    operator_surface.write_codex_settings_env(codex_updates)

    if request.form.get("CONFIGURE_9ROUTER") and selected_model:
        result = operator_surface.configure_9router_local_model(ollama_host, selected_model)
        flash(
            f"Local model route saved: {result['alias']} -> {result['routed_model']}.",
            "success",
        )
    elif selected_model:
        flash("Local model defaults saved for LOKI THE SUN GOD and Codex.", "success")
    else:
        flash("No local model found yet. Run `ollama pull qwen2.5-coder:7b`, then save again.", "warning")
    return redirect(url_for("ai_ops"))


@app.route("/ops/ai/router/save", methods=["POST"])
@login_required
@ops_admin_required
def ai_ops_save_router():
    updates = {
        "PORT": _normalize_setting_text(request.form.get("PORT")) or "20128",
        "BASE_URL": _normalize_setting_text(request.form.get("BASE_URL")) or "http://localhost:20128",
        "CLOUD_URL": _normalize_setting_text(request.form.get("CLOUD_URL")) or "https://9router.com",
        "NEXT_PUBLIC_BASE_URL": _normalize_setting_text(request.form.get("NEXT_PUBLIC_BASE_URL"))
        or "http://localhost:20128",
        "NEXT_PUBLIC_CLOUD_URL": _normalize_setting_text(request.form.get("NEXT_PUBLIC_CLOUD_URL"))
        or "https://9router.com",
        "DATA_DIR": _normalize_setting_text(request.form.get("DATA_DIR")),
        "ENABLE_REQUEST_LOGS": "true" if request.form.get("ENABLE_REQUEST_LOGS") else "false",
        "OBSERVABILITY_ENABLED": "true" if request.form.get("OBSERVABILITY_ENABLED") else "false",
        "AUTH_COOKIE_SECURE": "true" if request.form.get("AUTH_COOKIE_SECURE") else "false",
        "REQUIRE_API_KEY": "true" if request.form.get("REQUIRE_API_KEY") else "false",
    }
    for field in ("JWT_SECRET", "INITIAL_PASSWORD", "API_KEY_SECRET", "MACHINE_ID_SALT"):
        secret_value = _secret_update(field)
        if secret_value is not None:
            updates[field] = secret_value
    operator_surface.save_router_runtime_env(updates)
    flash("9router runtime settings saved.", "success")
    return redirect(url_for("ai_ops"))


@app.route("/ops/ai/memory/save", methods=["POST"])
@login_required
@ops_admin_required
def ai_ops_save_memory():
    palace_path = _normalize_setting_text(request.form.get("palace_path"))
    normalized_path = palace_path.replace("\\", "/").lower()
    if palace_path and (_looks_like_root_path(palace_path) or normalized_path.endswith((".json", ".md"))):
        flash("Palace path must point to a directory, not a root path or file.", "danger")
        return redirect(url_for("ai_ops"))

    operator_surface.save_mempalace_config(
        {
            "palace_path": palace_path,
            "collection_name": _normalize_setting_text(request.form.get("collection_name")),
            "topic_wings": _multiline_tokens(request.form.get("topic_wings")),
        }
    )
    flash("MemPalace config saved.", "success")
    return redirect(url_for("ai_ops"))


@app.route("/guild/<guild_id>")
@login_required
@guild_admin_required
def guild(guild_id):
    guild_id = int(guild_id)
    structure = _guild_template_context(guild_id)
    cfg = db_one("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
    if not cfg:
        db_exec("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (guild_id,))
        cfg = db_one("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
    automod = db_one("SELECT * FROM automod_rules WHERE guild_id=?", (guild_id,))
    if not automod:
        db_exec("INSERT OR IGNORE INTO automod_rules(guild_id) VALUES(?)", (guild_id,))
        automod = db_one("SELECT * FROM automod_rules WHERE guild_id=?", (guild_id,))
    suggestion_cfg = db_one("SELECT * FROM suggestion_config WHERE guild_id=?", (guild_id,))
    disabled_cmds = [r[0] for r in db_all("SELECT command FROM disabled_commands WHERE guild_id=?", (guild_id,))]
    mod_roles = [r[0] for r in db_all("SELECT role_id FROM mod_roles WHERE guild_id=?", (guild_id,))]
    autoroles = [r[0] for r in db_all("SELECT role_id FROM autoroles WHERE guild_id=?", (guild_id,))]
    forms = db_all("SELECT name, title, target_channel_id FROM forms WHERE guild_id=?", (guild_id,))
    events = db_all(
        "SELECT id, title, starts_at FROM events WHERE guild_id=? AND starts_at>? ORDER BY starts_at LIMIT 10",
        (guild_id, int(__import__("time").time())),
    )

    # KPI counts — safe COALESCE, single row each
    def _count(sql, params=()):
        r = db_one(sql, params)
        return r[0] if r else 0

    kpis = {
        "forms": len(forms),
        "events": len(events),
        "tickets_open": _count("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)),
        "tags": _count("SELECT COUNT(*) FROM tags WHERE guild_id=?", (guild_id,)),
        "streams": _count("SELECT COUNT(*) FROM stream_subs WHERE guild_id=?", (guild_id,)),
        "warnings": _count("SELECT COUNT(*) FROM warnings WHERE guild_id=?", (guild_id,)),
        "pending_apps": _count(
            "SELECT COUNT(*) FROM form_responses WHERE guild_id=? AND COALESCE(status,'pending')='pending'", (guild_id,)
        ),
        "disabled_cmds": len(disabled_cmds),
    }
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "guild.html",
        cfg=cfg,
        automod=automod,
        suggestion_cfg=suggestion_cfg,
        disabled_cmds=disabled_cmds,
        mod_roles=mod_roles,
        autoroles=autoroles,
        forms=forms,
        events=events,
        kpis=kpis,
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_save(guild_id):
    guild_id = int(guild_id)
    f = request.form

    # ── general ──
    prefix = f.get("prefix", "!")[:10]
    mute_role = _int_or_none(f.get("mute_role"))
    log_ch = _int_or_none(f.get("log_channel"))
    welcome_ch = _int_or_none(f.get("welcome_channel"))
    welcome_msg = f.get("welcome_msg", "")[:500]
    goodbye_msg = f.get("goodbye_msg", "")[:500]
    star_ch = _int_or_none(f.get("starboard_channel"))
    star_thresh = _safe_int(f.get("star_threshold"), 3)
    level_enabled = 1 if f.get("level_enabled") else 0

    shared_db.save_guild_config_sync(
        guild_id,
        {
            "prefix": prefix,
            "mute_role": mute_role,
            "log_channel": log_ch,
            "welcome_channel": welcome_ch,
            "welcome_msg": welcome_msg,
            "goodbye_msg": goodbye_msg,
            "starboard_channel": star_ch,
            "star_threshold": star_thresh,
            "level_enabled": level_enabled,
        },
    )

    # ── automod ──
    am = {
        "anti_invite": 1 if f.get("anti_invite") else 0,
        "anti_spam": 1 if f.get("anti_spam") else 0,
        "anti_caps": 1 if f.get("anti_caps") else 0,
        "anti_mention": 1 if f.get("anti_mention") else 0,
        "max_mentions": _safe_int(f.get("max_mentions"), 5),
        "spam_threshold": _safe_int(f.get("spam_threshold"), 5),
        "caps_percent": _safe_int(f.get("caps_percent"), 70),
        "bad_words": (f.get("bad_words") or "")[:1000],
    }
    shared_db.save_automod_rules_sync(guild_id, am)

    flash("Settings saved!", "success")
    return redirect(url_for("guild", guild_id=guild_id))


@app.route("/guild/<guild_id>/events")
@login_required
@guild_admin_required
def guild_events(guild_id):
    guild_id = int(guild_id)
    events = [
        dict(row)
        for row in db_all(
            "SELECT e.id, e.title, e.description, e.starts_at, e.location, e.color, e.channel_id, e.message_id, "
            "(SELECT COUNT(*) FROM event_reminders er WHERE er.event_id=e.id AND er.fired=0) as pending_reminders, "
            "(SELECT COUNT(*) FROM event_reposts ep WHERE ep.event_id=e.id) as reposts "
            "FROM events e WHERE e.guild_id=? ORDER BY e.starts_at DESC LIMIT 30",
            (guild_id,),
        )
    ]
    for event in events:
        event["starts_at_input"] = _event_datetime_input(event["starts_at"])
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    structure = _guild_template_context(guild_id)
    return render_template(
        "events.html", events=events, guild_id=guild_id, guild_info=g_info, user=session["user"], **structure
    )


@app.route("/guild/<guild_id>/events/create", methods=["POST"])
@login_required
@guild_admin_required
def guild_events_create(guild_id):
    guild_id = int(guild_id)
    title = (request.form.get("title") or "").strip()[:120]
    description = (request.form.get("description") or "").strip()[:2000]
    location = (request.form.get("location") or "").strip()[:200]
    starts_at = _parse_event_datetime(request.form.get("starts_at") or "")
    color_text = (request.form.get("color") or "#57F287").strip()
    if not title or not description or not starts_at:
        flash("Title, start time, and description are required.", "danger")
        return redirect(url_for("guild_events", guild_id=guild_id))
    try:
        color = int(color_text.strip("#"), 16)
    except ValueError:
        color = 0x57F287
    db_exec(
        "INSERT INTO events(guild_id,channel_id,message_id,title,description,starts_at,host_id,color,location) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (guild_id, 0, 0, title, description, starts_at, 0, color, location),
    )
    flash("Event created from the dashboard.", "success")
    return redirect(url_for("guild_events", guild_id=guild_id))


@app.route("/guild/<guild_id>/events/<int:event_id>/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_events_save(guild_id, event_id):
    guild_id = int(guild_id)
    title = (request.form.get("title") or "").strip()[:120]
    description = (request.form.get("description") or "").strip()[:2000]
    location = (request.form.get("location") or "").strip()[:200]
    starts_at = _parse_event_datetime(request.form.get("starts_at") or "")
    color_text = (request.form.get("color") or "").strip()
    reminder_offset = (request.form.get("reminder_offset") or "").strip()
    if not title or not description or not starts_at:
        flash("Title, start time, and description are required.", "danger")
        return redirect(url_for("guild_events", guild_id=guild_id))
    try:
        color = int((color_text or "#57F287").strip("#"), 16)
    except ValueError:
        flash("Event color must be a hex value like #57F287.", "danger")
        return redirect(url_for("guild_events", guild_id=guild_id))
    updated = db_exec(
        "UPDATE events SET title=?, description=?, starts_at=?, location=?, color=? WHERE id=? AND guild_id=?",
        (title, description, starts_at, location, color, event_id, guild_id),
    )
    if not updated:
        flash(f"No event with ID {event_id} was found.", "danger")
        return redirect(url_for("guild_events", guild_id=guild_id))
    if reminder_offset:
        try:
            from utils.helpers import parse_duration

            offset_secs = parse_duration(reminder_offset)
        except Exception:
            offset_secs = None
        if not offset_secs:
            flash("Saved event changes, but reminder offset was invalid.", "warning")
        else:
            db_exec("INSERT INTO event_reminders(event_id,offset_secs) VALUES(?,?)", (event_id, offset_secs))
            flash("Event updated and reminder added.", "success")
            return redirect(url_for("guild_events", guild_id=guild_id))
    flash("Event settings saved.", "success")
    return redirect(url_for("guild_events", guild_id=guild_id))


@app.route("/guild/<guild_id>/events/<int:event_id>/delete", methods=["POST"])
@login_required
@guild_admin_required
def guild_events_delete(guild_id, event_id):
    guild_id = int(guild_id)
    removed = db_exec("DELETE FROM events WHERE id=? AND guild_id=?", (event_id, guild_id))
    db_exec("DELETE FROM event_reminders WHERE event_id=?", (event_id,))
    db_exec("DELETE FROM event_reposts WHERE event_id=?", (event_id,))
    flash("Event removed." if removed else "That event was not found.", "success" if removed else "warning")
    return redirect(url_for("guild_events", guild_id=guild_id))


@app.route("/guild/<guild_id>/forms")
@login_required
@guild_admin_required
def guild_forms(guild_id):
    guild_id = int(guild_id)
    forms = db_all("SELECT name, title, target_channel_id, button_label FROM forms WHERE guild_id=?", (guild_id,))
    form_responses = {}
    for form in forms:
        cnt = db_one("SELECT COUNT(*) FROM form_responses WHERE guild_id=? AND form_name=?", (guild_id, form["name"]))
        form_responses[form["name"]] = cnt[0] if cnt else 0
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    structure = _guild_template_context(guild_id)
    return render_template(
        "forms.html",
        forms=forms,
        form_responses=form_responses,
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/commands")
@login_required
@guild_admin_required
def guild_commands(guild_id):
    guild_id = int(guild_id)
    commands = [c for c in parse_command_catalog(COMMAND_ROOT) if c.get("slash_enabled")]
    category_counts = Counter(command["category"] for command in commands)
    structure = _guild_template_context(guild_id)
    disabled_commands = [
        row[0] for row in db_all("SELECT command FROM disabled_commands WHERE guild_id=?", (guild_id,))
    ]
    ignored_channels = [
        row[0] for row in db_all("SELECT channel_id FROM ignored_channels WHERE guild_id=?", (guild_id,))
    ]
    mod_roles = [row[0] for row in db_all("SELECT role_id FROM mod_roles WHERE guild_id=?", (guild_id,))]
    stats = {
        "total": len(commands),
        "with_options": sum(1 for command in commands if command.get("option_count")),
        "option_total": sum(command.get("option_count", 0) for command in commands),
        "autocomplete_total": sum(
            1 for command in commands if any(option.get("autocomplete") for option in command.get("options", []))
        ),
    }
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "commands.html",
        commands=commands,
        command_names=sorted(command["full_name"] for command in commands),
        category_counts=sorted(category_counts.items()),
        stats=stats,
        disabled_commands=disabled_commands,
        ignored_channels=ignored_channels,
        mod_roles=mod_roles,
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/mixer")
@login_required
@guild_admin_required
def guild_mixer(guild_id):
    guild_id = int(guild_id)
    structure = _guild_template_context(guild_id)
    settings = db_one("SELECT * FROM loki_music_settings WHERE guild_id=?", (guild_id,))
    if not settings:
        db_exec(
            "INSERT OR IGNORE INTO loki_music_settings(guild_id, updated_at) VALUES(?,?)",
            (guild_id, int(time.time())),
        )
        settings = db_one("SELECT * FROM loki_music_settings WHERE guild_id=?", (guild_id,))
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "mixer.html",
        guild_id=guild_id,
        guild_info=g_info,
        settings=settings,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/mixer/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_mixer_save(guild_id):
    guild_id = int(guild_id)
    preset = request.form.get("eq_preset", "Flat").strip() or "Flat"
    volume = max(0, min(150, int(request.form.get("volume", "80") or "80")))
    db_exec(
        """
        INSERT OR REPLACE INTO loki_music_settings(
            guild_id, dj_role_id, request_channel_id, eq_preset, mixer_locked, volume, updated_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            guild_id,
            _int_or_none(request.form.get("dj_role_id")),
            _int_or_none(request.form.get("request_channel_id")),
            preset,
            1 if request.form.get("mixer_locked") == "on" else 0,
            volume,
            int(time.time()),
        ),
    )
    flash("LOKI mixer settings saved.", "success")
    return redirect(url_for("guild_mixer", guild_id=guild_id))


@app.route("/guild/<guild_id>/npc")
@login_required
@guild_admin_required
def guild_npc(guild_id):
    guild_id = int(guild_id)
    structure = _guild_template_context(guild_id)
    settings = db_one("SELECT * FROM loki_npc_settings WHERE guild_id=?", (guild_id,))
    if not settings:
        db_exec(
            "INSERT OR IGNORE INTO loki_npc_settings(guild_id, updated_at) VALUES(?,?)",
            (guild_id, int(time.time())),
        )
        settings = db_one("SELECT * FROM loki_npc_settings WHERE guild_id=?", (guild_id,))
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "npc.html",
        guild_id=guild_id,
        guild_info=g_info,
        settings=settings,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/npc/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_npc_save(guild_id):
    guild_id = int(guild_id)
    db_exec(
        """
        INSERT OR REPLACE INTO loki_npc_settings(
            guild_id, enabled, persona_json, channel_allowlist, web_crawl_enabled, auto_post_channel_id, updated_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            guild_id,
            1 if request.form.get("enabled") == "on" else 0,
            request.form.get("persona_json", "").strip(),
            request.form.get("channel_allowlist", "").strip(),
            1 if request.form.get("web_crawl_enabled") == "on" else 0,
            _int_or_none(request.form.get("auto_post_channel_id")),
            int(time.time()),
        ),
    )
    flash("LOKI NPC settings saved.", "success")
    return redirect(url_for("guild_npc", guild_id=guild_id))


@app.route("/guild/<guild_id>/activities-control")
@login_required
@guild_admin_required
def guild_activities_control(guild_id):
    guild_id = int(guild_id)
    structure = _guild_template_context(guild_id)
    activities = db_all(
        "SELECT * FROM loki_activity_controls WHERE guild_id=? ORDER BY created_at DESC LIMIT 50",
        (guild_id,),
    )
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "activities_control.html",
        guild_id=guild_id,
        guild_info=g_info,
        activities=activities,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/activities-control/create", methods=["POST"])
@login_required
@guild_admin_required
def guild_activities_control_create(guild_id):
    guild_id = int(guild_id)
    title = request.form.get("title", "").strip()
    if not title:
        flash("Activity title is required.", "danger")
        return redirect(url_for("guild_activities_control", guild_id=guild_id))
    db_exec(
        """
        INSERT INTO loki_activity_controls(guild_id, title, status, activity_type, created_by, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            guild_id,
            title,
            request.form.get("status", "planned").strip() or "planned",
            request.form.get("activity_type", "portal").strip() or "portal",
            int(session.get("user", {}).get("id", "0") or 0),
            int(time.time()),
            int(time.time()),
        ),
    )
    flash("LOKI activity created.", "success")
    return redirect(url_for("guild_activities_control", guild_id=guild_id))


@app.route("/guild/<guild_id>/developer")
@login_required
@guild_admin_required
def guild_developer(guild_id):
    guild_id = int(guild_id)
    structure = _guild_template_context(guild_id)
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "developer_settings.html",
        guild_id=guild_id,
        guild_info=g_info,
        app_env=operator_surface.ai_router_settings().get("app_env", {}),
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/commands/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_commands_save(guild_id):
    guild_id = int(guild_id)
    action = (request.form.get("action") or "").strip().lower()
    if action == "disable":
        command = (request.form.get("command") or "").strip()
        if not command:
            flash("Choose a command to disable.", "danger")
        else:
            db_exec("INSERT OR IGNORE INTO disabled_commands(guild_id,command) VALUES(?,?)", (guild_id, command))
            flash(f"Disabled `{command}` for non-admins.", "success")
    elif action == "enable":
        command = (request.form.get("command") or "").strip()
        removed = db_exec("DELETE FROM disabled_commands WHERE guild_id=? AND command=?", (guild_id, command))
        flash(
            f"Re-enabled `{command}`." if removed else f"`{command}` was not disabled.",
            "success" if removed else "warning",
        )
    elif action == "ignore":
        channel_id = _int_or_none(request.form.get("channel_id"))
        if not channel_id:
            flash("Choose a channel to ignore.", "danger")
        else:
            db_exec("INSERT OR IGNORE INTO ignored_channels(guild_id,channel_id) VALUES(?,?)", (guild_id, channel_id))
            flash("Ignored channel saved.", "success")
    elif action == "unignore":
        channel_id = _int_or_none(request.form.get("channel_id"))
        removed = db_exec("DELETE FROM ignored_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        flash("Channel restored." if removed else "That channel was not ignored.", "success" if removed else "warning")
    elif action == "add_mod_role":
        role_id = _int_or_none(request.form.get("role_id"))
        if not role_id:
            flash("Choose a moderator role to add.", "danger")
        else:
            db_exec("INSERT OR IGNORE INTO mod_roles(guild_id,role_id) VALUES(?,?)", (guild_id, role_id))
            flash("Moderator role added.", "success")
    elif action == "remove_mod_role":
        role_id = _int_or_none(request.form.get("role_id"))
        removed = db_exec("DELETE FROM mod_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
        flash(
            "Moderator role removed." if removed else "That role was not configured.",
            "success" if removed else "warning",
        )
    else:
        flash("Unsupported commands action.", "danger")
    return redirect(url_for("guild_commands", guild_id=guild_id))


@app.route("/guild/<guild_id>/forms/<form_name>/responses")
@login_required
@guild_admin_required
def form_responses_page(guild_id, form_name):
    guild_id = int(guild_id)
    responses = db_all(
        "SELECT id, user_id, responses, submitted_at, "
        "COALESCE(status,'pending') AS status, decided_by, decided_at, decision_note "
        "FROM form_responses "
        "WHERE guild_id=? AND form_name=? ORDER BY submitted_at DESC LIMIT 100",
        (guild_id, form_name),
    )
    parsed = []
    counts = {"pending": 0, "approved": 0, "denied": 0}
    for r in responses:
        try:
            ans = json.loads(r["responses"])
        except Exception:
            ans = {}
        st = r["status"] or "pending"
        counts[st] = counts.get(st, 0) + 1
        parsed.append(
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "submitted_at": r["submitted_at"],
                "answers": ans,
                "status": st,
                "decided_by": r["decided_by"],
                "decided_at": r["decided_at"],
                "decision_note": r["decision_note"] or "",
            }
        )
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    return render_template(
        "form_responses.html",
        responses=parsed,
        form_name=form_name,
        counts=counts,
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
    )


# ─── Streams ─────────────────────────────────────────────────────────────────


def _ensure_streams_table():
    db_exec("""CREATE TABLE IF NOT EXISTS stream_subs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        channel_name TEXT NOT NULL,
        target_channel_id INTEGER NOT NULL,
        mention_role_id INTEGER,
        last_status INTEGER DEFAULT 0,
        last_event_at INTEGER DEFAULT 0,
        UNIQUE(guild_id, platform, channel_name))""")


@app.route("/guild/<guild_id>/streams")
@login_required
@guild_admin_required
def guild_streams(guild_id):
    guild_id = int(guild_id)
    _ensure_streams_table()
    streams = db_all(
        "SELECT id, platform, channel_name, target_channel_id, mention_role_id, last_status "
        "FROM stream_subs WHERE guild_id=? ORDER BY platform, channel_name",
        (guild_id,),
    )
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    structure = _guild_template_context(guild_id)
    return render_template(
        "streams.html", streams=streams, guild_id=guild_id, guild_info=g_info, user=session["user"], **structure
    )


@app.route("/guild/<guild_id>/streams/add", methods=["POST"])
@login_required
@guild_admin_required
def guild_streams_add(guild_id):
    guild_id = int(guild_id)
    _ensure_streams_table()
    f = request.form
    platform = (f.get("platform") or "").lower().strip()
    if platform not in ("twitch", "kick", "tiktok"):
        flash("Invalid platform.", "danger")
        return redirect(url_for("guild_streams", guild_id=guild_id))
    name = (f.get("channel_name") or "").strip()
    target = _int_or_none(f.get("target_channel_id"))
    role = _int_or_none(f.get("mention_role_id"))
    if not name or not target:
        flash("Channel name and target channel are required.", "danger")
        return redirect(url_for("guild_streams", guild_id=guild_id))
    try:
        db_exec(
            "INSERT INTO stream_subs(guild_id, platform, channel_name, target_channel_id, mention_role_id) "
            "VALUES(?,?,?,?,?)",
            (guild_id, platform, name, target, role),
        )
        flash(f"Tracking {platform}/{name}.", "success")
    except shared_db.IntegrityError:
        flash("Already tracked.", "danger")
    return redirect(url_for("guild_streams", guild_id=guild_id))


@app.route("/guild/<guild_id>/streams/<int:stream_id>/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_streams_save(guild_id, stream_id):
    guild_id = int(guild_id)
    _ensure_streams_table()
    platform = (request.form.get("platform") or "").lower().strip()
    name = (request.form.get("channel_name") or "").strip()
    target = _int_or_none(request.form.get("target_channel_id"))
    role = _int_or_none(request.form.get("mention_role_id"))
    if platform not in ("twitch", "kick", "tiktok") or not name or not target:
        flash("Platform, creator name, and target channel are required.", "danger")
        return redirect(url_for("guild_streams", guild_id=guild_id))
    updated = db_exec(
        "UPDATE stream_subs SET platform=?, channel_name=?, target_channel_id=?, mention_role_id=? "
        "WHERE id=? AND guild_id=?",
        (platform, name, target, role, stream_id, guild_id),
    )
    flash(
        "Stream updated." if updated else "That stream subscription was not found.", "success" if updated else "warning"
    )
    return redirect(url_for("guild_streams", guild_id=guild_id))


@app.route("/guild/<guild_id>/streams/delete", methods=["POST"])
@login_required
@guild_admin_required
def guild_streams_delete(guild_id):
    guild_id = int(guild_id)
    sid = _int_or_none(request.form.get("id"))
    if sid:
        db_exec("DELETE FROM stream_subs WHERE id=? AND guild_id=?", (sid, guild_id))
        flash("Removed.", "success")
    return redirect(url_for("guild_streams", guild_id=guild_id))


# ─── Form builder ────────────────────────────────────────────────────────────


@app.route("/guild/<guild_id>/forms/create", methods=["POST"])
@login_required
@guild_admin_required
def guild_forms_create(guild_id):
    guild_id = int(guild_id)
    name = (request.form.get("name") or "").strip().lower()
    title = (request.form.get("title") or "").strip()
    if not name or not title:
        flash("Name and title required.", "danger")
        return redirect(url_for("guild_forms", guild_id=guild_id))
    try:
        db_exec(
            "INSERT INTO forms(guild_id, name, title, fields, button_label) VALUES(?,?,?,?,?)",
            (guild_id, name, title, "[]", "Fill Form"),
        )
        flash(f"Form '{name}' created.", "success")
        return redirect(url_for("form_edit", guild_id=guild_id, form_name=name))
    except shared_db.IntegrityError:
        flash("A form with that name already exists.", "danger")
        return redirect(url_for("guild_forms", guild_id=guild_id))


@app.route("/guild/<guild_id>/forms/<form_name>/edit")
@login_required
@guild_admin_required
def form_edit(guild_id, form_name):
    guild_id = int(guild_id)
    form = db_one(
        "SELECT name, title, target_channel_id, button_label, fields FROM forms WHERE guild_id=? AND name=?",
        (guild_id, form_name),
    )
    if not form:
        flash("Form not found.", "danger")
        return redirect(url_for("guild_forms", guild_id=guild_id))
    try:
        existing_fields = json.loads(form["fields"] or "[]")
    except Exception:
        existing_fields = []
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), {})
    structure = _guild_template_context(guild_id)
    return render_template(
        "form_builder.html",
        form={
            "title": form["title"],
            "button_label": form["button_label"],
            "target_channel_id": form["target_channel_id"],
        },
        existing_fields=existing_fields,
        form_name=form_name,
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
        **structure,
    )


@app.route("/guild/<guild_id>/forms/<form_name>/save", methods=["POST"])
@login_required
@guild_admin_required
def form_save(guild_id, form_name):
    guild_id = int(guild_id)
    f = request.form
    title = (f.get("title") or "")[:45]
    button_label = (f.get("button_label") or "Fill Form")[:80]
    target = _int_or_none(f.get("target_channel_id"))
    if not title.strip():
        flash("Form title is required.", "danger")
        return redirect(url_for("form_edit", guild_id=guild_id, form_name=form_name))
    try:
        fields = json.loads(f.get("fields_json") or "[]")
        # sanitize — preserves advanced attrs (min/max len, default, pattern)
        clean = []
        for item in fields[:5]:
            label = str(item.get("label", "")).strip()[:45]
            if not label:
                continue
            row = {
                "label": label,
                "style": "long" if item.get("style") == "long" else "short",
                "required": bool(item.get("required", True)),
                "placeholder": str(item.get("placeholder", ""))[:100],
            }
            # Discord modal hard caps: 0..4000 length
            if item.get("min_length") not in (None, ""):
                try:
                    row["min_length"] = max(0, min(4000, int(item["min_length"])))
                except (TypeError, ValueError):
                    pass
            if item.get("max_length") not in (None, ""):
                try:
                    row["max_length"] = max(1, min(4000, int(item["max_length"])))
                except (TypeError, ValueError):
                    pass
            if item.get("default"):
                row["default"] = str(item["default"])[:100]
            if item.get("pattern"):
                row["pattern"] = str(item["pattern"])[:200]
            clean.append(row)
        if not clean:
            flash("Add at least one field with a label before saving.", "danger")
            return redirect(url_for("form_edit", guild_id=guild_id, form_name=form_name))
        fields_json = json.dumps(clean)
    except Exception as e:
        flash(f"Invalid fields JSON: {e}", "danger")
        return redirect(url_for("form_edit", guild_id=guild_id, form_name=form_name))
    db_exec(
        "UPDATE forms SET title=?, button_label=?, target_channel_id=?, fields=? WHERE guild_id=? AND name=?",
        (title, button_label, target, fields_json, guild_id, form_name),
    )
    flash("Form saved.", "success")
    return redirect(url_for("form_edit", guild_id=guild_id, form_name=form_name))


# ─── Embed builder + send-as-bot ─────────────────────────────────────────────


def _bot_get(path: str):
    return requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bot {bot_token()}"},
        timeout=HTTP_TIMEOUT,
    )


def _bot_post(path: str, payload: dict):
    return requests.post(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bot {bot_token()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=HTTP_TIMEOUT,
    )


@app.route("/guild/<guild_id>/embed", methods=["GET"])
@login_required
@guild_admin_required
def guild_embed_builder(guild_id):
    guild_id = int(guild_id)
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), None)
    structure = _guild_template_context(guild_id)
    # Channels — fetched from Discord (cache could be added later)
    channels = []
    if bot_token():
        try:
            r = _bot_get(f"/guilds/{guild_id}/channels")
            if r.ok:
                channels = [
                    {"id": c["id"], "name": c["name"], "type": c["type"]}
                    for c in r.json()
                    if c.get("type") in (0, 5)  # text + announcement
                ]
                channels.sort(key=lambda c: c["name"])
        except Exception:
            pass
    return render_template(
        "embed_builder.html",
        guild_id=guild_id,
        guild_info=g_info,
        channels=structure["channel_choices"] or channels,
        user=session["user"],
    )


@app.route("/guild/<guild_id>/embed/send", methods=["POST"])
@login_required
@guild_admin_required
def guild_embed_send(guild_id):
    payload = request.get_json(force=True) or {}
    channel_id = payload.get("channel_id")
    if not channel_id:
        return jsonify({"ok": False, "error": "channel_id required"}), 400
    token = bot_token()
    if not token:
        return jsonify({"ok": False, "error": "DISCORD_TOKEN is not configured for embed sending."}), 400
    if len(token.split(".")) < 2:
        return jsonify(
            {"ok": False, "error": "DISCORD_TOKEN format looks invalid; check the dashboard environment."}
        ), 400

    embed = payload.get("embed") or {}
    # Build a sanitized Discord embed object
    out_embed = {}
    for k in ("title", "description", "url"):
        v = (embed.get(k) or "").strip()
        if v:
            out_embed[k] = v[: 4000 if k == "description" else 256]
    if embed.get("color"):
        try:
            c = embed["color"]
            if isinstance(c, str) and c.startswith("#"):
                c = int(c[1:], 16)
            out_embed["color"] = int(c) & 0xFFFFFF
        except (TypeError, ValueError):
            pass
    if embed.get("image_url"):
        out_embed["image"] = {"url": embed["image_url"]}
    if embed.get("thumbnail_url"):
        out_embed["thumbnail"] = {"url": embed["thumbnail_url"]}
    if embed.get("author_name"):
        out_embed["author"] = {
            "name": embed["author_name"][:256],
            **({"icon_url": embed["author_icon"]} if embed.get("author_icon") else {}),
            **({"url": embed["author_url"]} if embed.get("author_url") else {}),
        }
    if embed.get("footer_text"):
        out_embed["footer"] = {
            "text": embed["footer_text"][:2048],
            **({"icon_url": embed["footer_icon"]} if embed.get("footer_icon") else {}),
        }
    if embed.get("timestamp"):
        out_embed["timestamp"] = embed["timestamp"]
    fields = embed.get("fields") or []
    if fields:
        out_embed["fields"] = [
            {
                "name": (f.get("name") or "​")[:256],
                "value": (f.get("value") or "​")[:1024],
                "inline": bool(f.get("inline")),
            }
            for f in fields[:25]
        ]

    body = {
        "content": (payload.get("content") or "")[:2000] or None,
        "embeds": [out_embed] if out_embed else [],
    }
    body = {k: v for k, v in body.items() if v}

    try:
        r = _bot_post(f"/channels/{channel_id}/messages", body)
        if r.ok:
            data = r.json()
            return jsonify({"ok": True, "message_id": data.get("id")})
        return jsonify({"ok": False, "error": r.text, "status": r.status_code}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Audit log timeline ──────────────────────────────────────────────────────


@app.route("/guild/<guild_id>/audit")
@login_required
@guild_admin_required
def guild_audit(guild_id):
    guild_id = int(guild_id)
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), None)
    # Unified timeline: warnings + notes + tickets + form responses
    events = []
    for r in db_all(
        "SELECT id, user_id, mod_id, reason, created_at FROM warnings "
        "WHERE guild_id=? ORDER BY created_at DESC LIMIT 200",
        (guild_id,),
    ):
        events.append(
            {
                "type": "warning",
                "ts": r["created_at"],
                "actor": r["mod_id"],
                "subject": r["user_id"],
                "detail": r["reason"],
                "id": r["id"],
            }
        )
    for r in db_all(
        "SELECT id, user_id, mod_id, content, created_at FROM notes "
        "WHERE guild_id=? ORDER BY created_at DESC LIMIT 200",
        (guild_id,),
    ):
        events.append(
            {
                "type": "note",
                "ts": r["created_at"],
                "actor": r["mod_id"],
                "subject": r["user_id"],
                "detail": r["content"],
                "id": r["id"],
            }
        )
    for r in db_all(
        "SELECT id, opener_id, status, opened_at, closed_at, reason FROM tickets "
        "WHERE guild_id=? ORDER BY opened_at DESC LIMIT 200",
        (guild_id,),
    ):
        events.append(
            {
                "type": "ticket-open",
                "ts": r["opened_at"],
                "actor": r["opener_id"],
                "subject": r["opener_id"],
                "detail": r["reason"] or f"#{r['id']}",
                "id": r["id"],
            }
        )
        if r["closed_at"]:
            events.append(
                {
                    "type": "ticket-close",
                    "ts": r["closed_at"],
                    "actor": None,
                    "subject": r["opener_id"],
                    "detail": f"#{r['id']}",
                    "id": r["id"],
                }
            )
    for r in db_all(
        "SELECT id, form_name, user_id, status, decided_by, decided_at, submitted_at "
        "FROM form_responses WHERE guild_id=? ORDER BY submitted_at DESC LIMIT 200",
        (guild_id,),
    ):
        events.append(
            {
                "type": "form-submit",
                "ts": r["submitted_at"],
                "actor": r["user_id"],
                "subject": r["user_id"],
                "detail": r["form_name"],
                "id": r["id"],
            }
        )
        if r["decided_at"] and r["status"] in ("approved", "denied"):
            events.append(
                {
                    "type": f"form-{r['status']}",
                    "ts": r["decided_at"],
                    "actor": r["decided_by"],
                    "subject": r["user_id"],
                    "detail": r["form_name"],
                    "id": r["id"],
                }
            )
    events.sort(key=lambda e: e["ts"], reverse=True)
    events = events[:300]
    return render_template("audit.html", guild_id=guild_id, guild_info=g_info, user=session["user"], events=events)


# ─── Tickets dashboard panel ─────────────────────────────────────────────────


@app.route("/guild/<guild_id>/tickets")
@login_required
@guild_admin_required
def guild_tickets(guild_id):
    guild_id = int(guild_id)
    g_info = next((g for g in session.get("guilds", []) if str(g["id"]) == str(guild_id)), None)
    cfg = db_one(
        "SELECT tickets_category_id, tickets_log_channel, tickets_staff_role FROM guild_config WHERE guild_id=?",
        (guild_id,),
    )
    rows = db_all(
        "SELECT id, channel_id, opener_id, status, opened_at, closed_at, reason "
        "FROM tickets WHERE guild_id=? ORDER BY opened_at DESC LIMIT 200",
        (guild_id,),
    )
    tickets = [dict(r) for r in rows]
    open_count = sum(1 for t in tickets if t["status"] == "open")
    closed_count = sum(1 for t in tickets if t["status"] == "closed")
    structure = _guild_template_context(guild_id)
    return render_template(
        "tickets.html",
        guild_id=guild_id,
        guild_info=g_info,
        user=session["user"],
        tickets=tickets,
        open_count=open_count,
        closed_count=closed_count,
        cfg=cfg,
        **structure,
    )


@app.route("/guild/<guild_id>/tickets/save", methods=["POST"])
@login_required
@guild_admin_required
def guild_tickets_save(guild_id):
    guild_id = int(guild_id)
    shared_db.save_guild_config_sync(
        guild_id,
        {
            "tickets_category_id": _int_or_none(request.form.get("tickets_category_id")),
            "tickets_log_channel": _int_or_none(request.form.get("tickets_log_channel")),
            "tickets_staff_role": _int_or_none(request.form.get("tickets_staff_role")),
        },
    )
    flash("Ticket settings saved.", "success")
    return redirect(url_for("guild_tickets", guild_id=guild_id))


# ─── Form response approve/deny ──────────────────────────────────────────────


@app.route("/guild/<guild_id>/forms/<form_name>/responses/<int:resp_id>/decide", methods=["POST"])
@login_required
@guild_admin_required
def form_response_decide(guild_id, form_name, resp_id):
    guild_id = int(guild_id)
    decision = (request.form.get("decision") or "").lower()
    note = (request.form.get("note") or "")[:500]
    if decision not in ("approved", "denied", "pending"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("form_responses_page", guild_id=guild_id, form_name=form_name))
    db_exec(
        "UPDATE form_responses SET status=?, decided_by=?, decided_at=?, decision_note=? "
        "WHERE id=? AND guild_id=? AND form_name=?",
        (decision, session["user"]["id"], int(__import__("time").time()), note, resp_id, guild_id, form_name),
    )
    # Optional: DM the applicant about the decision via bot
    if bot_token() and decision in ("approved", "denied"):
        try:
            row = db_one("SELECT user_id FROM form_responses WHERE id=?", (resp_id,))
            if row:
                # Discord requires opening a DM channel first
                dm = requests.post(
                    f"{API_BASE}/users/@me/channels",
                    headers={"Authorization": f"Bot {bot_token()}", "Content-Type": "application/json"},
                    json={"recipient_id": str(row["user_id"])},
                    timeout=8,
                )
                if dm.ok:
                    dm_id = dm.json().get("id")
                    if dm_id:
                        verb = "approved ✅" if decision == "approved" else "denied ❌"
                        verb = "approved" if decision == "approved" else "denied"
                        msg = f"Your application **{form_name}** was {verb}."
                        if note:
                            msg += f"\n\n> {note}"
                        _bot_post(f"/channels/{dm_id}/messages", {"content": msg})
        except Exception as e:
            app.logger.warning(f"DM applicant failed: {e}")
    flash(f"Marked as {decision}.", "success")
    return redirect(url_for("form_responses_page", guild_id=guild_id, form_name=form_name))


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _int_or_none(val):
    try:
        return int(val) if val else None
    except ValueError:
        return None


def _safe_int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "5000"))
    debug = os.getenv("DASHBOARD_DEBUG", "false").lower() == "true"
    # bootstrap aux tables before serving
    try:
        with app.app_context():
            _ensure_streams_table()
    except Exception as e:
        print(f"WARN: stream table bootstrap: {e}")
    print(f"Dashboard running on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
