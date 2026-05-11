# Codex handoff

## Current state

This repository is a TypeScript monorepo containing a starter Discord Activity, bot/backend, shared state module, OBS service, Twitch service, and docs.

It is intended to be imported into Codex and iterated into a working production app.

## Recommended first Codex task

```text
Run npm install, npm run typecheck, and npm run build. Fix any TypeScript or dependency issues. Preserve the architecture: Activity frontend, bot/backend, shared state, OBS service, Twitch service.
```

## Recommended second task

```text
Complete Discord Activity authentication. Ensure /api/token correctly exchanges the Discord authorization code, and ensure the frontend calls discordSdk.commands.authenticate successfully. Add server-side validation for Activity instance and user identity.
```

## Recommended third task

```text
Add tests for RoomManager. Cover setVideo, play, pause, seek, queue, next, lock, host, OBS status, Twitch status, and end.
```

## Recommended fourth task

```text
Add Redis persistence for room state and WebSocket cleanup with heartbeat timeout.
```

## Important files

```text
shared/src/index.ts
server/src/rooms.ts
server/src/websocket.ts
server/src/bot.ts
server/src/services/obs.ts
server/src/services/twitch.ts
client/src/main.ts
client/src/discord.ts
client/src/player.ts
```

## Expected behavior

- If OBS is not running, the app still works for Activity playback control.
- If Twitch credentials are missing, the app still works and skips Twitch metadata changes.
- If Discord bot token is missing, the HTTP/WebSocket server still starts for local frontend testing.
- Activity clients join rooms and receive state through WebSockets.
