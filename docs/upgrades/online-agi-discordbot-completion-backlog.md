# LOKI Online AGI / Discord Bot / Music / LLM / Knowledge System Completion Backlog

Generated: 2026-05-15
Source baseline: `master` after Railway publication commit `82ecbe82718b233b9e3e4fabde89551c5d16d02d`.

## Product target

LOKI THE SUN GOD should operate as an online Discord-first AGI-style system with:

- hosted Discord bot worker;
- hosted dashboard/operator console;
- hosted Activity Bridge for shared media rooms;
- Lavalink/Wavelink music playback;
- bounded LLM/NPC behavior;
- privacy-preserving public memory and member summaries;
- Camelot-compatible knowledge records;
- Hermes/Mythos advisory upgrade loop;
- Railway production deployment and health verification;
- local/desktop/GPU worker extensions as optional operator-controlled surfaces.

## Current completion state

### Completed / online-ready

- Discord worker and dashboard are deployed on Railway production.
- Activity Bridge is deployed on Railway production as its own TypeScript service.
- GitHub CI is green for the published master commit.
- Discord acceptance probe verifies bot identity, guild reachability, permissions, command registration, dashboard health, and Activity Bridge health.
- Natural language Discord routing exists with admin-action policy gates.
- NPC memory stores redacted public messages with retention and user purge helpers.
- Dashboard NPC settings are persisted.
- LLM `/ask` and NPC provider paths support OpenAI-compatible configuration and safe missing-provider fallback.
- Music commands, Lavalink/Wavelink adapter, queue metadata, queue limits, loop/shuffle, mixer/EQ, and jukebox controls exist.
- MCP/operator read surfaces and Hermes/Mythos/Camelot advisory docs/contracts exist.
- Release gates cover pytest, ruff, secret scan, release check, Activity Bridge build/typecheck/tests, CI, Railway status, and health checks.

### Newly completed in this pass

- Camelot-compatible record persistence now exists for the P1 knowledge-management slice:
  - `loki_camelot_records` stores schema-shaped wing records with payload JSON.
  - `loki_memory.camelot_records` validates the checked-in Camelot schema contract without adding runtime dependencies.
  - Import/export helpers enforce required fields, enums, list shapes, score bounds, and no-extra-properties.
  - Member public-memory snapshots can be converted into Camelot `user` records using only redacted public snippets.
  - Tests cover validation, secret/email redaction, upsert/get/export/import, and member snapshot conversion.
- MCP read tools now expose safe knowledge-management previews:
  - `loki_search_public_memory` searches redacted public NPC memory without source URLs.
  - `loki_preview_memory_export` previews redacted member exports without audit rows or source URLs.
  - `loki_preview_memory_delete` reports delete counts/ranges without mutating rows.
  - `loki_export_camelot_records` exports read-only Camelot records through the MCP surface.
  - The MCP smoke test seeds memory/Camelot fixtures and verifies these read-only tools stay non-mutating.

### Previously completed

- NPC runtime now reads per-guild dashboard settings instead of only environment variables:
  - `loki_npc_settings.enabled` gates replies for the guild.
  - `loki_npc_settings.channel_allowlist` gates message handling for the guild.
  - environment variables remain fallback defaults when no DB row exists.
- `/npc reset` now clears persisted `persona_json` for the current guild.
- `/npc memory [member]` now exposes deterministic redacted public-memory snapshots
  through slash-command-only private responses; users can view their own memory
  and Manage Server operators can inspect other members.
- `/npc memory-export <member>` and `/npc memory-delete <member>` now give
  Manage Server operators private redacted export/delete actions with audit
  receipts in `loki_audit_receipts`.
- Deterministic no-LLM member memory helpers were added:
  - `recent_public_memory_for_user(...)`
  - `member_memory_snapshot(...)`
- Tests now cover dashboard-setting runtime enforcement, reset persistence, user-scoped memory snapshots, redaction, and bounds.
- Audio intake and codec guardrail policy now exists for the first P3 media slice:
  - `loki_music.audio_intake` classifies Lavalink, Spotify metadata, local files, Discord attachments, generated audio, DCA assets, and voice captures.
  - `loki_music.codec_policy` distinguishes Discord Audio DCA from DTS/DCA and defines the Discord-safe Opus voice target.
  - Tests cover every audio input kind and codec vocabulary guardrail.

## Remaining programming goals

### P0 — Human/live Discord acceptance boundary

Status: partially complete; cannot be truthfully automated by the bot token alone.

Remaining:
1. Configure `LOKI_ACCEPTANCE_VOICE_CHANNEL_ID` for a staging voice channel.
2. Run the Discord acceptance probe with voice channel IDs.
3. Use a real Discord user or separate test client to invoke slash commands.
4. Use a real listener/test client to confirm audible playback.

Acceptance:
- `/dashboard` responds in Discord with the hosted dashboard URL.
- `/play`, `/queue`, `/stop` work from a real user in the intended guild/channel.
- Lavalink audio is actually heard by a listener.

### P1 — NPC/member intelligence and knowledge management

