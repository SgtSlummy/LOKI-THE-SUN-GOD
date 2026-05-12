# LOKI THE SUN GOD Implementation Notes

LOKI is rebuilt from the legacy Discord bot base as a standalone Discord bot, dashboard, desktop surface, MCP server, and ChatGPT Apps bridge.

## Public Diva Parity

The Diva work is clean-room public parity. The implementation uses public pages and permitted observed behavior to shape command names and UX, then implements original LOKI code. The public audio filter command family is intentionally excluded from v1; LOKI exposes equalizer presets and a mixer instead.

## Core Modules

- `loki_engine`: shared permission decisions and audit records for bot, dashboard, MCP, ChatGPT app, and background agents.
- `loki_music`: music session, mixer state, and Lavalink-compatible equalizer preset payloads.
- `loki_music.wavelink_backend`: Wavelink/Lavalink v4 runtime adapter for node connection, voice player creation, search resolution, queueing, playback controls, volume, EQ filters, and track-end advancement.
- `loki_npc`: generated Discord NPC persona, redaction, and OpenAI Responses API payload construction with `store=false`.
- `loki_memory`: bounded Codex AGI adapter registry for NOO/Noophyte, Quantum Roots, Swarm Brain, CosmicOS, OpenMythos, SLIME GOD, Camelot, and discovered Codex AGI projects.
- `loki_research`: public Diva catalog, recommendation scaffolding, V4-V7 packet compiler, V8 Hermes integration manifest, hard-coded bot assembly plan, final product blueprint, complete package manifest, and package readiness report.
- `loki_research.experiments`: dry-run-only self-research and mutation safety contracts for future iteration labs.
- `loki_mcp`: local/ChatGPT-readable MCP tools and resources.

## Guardrails

- Raw Discord messages are not direct training data.
- Private channels, deleted content, secrets, and opted-out users are excluded from memory.
- Public-channel memory is redacted, expires after the default retention window, and supports per-user purge.
- NPC listening can be narrowed with `LOKI_NPC_ALLOWED_CHANNEL_IDS`; user memory opt-out uses `LOKI_NPC_MEMORY_OPT_OUT_USER_IDS`.
- NPC replies can be public, but Discord settings changes require server-side admin/manage-guild checks.
- Natural-language Discord UX is the default: `bot.py` skips slash command sync unless `LOKI_NATURAL_LANGUAGE_ONLY=false` and `LOKI_ENABLE_SLASH_SYNC=true` are both set.
- User rights start with no extra search/change privileges until an admin grants them; admin-level changes remain role locked.
- Activity changes require Discord event permissions or admin privileges.
- Codex AGI adapters are advisory and must produce auditable receipts before external actions.
