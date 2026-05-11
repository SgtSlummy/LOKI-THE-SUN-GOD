# API Surface

## Dashboard

Base app: [dashboard_app.py](/C:/LOKI%20THE%20SUN%20GOD/dashboard_app.py)

### Public routes

- `GET /`
- `GET /healthz`
- `GET /login`
- `GET /callback`
- `GET /logout`
- `GET /dev/connect-loki`

### Authenticated guild routes

- `GET /guilds`
- `GET /guild/<guild_id>`
- `POST /guild/<guild_id>/save`
- `GET /guild/<guild_id>/commands`
- `GET /guild/<guild_id>/embed`
- `GET /guild/<guild_id>/forms`
- `POST /guild/<guild_id>/forms/create`
- `GET /guild/<guild_id>/forms/<form_name>/edit`
- `POST /guild/<guild_id>/forms/<form_name>/save`
- `GET /guild/<guild_id>/forms/<form_name>/responses`
- `POST /guild/<guild_id>/forms/<form_name>/responses/<resp_id>/decide`
- `GET /guild/<guild_id>/events`
- `GET /guild/<guild_id>/streams`
- `POST /guild/<guild_id>/streams/add`
- `POST /guild/<guild_id>/streams/delete`
- `GET /guild/<guild_id>/tickets`
- `POST /guild/<guild_id>/tickets/save`
- `GET /guild/<guild_id>/audit`

### Admin post protection

Dashboard `POST` routes require the session CSRF token.

- HTML forms send `csrf_token`
- JSON routes send `X-CSRF-Token`

### Health response

`GET /healthz`

```json
{
  "ok": true,
  "database_ok": true,
  "oauth_ready": false,
  "missing_oauth": ["DISCORD_CLIENT_ID"],
  "local_bridge_available": true,
  "database_backend": "sqlite",
  "database": "C:/LOKI THE SUN GOD/data/bot.db",
  "db_path": "C:/LOKI THE SUN GOD/data/bot.db"
}
```

## Desktop control center

Base app: [desktop_app.py](/C:/LOKI%20THE%20SUN%20GOD/desktop_app.py)

### Service APIs

- `GET /api/status`
- `POST /api/<service_id>/start`
- `POST /api/<service_id>/stop`
- `POST /api/<service_id>/restart`
- `GET /api/<service_id>/stream`

### LOKI THE SUN GOD operator APIs

- `GET /api/loki/guilds`
- `GET /api/loki/<guild_id>/config`
- `POST /api/loki/<guild_id>/config`
- `DELETE /api/loki/<guild_id>/sticky/<channel_id>`
- `GET /api/loki/<guild_id>/channels`
- `GET /api/loki/command-library`
- `GET /api/loki/options`
- `GET /api/loki/ai-docs`
- `GET /api/loki/ollama`
- `GET /api/diagnostics`

These desktop operator endpoints now share their read logic with the offline MCP surface through [utils/operator_surface.py](/C:/LOKI%20THE%20SUN%20GOD/utils/operator_surface.py).

## Offline MCP

Entrypoint: `python -m loki_mcp`

See [docs/MCP.md](/C:/LOKI%20THE%20SUN%20GOD/docs/MCP.md) for client registration details.

### Resources

- `loki://overview`
- `loki://diagnostics`
- `loki://commands`
- `loki://options`
- `loki://ai-docs`
- `loki://ollama-status`
- `loki://guild/<guild_id>/config`
- `loki://guild/<guild_id>/channels`

### Tools

- `loki_list_guilds`
- `loki_get_guild_config`
- `loki_get_channel_clusters`
- `loki_search_commands`
- `loki_search_ai_docs`
- `loki_get_diagnostics`
- `loki_get_ollama_status`

Optional write tools are only registered when `LOKI_MCP_ENABLE_WRITES=true`.

## Bot runtime

The Discord bot itself does not expose an HTTP API. Its release-facing verification path is:

- [scripts/release_check.py](/C:/LOKI%20THE%20SUN%20GOD/scripts/release_check.py)
- [scripts/smoke_test_local.ps1](/C:/LOKI%20THE%20SUN%20GOD/scripts/smoke_test_local.ps1)

The shared command and slash metadata used by both the bot and the operator surfaces is generated from:

- [utils/command_catalog.py](/C:/LOKI%20THE%20SUN%20GOD/utils/command_catalog.py)
- [utils/command_descriptions.py](/C:/LOKI%20THE%20SUN%20GOD/utils/command_descriptions.py)
