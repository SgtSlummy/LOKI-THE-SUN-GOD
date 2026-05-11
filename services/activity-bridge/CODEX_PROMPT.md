# Codex prompt

You are working in a TypeScript monorepo named `discord-activity-stream-control`.

The product is a Discord Activity controlled by the same Discord application's integrated bot. The Activity is the embedded UI/player/control room. The bot exposes slash commands and buttons. The backend owns room state and broadcasts changes over WebSockets. OBS is the video mixer/encoder for Twitch output and for Discord-visible output through Go Live/window share.

## Immediate objective

Make the starter runnable end-to-end in development:

1. Install dependencies.
2. Ensure `npm run build` passes.
3. Implement any missing TypeScript details.
4. Register Discord slash commands from `server/src/register-commands.ts`.
5. Verify WebSocket sync between Activity client and backend.
6. Verify `/watch set`, `/watch play`, `/watch pause`, `/watch seek`, `/watch status`, and `/watch scene` handlers update state.
7. Keep OBS/Twitch integrations optional when credentials are absent.

## Important design facts

- The Discord Activity is a web app in an iframe and communicates with Discord using the Embedded App SDK.
- Discord Activity networking is proxied and supports WebSockets; WebRTC is not supported for Activity networking.
- Twitch broadcast ingest expects encoded video from a tool such as OBS over RTMP.
- OBS can be controlled externally through its built-in WebSocket endpoint.

## Never do this

- Do not use selfbots or user tokens.
- Do not try to make a normal Discord bot account stream video directly.
- Do not put stream keys or bot tokens into client code.
- Do not use the Activity frontend as the trusted authority for room control.

## Useful files

- `shared/src/index.ts` — shared types and room helpers.
- `server/src/rooms.ts` — room state controller.
- `server/src/websocket.ts` — Activity WebSocket sync.
- `server/src/bot.ts` — Discord bot client and interaction routing.
- `server/src/services/obs.ts` — OBS control adapter.
- `server/src/services/twitch.ts` — Twitch API placeholder.
- `client/src/main.ts` — Activity UI entry point.
- `docs/` — setup and architecture notes.
