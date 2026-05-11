# Activity Stream Bridge

LOKI uses `services/activity-bridge` as a separate TypeScript bridge service for Discord Activity room state, WebSocket playback sync, OBS controls, and Twitch metadata. LOKI Python remains the only production Discord bot command owner.

## Local Services

Start the bridge separately from the Python dashboard and worker:

```powershell
cd .\services\activity-bridge
npm install
npm run build
npm run start
```

Set the LOKI dashboard env:

```text
ACTIVITY_BRIDGE_URL=http://127.0.0.1:3001
ACTIVITY_BRIDGE_TOKEN=shared-local-token
ACTIVITY_CLIENT_PUBLIC_URL=http://127.0.0.1:5173
```

Set the bridge env:

```text
ACTIVITY_BRIDGE_TOKEN=shared-local-token
ENABLE_BRIDGE_DISCORD_BOT=false
ALLOW_ACTIVITY_SIDE_CONTROLS=false
ALLOW_STREAM_START_STOP=false
```

## Production Ownership

- LOKI Python owns Discord commands and dashboard permission gates.
- The bridge owns room state, Activity WebSocket sync, OBS adapter calls, and Twitch metadata calls.
- The bridge Discord gateway remains disabled unless a future migration explicitly moves command ownership.
- Room APIs fail closed when `ACTIVITY_BRIDGE_TOKEN` is missing. The dashboard and bridge must share the same server-side token.
- Activity-side WebSocket controls remain disabled by default. When enabled, control messages must carry the short-lived session token issued by the Discord Activity OAuth exchange.
- Stream start/stop stays disabled until `ALLOW_STREAM_START_STOP=true` and the dashboard confirmation path is reviewed.

## Dashboard First Flow

1. Open the LOKI dashboard Activity Control page.
2. Confirm bridge status shows online.
3. Create or select a room.
4. Set media, queue items, and use play/pause/next controls.
5. Refresh OBS/Twitch status or switch OBS scenes.
6. Launch the Discord Activity client after the room state path is verified.

## Railway Shape

Create a third Railway service rooted at `services/activity-bridge`.

- LOKI web: `gunicorn dashboard_app:app --bind 0.0.0.0:$PORT`
- LOKI worker: `python -m bot`
- Activity bridge: `npm run start` after `npm run build`

Host the Discord Activity client as a separate static site from
`services/activity-bridge/client/dist`. Its public build env is
`VITE_DISCORD_CLIENT_ID`, `VITE_SERVER_ORIGIN`, and `VITE_WS_ORIGIN`; never put
bot tokens, bridge tokens, client secrets, Twitch tokens, or OBS passwords in
`VITE_*` variables.

Use shared Railway variables for `ACTIVITY_BRIDGE_URL`, `ACTIVITY_BRIDGE_TOKEN`,
`ACTIVITY_CLIENT_PUBLIC_URL`, `PUBLIC_SERVER_ORIGIN`, `PUBLIC_CLIENT_ORIGIN`,
Discord OAuth credentials, OBS settings, and Twitch metadata credentials.
