# Security and safety notes

## Secrets

Never put these in client code:

```text
DISCORD_BOT_TOKEN
DISCORD_CLIENT_SECRET
TWITCH_ACCESS_TOKEN
OBS_WEBSOCKET_PASSWORD
stream keys
```

Only expose:

```text
VITE_DISCORD_CLIENT_ID
VITE_SERVER_ORIGIN
VITE_WS_ORIGIN
```

## Bot and Activity trust boundaries

The Activity UI is not trusted. A user can manipulate frontend JavaScript. All real control decisions belong on the backend.

Backend checks should include:

- authenticated Discord user identity,
- guild/channel/Activity instance,
- host or moderator authorization,
- locked-room state,
- URL validation,
- rate limiting.

## OBS control

Keep stream start/stop disabled by default:

```env
ALLOW_STREAM_START_STOP=false
```

Enable only after adding confirmation prompts and audit logs.

## Selfbot/user-token avoidance

This project uses an official bot token and official application command interactions. It does not use selfbot behavior or user tokens.

## Media source validation

The starter only accepts HTTP(S) URLs. Production should also validate:

- domain allowlist,
- content type,
- file size,
- duration,
- copyright/permission rules for public streams,
- malware/phishing risk for arbitrary URLs.
