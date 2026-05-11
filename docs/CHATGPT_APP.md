# ChatGPT App MCP Surface

LOKI exposes a ChatGPT-readable MCP surface through `loki_mcp`.

## Read Tools

- `loki_list_guilds`
- `loki_get_guild_config`
- `loki_search_commands`
- `loki_get_music_state`
- `loki_get_npc_summary`
- `loki_get_activity_state`
- `loki_get_mythos_summary`

## Widget Resource

- `loki://chatgpt/widget/v1`
- MIME: `text/html;profile=mcp-app`

The app follows the decoupled data/render pattern: read tools return structured data, and the widget is a separate resource. Mutating tools remain disabled unless explicitly enabled and still require server-side authorization.
