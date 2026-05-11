# Local development

## Prerequisites

- Node.js 20+
- Discord application with bot and Activities enabled
- OBS Studio 28+ for OBS WebSocket testing
- A tunneling tool for HTTPS Activity access

## Install

```bash
cp .env.example .env
npm install
npm run build
```

## Run

```bash
npm run dev
```

This runs:

```text
client: Vite on http://localhost:5173
server: Express/WebSocket/Bot on http://localhost:3001
```

## Tunnel

Option A: one tunnel to Vite, using Vite proxy for `/api` and `/ws`:

```bash
cloudflared tunnel --url http://localhost:5173
```

Option B: separate tunnels:

```bash
cloudflared tunnel --url http://localhost:5173
cloudflared tunnel --url http://localhost:3001
```

## Activity URL mappings

For Option A:

```text
/ → generated-client-tunnel.trycloudflare.com
```

For Option B:

```text
/    → generated-client-tunnel.trycloudflare.com
/api → generated-server-tunnel.trycloudflare.com
/ws  → generated-server-tunnel.trycloudflare.com
```

## Test without Discord Activity

The client has a local-dev fallback if `VITE_DISCORD_CLIENT_ID` is missing.

```bash
npm run dev
```

Open:

```text
http://localhost:5173
```

Then use the REST API or bot commands to mutate `local:default` / local Activity room state.

## Useful endpoints

```text
GET  /health
GET  /api/rooms
GET  /api/rooms/:roomId
POST /api/rooms/:roomId/play
POST /api/rooms/:roomId/pause
POST /api/rooms/:roomId/seek
POST /api/token
```
