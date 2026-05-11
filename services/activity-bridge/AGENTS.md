# Agent instructions for Codex

## Goal

Continue development of a Discord Activity that is controlled by its integrated Discord bot and can coordinate OBS/Twitch stream output.

## Constraints

- Keep the Discord Activity as a sandboxed web app UI.
- Keep bot commands and Activity controls routed through the backend.
- Keep the backend as the source of truth for room state.
- Use WebSockets for Activity-client synchronization.
- Use OBS as the stream mixer/encoder for Twitch and Discord-visible output.
- Do not implement user-token/selfbot behavior.
- Do not claim that a Discord bot can directly Go Live or screenshare through a normal bot token.

## Prioritized next tasks

1. Finish Discord OAuth token exchange and Activity authentication.
2. Add robust permission checks for host/mod/admin control.
3. Add durable persistence with Redis/Postgres.
4. Add OBS source management for browser sources and overlays.
5. Add Twitch channel metadata updates and stream status fetch.
6. Add multi-room cleanup and heartbeat timeout behavior.
7. Add unit tests for room state reducers.
8. Add integration tests for WebSocket and command handlers.

## Code style

- TypeScript only.
- Prefer small pure functions in `shared/` and `server/src/rooms.ts`.
- Keep external service adapters isolated in `server/src/services/`.
- Return structured errors from API routes.
- Avoid hard-coded guild/channel IDs.