Status: runtime foundation exists; member summary product surface is incomplete.

Next slices:
1. Add source-aware member profiles from public-memory snippets only. (partial: deterministic member snapshots can now be converted into Camelot `user` records.)
2. Add Camelot record import/export table or adapter matching `docs/schemas/camelot-wing.schema.json`. (complete: `loki_camelot_records` and `loki_memory.camelot_records`.)
3. Add MCP read tools for memory search/export/delete previews. (complete: read-only MCP tools expose redacted search, export/delete previews, and Camelot export.)
4. Add operator/dashboard views for source-aware member profiles and Camelot exports.

Acceptance:
- Member summaries are deterministic without LLM when no provider is configured.
- LLM summaries, when enabled, cite only redacted/public memory snippets.
- Private channels, opted-out users, deleted messages, secrets, and tokens are excluded.
- Admin delete/export actions create audit receipts.

### P2 — Activity Bridge Discord integration

Status: hosted bridge exists; Discord cog integration is partial.

Next slices:
1. Wire `cogs/loki_activities.py` to `loki_activity_bridge.client.ActivityBridgeClient`.
2. Add Discord commands for bridge health, room status, queue, set media, pause/play/next.
3. Keep mutating controls behind Manage Guild / Manage Events / Create Events permission gates.
4. Add tests for missing bridge URL, wrong token, bridge health, room snapshots, and control failures.
5. Add room heartbeat/stale cleanup and persistence adapter contract.

Acceptance:
- Discord admins can inspect and manage Activity Bridge rooms from Discord.
- Non-admin users can only use safe read/participant actions.
- Activity Bridge does not lose safety controls when side controls or stream start/stop are disabled.

### P3 — Music/media high-fidelity package

Status: Lavalink/Wavelink music is active; first intake/codec policy guardrails now exist; optional capability probes and DCA asset tooling remain.

Next slices:
1. Add `loki_music/audio_capabilities.py` and tests for optional FFmpeg/DCA availability.
2. Add `loki_music/ffmpeg_tools.py` as optional probe/transcode wrapper.
3. Add optional DCA asset helpers for pre-encoded short alert/soundboard clips.

Acceptance:
- Lavalink remains the primary production streaming path.
- Optional FFmpeg/DCA tools do not block Railway worker startup when absent.
- No client-patcher or Discord ToS-risk experiment is shipped as bot runtime code.

### P4 — Online crawler/recommendation/posting system

Status: policy and research-source schema exist; autonomous crawler/poster remains blocked.

Next slices:
1. Define crawler allowlist/denylist and safety policy in DB and dashboard.
2. Add source ingestion with confidence, reason-for-fit, and safety status.
3. Add recommendation queue with operator approval required before Discord posting.
4. Add audit receipts for every source and proposed post.
5. Add dry-run crawler tests with local fixtures only.

Acceptance:
- No autonomous external post occurs without explicit operator approval.
- Every recommendation has source URL, confidence, safety status, and target-channel approval.

### P5 — Hermes/Mythos/Camelot runtime loop

Status: advisory manifests, schemas, and bridge utilities exist; live loop is not fully wired.

Next slices:
1. Add a dashboard/operator endpoint to compile a Mythos packet from current status.
2. Add Camelot-compatible record persistence and export/import validation.
3. Add a safe Hermes prompt builder with transcript redaction and local-only execution policy.
4. Add upgrade proposal queue with grading and rollback metadata.
5. Add MCP tools for read-only Mythos/Camelot status.

Acceptance:
- Hermes/Mythos outputs stay advisory until operator approval.
- Every proposal has tests, rollback path, risk score, and evidence links.

### P6 — Desktop/local GPU workers

Status: desktop artifacts and optional GPU worker contracts exist; manual Windows smoke remains.

Next slices:
1. Run PyInstaller/Windows desktop smoke on the host.
2. Add a local GPU worker protocol and health check.
3. Route optional model jobs through the operator dashboard with explicit start/stop controls.
4. Add no-secret config validation.

Acceptance:
- Desktop starts without secrets in logs.
- GPU worker absence never breaks hosted Railway services.

## Release gates for every slice

Run from repo root unless noted:

```bash
python -m pytest -q
python -m ruff check .
python scripts/release_check.py
python scripts/secret_scan.py
git diff --check
```

Run from `services/activity-bridge` when bridge files change:

```bash
npm run build
npm run typecheck
npm run test:rooms
```

Hosted publication gates:

- GitHub CI success on `master`.
- Railway `dashboard`, `worker`, and `activity-bridge` services `SUCCESS` and `stopped=false`.
- Dashboard `/healthz` HTTP 200 with `ok:true` and `database_ok:true`.
- Activity Bridge `/healthz` HTTP 200 with `ok:true`.
- Discord acceptance probe `ok:true`, with human/live voice boundary reported separately.

## Rollback policy

- Every programming slice must be one focused commit.
- For Railway changes, keep previous deployment IDs in the final report.
- For DB changes, add migration/backfill tests and backup/restore notes before publish.
- For autonomous posting/crawling, ship dry-run first and require operator approval before live posting.
