# LOKI AI Agent Workflow

## Goal

Build LOKI THE SUN GOD as a Discord-native operator system with a bounded NPC, music engine, activity controller, Mythos evidence compiler, and safe external research loop.

## Users

- Server members who interact with music, quests, activities, and the NPC.
- Guild admins who can change Discord settings, memory settings, OAuth settings, and activity/event state.
- Operators who run local checks, desktop controls, Railway deployment, and Mythos packets.

## Autonomy Level

LOKI can suggest, summarize, score, queue, and draft. It cannot change Discord settings, post external recommendations, ingest private content, or apply code changes without the matching permission gate and audit receipt.

## Agent Lanes

- `public-diva-indexer`: keeps clean-room public Diva command and UX evidence current.
- `command-parity-mapper`: maps public command parity into original LOKI command surfaces.
- `music-engine-architect`: owns queue, Lavalink/Wavelink, song-request mirror, and DJ permission boundaries.
- `audio-mixer-eq`: owns equalizer presets, custom EQ payloads, and mixer dashboard controls.
- `npc-persona-guardian`: owns generated guild persona, redacted memory access, cooldowns, and prompt-injection checks.
- `activity-control-auditor`: owns scheduled events, Discord Activities where supported, and gamified portal quests.
- `codex-agi-adapter`: keeps NOO, quantum_roots, swarm_brain, and SLIME GOD outputs advisory and auditable.
- `security-privacy-verifier`: blocks secret leakage, private-channel ingestion, unsafe recommendations, and unauthorized mutation.
- `railway-deploy-verifier`: checks hosted web, worker, Postgres, OAuth callback, and Discord live gates.

## Runtime Workflow

1. Discord, portal, desktop, MCP, or ChatGPT App requests enter `loki_engine`.
2. `loki_engine` resolves command metadata, target guild, requesting user, and required permissions.
3. Read-only calls can use command catalog, music state, NPC memory summaries, Mythos packet summaries, or activity state.
4. Mutating calls require Discord admin/manage-guild/manage-event/DJ permission checks on the server side.
5. External research candidates are scored for source confidence, reason-for-fit, safety, and channel approval before posting.
6. Advisory Codex AGI outputs are stored with provenance and confidence, then verified before any operator-visible decision.
7. Every external action receives an audit receipt.

## Memory

- Public-channel Discord memory is redacted before storage.
- Private channels, deleted content, secrets, and opted-out users are excluded.
- Admins need export, delete, channel allowlist, crawl settings, and personality reset controls.
- MemPalace is used for local project memory and operator recovery, not for hidden Discord data retention.

## Tools

- Discord bot cogs for server commands and permission-aware interactions.
- Flask dashboard and desktop dashboard for operator controls.
- ChatGPT Apps MCP for read-first administration tools with explicit mutation gates.
- Wavelink/Lavalink for music sessions and EQ payloads.
- Research-source-indexing for source inventory, claims, gaps, and confidence.
- Mythos packets for evidence and verifier state.
- SuperAGI/Codex AGI adapters only through bounded advisory interfaces.

## Experiments

The self-research lab is disabled by default, blocked in production, and limited to `.loki_lab`. Candidate mutations must include score, rollback instructions, changed path list, and review path. The dry-run lab cannot hot-edit production code.

## Tests

- Unit tests for command registry, permissions, EQ mapping, NPC gating, memory redaction, and advisory adapters.
- Integration tests with Discord mocks for music, song requests, admin settings, activity events, and NPC responses.
- Playwright tests for portal login states, mixer UI, dashboard controls, mobile layout, and no text overlap.
- Desktop smoke tests for launch, config validation, logs, and control actions.
- Security tests for secrets, prompt injection, unauthorized admin actions, unsafe recommendations, and private-channel ingestion.
- Deployment checks for Railway web/worker, Vercel preview, health endpoints, Lavalink, and database migrations.

## Done Signal

A pass is complete when Mythos has no unresolved verifier findings, local checks pass, the safe preview or hosted target is validated, blockers are documented with owner and next action, and no raw subagent chatter is promoted into decisions.
