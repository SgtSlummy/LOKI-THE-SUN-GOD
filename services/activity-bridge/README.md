# Discord Activity Stream Control Starter

This repository is a Codex-ready starter kit for a Discord Activity that is controlled by the same Discord application's integrated bot.

It is designed around this flow:

```text
Discord slash command / button / Activity control
        ↓
Backend permission + room-state controller
        ↓
WebSocket broadcast to Activity clients
        ↓
Optional OBS WebSocket command
        ↓
OBS-composited output
        ├── Twitch RTMP stream
        └── Discord Go Live / shared OBS projector window
```

## What this starter includes

- Discord Activity frontend using `@discord/embedded-app-sdk`.
- Integrated Discord bot using `discord.js` application commands.
- Express backend with WebSocket room sync.
- Shared TypeScript types for room state and control messages.
- OBS WebSocket adapter for scene switching, source toggling, text overlays, and optional stream start/stop.
- Twitch API placeholder service for stream metadata updates.
- Documentation for Discord setup, OBS/Twitch setup, testing, and Codex handoff.

## What this starter does not do

- It does not make the bot directly screenshare or Go Live in Discord.
- It does not capture Discord Go Live video through Discord APIs.
- It does not bypass Discord Activity networking limits.

The intended production design is to use OBS or another encoder/mixer for actual video composition and Twitch output.

## Quick start

```bash
cp .env.example .env
npm install
npm run build
npm run register:commands
npm run dev
```

Then configure the Discord Developer Portal URL mappings for your Activity and open the Activity from Discord.

## First working path

1. Create a Discord application.
2. Add a bot to that application.
3. Enable Activities.
4. Add `.env` values.
5. Register commands.
6. Run the server and client locally.
7. Tunnel the client/server for Discord Activity URL mappings.
8. Launch the Activity in a test server.
9. Run `/watch set url:<video-url>`.
10. Run `/watch play`.
11. Open OBS and point a browser source or window capture at the Activity.
12. Stream from OBS to Twitch and share the OBS projector window in Discord Go Live.

## Repository map

```text
client/   Activity frontend
server/   Bot, backend API, WebSocket server, OBS/Twitch services
shared/   Shared TypeScript types and helpers
docs/     Architecture, setup, testing, and handoff notes
scripts/  Utility scripts
```

## Core commands

```text
/watch status
/watch set url:<url>
/watch play
/watch pause
/watch seek seconds:<number>
/watch queue url:<url>
/watch next
/watch scene name:<scene>
/watch overlay name:<overlay> visible:<true|false>
/watch title text:<text>
/watch end
```

## Codex entry points

Read these first:

1. `CODEX_PROMPT.md`
2. `AGENTS.md`
3. `docs/01-architecture.md`
4. `docs/02-discord-setup.md`
5. `docs/03-obs-twitch-discord.md`

