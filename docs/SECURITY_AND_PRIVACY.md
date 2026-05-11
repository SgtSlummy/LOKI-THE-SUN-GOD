# Security And Privacy

- Never commit `.env`, databases, logs, caches, generated executables, or Discord tokens.
- LOKI NPC uses redacted public-channel memory only by default.
- Raw Discord content is not direct fine-tuning data.
- Private channels, deleted messages, secrets, and opted-out users are excluded from memory.
- `LOKI_NPC_ALLOWED_CHANNEL_IDS` can restrict NPC listening, and `LOKI_NPC_MEMORY_OPT_OUT_USER_IDS` excludes users from public-channel memory.
- Relay skips open ticket channels, the configured ticket category, and `RELAY_SENSITIVE_CHANNEL_IDS` for live and backfill processing.
- Web recommendations require source URL, confidence, reason-for-fit, and safety status.
- Discord setting mutations require server-side administrator or manage-guild permission checks.
- Activity/event mutations require create-events, manage-events, manage-guild, or administrator permission depending on action.
- MCP write tools stay disabled unless `LOKI_MCP_ENABLE_WRITES=true`.
- Run `python scripts/secret_scan.py` before pushing a public branch.
