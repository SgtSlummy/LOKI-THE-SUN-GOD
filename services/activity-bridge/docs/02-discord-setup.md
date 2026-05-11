# Discord setup

## 1. Create the application

1. Open the Discord Developer Portal.
2. Create a new application.
3. Save the application/client ID.
4. Add a bot user.
5. Copy the bot token into `.env` as `DISCORD_BOT_TOKEN`.
6. Copy OAuth2 client credentials into `.env`.

## 2. Enable Activities

1. Open the application settings.
2. Enable Activities.
3. Configure Activity URL mappings.
4. During development, use a tunnel such as Cloudflare Tunnel, ngrok, or another HTTPS tunnel.

Example mapping pattern:

```text
/       → activity-client-tunnel.example.com
/api    → activity-server-tunnel.example.com
/ws     → activity-server-tunnel.example.com
```

When using Vite proxy locally, mapping `/` to the Vite tunnel may be enough because Vite proxies `/api` and `/ws` to the backend.

## 3. Install bot

Use OAuth2 installation with bot/application command scopes.

Common scopes:

```text
bot
applications.commands
```

Development permissions can start with server admin permissions, then narrow later.

## 4. Register commands

Set these variables:

```env
DISCORD_APPLICATION_ID=...
DISCORD_BOT_TOKEN=...
DISCORD_DEV_GUILD_ID=...
```

Then run:

```bash
npm run register:commands
```

If `DISCORD_DEV_GUILD_ID` is set, commands are registered only in that guild for faster development.

## 5. Launch the Activity

Use the Discord App Launcher or Entry Point command for the Activity.

The Activity client does:

```text
DiscordSDK(clientId)
await discordSdk.ready()
authorize/authenticate if configured
read guildId/channelId/instanceId
connect to backend WebSocket
join room
```

## 6. Run control commands

```text
/watch status
/watch set url:https://example.com/video.mp4
/watch play
/watch pause
/watch seek seconds:90
/watch queue url:https://example.com/next.mp4
/watch next
/watch scene name:Live
/watch overlay scene:Live source:Now Playing visible:true
/watch title text:"Live Watch Room"
```

## 7. Permission model

Current starter behavior:

- unlocked room: bot controls and Activity controls are accepted.
- locked room: only host or server users with channel/server management permissions can control through the bot.

Recommended production work:

- Verify Activity user identity.
- Verify Activity instance.
- Check role allowlists.
- Store host/mod control state in the database.
