# Roadmap

## Phase 1 — MVP

- [x] Shared RoomState types.
- [x] WebSocket room sync.
- [x] Activity player UI.
- [x] Bot slash commands.
- [x] Bot control buttons.
- [x] OBS adapter scaffold.
- [x] Twitch metadata scaffold.
- [ ] End-to-end Discord OAuth validation.
- [ ] Activity Instance API verification.

## Phase 2 — Production state

- [ ] Redis for live room state.
- [ ] Postgres for saved rooms, user preferences, and queue history.
- [ ] Room TTL cleanup.
- [ ] WebSocket heartbeat and reconnect.
- [ ] Durable queue and playlist support.

## Phase 3 — Permissions

- [ ] Role allowlist.
- [ ] Host transfer flow.
- [ ] Locked-room moderation UI.
- [ ] Per-command permission checks.
- [ ] Audit log channel.

## Phase 4 — OBS stream studio

- [ ] Scene preset editor.
- [ ] Overlay source registry.
- [ ] Now-playing text source sync.
- [ ] Browser overlay route for OBS.
- [ ] Start/stop streaming confirmation flow.
- [ ] Recording controls.

## Phase 5 — Twitch integration

- [ ] OAuth flow for Twitch tokens.
- [ ] Stream status polling.
- [ ] Title/category updates.
- [ ] Chat event integration.
- [ ] Twitch chat overlay page.

## Phase 6 — Advanced Activity

- [ ] Host-only controls inside Activity.
- [ ] Viewer queue voting.
- [ ] Activity-side stream status panel.
- [ ] Embedded Twitch preview.
- [ ] Low-latency stream preview from OBS/CDN.
