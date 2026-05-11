# Architecture

## System diagram

```text
                                 ┌──────────────────────┐
                                 │ Discord Application   │
                                 │ app id / bot / OAuth  │
                                 └──────────┬───────────┘
                                            │
                   ┌────────────────────────┼────────────────────────┐
                   │                        │                        │
          ┌────────▼────────┐      ┌────────▼────────┐      ┌────────▼────────┐
          │ Discord Bot      │      │ Discord Activity │      │ Discord Client   │
          │ slash commands   │      │ iframe web app   │      │ app launcher     │
          │ buttons          │      │ SDK auth/context │      │ Go Live/manual   │
          └────────┬────────┘      └────────┬────────┘      └─────────────────┘
                   │                        │
                   │ interactions           │ WebSocket + API
                   │                        │
                   └────────────┬───────────┘
                                │
                       ┌────────▼─────────┐
                       │ Backend Server    │
                       │ room state        │
                       │ permissions       │
                       │ WebSocket sync    │
                       │ service adapters  │
                       └─────┬───────┬────┘
                             │       │
              OBS WebSocket  │       │ Twitch Helix API metadata
                             │       │
                       ┌─────▼───────▼────┐
                       │ OBS Studio        │
                       │ scenes/sources    │
                       │ overlays/mixer    │
                       │ RTMP output       │
                       └─────┬────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
          ┌──────▼──────┐        ┌───────▼────────┐
          │ Twitch RTMP  │        │ Discord Go Live │
          │ live stream  │        │ shared OBS view │
          └─────────────┘        └────────────────┘
```

## Data flow

### Bot command to Activity playback

```text
/watch play
   ↓
Discord interaction payload
   ↓
server/src/bot.ts
   ↓
server/src/rooms.ts mutates RoomState
   ↓
server/src/websocket.ts broadcasts PLAY
   ↓
client/src/player.ts applies state to <video>
```

### Activity button to backend

```text
Activity Play button
   ↓
client/src/socket.ts sends CONTROL_PLAY
   ↓
server/src/websocket.ts checks ALLOW_ACTIVITY_SIDE_CONTROLS
   ↓
server/src/activitySessions.ts verifies the Discord OAuth session token
   ↓
server/src/rooms.ts mutates RoomState
   ↓
WebSocket broadcast to all joined clients
```

### Bot command to OBS

```text
/watch scene name:Live
   ↓
server/src/bot.ts
   ↓
server/src/services/obs.ts
   ↓
OBS WebSocket SetCurrentProgramScene
   ↓
OBS program output updates
   ↓
Twitch and Discord-visible OBS output both change
```

## Room identity

The default room key is:

```ts
roomId = `${guildId}:${channelId}`
```

If guild/channel context is unavailable, the Activity falls back to:

```ts
roomId = `activity:${instanceId}`
```

This lets a voice/channel Activity session map cleanly to the same control channel used by the bot.

## Source of truth

The backend owns state. The Activity frontend never becomes the trusted state owner.

```text
Correct:
Activity UI → Backend → RoomState → Broadcast → All clients

Incorrect:
Activity UI → Local video only
```

## Video and stream design

Use OBS for actual video composition.

```text
OBS scene
├── media/game/window capture
├── Activity browser source or Activity window capture
├── Twitch chat overlay
├── bot-controlled text overlays
└── Discord window/projector capture if needed
```

Then either:

- stream OBS output to Twitch, and
- share the OBS projector/window in Discord Go Live.
