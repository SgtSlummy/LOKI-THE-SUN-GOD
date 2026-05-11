# OBS, Twitch, and Discord combined stream plan

## Clean answer

The Activity can control a stream system, but OBS should do the actual video combining and encoding.

```text
Discord Activity + Bot
        ↓
Backend control state
        ↓
OBS WebSocket
        ↓
OBS scene/output
        ├── Twitch via RTMP
        └── Discord Go Live via shared OBS projector/window
```

## OBS scene setup

Create these example scenes:

```text
Live
BRB
Activity
Starting Soon
Ending
```

Example `Live` scene:

```text
Live
├── Game Capture / Window Capture / Media Source
├── Browser Source: Activity UI or overlay page
├── Text Source: Now Playing
├── Text Source: Stream Title
├── Twitch Chat Overlay
└── Optional Discord window capture
```

## OBS WebSocket

OBS Studio 28+ includes obs-websocket by default. Enable it in OBS:

```text
Tools → WebSocket Server Settings
```

Set `.env`:

```env
OBS_WEBSOCKET_URL=ws://127.0.0.1:4455
OBS_WEBSOCKET_PASSWORD=your_password
ALLOW_STREAM_START_STOP=false
```

Keep `ALLOW_STREAM_START_STOP=false` while testing. Scene/source controls can still work without allowing the bot to start or stop streams.

## Twitch setup

OBS sends video to Twitch using the Twitch stream destination. Twitch ingest uses RTMP from a broadcast encoder.

Recommended flow:

```text
OBS Settings → Stream → Service: Twitch
```

The backend's Twitch service is for metadata/status, not for video encoding.

Use it for:

```text
/watch title text:"New stream title"
```

Production credentials needed:

```env
TWITCH_CLIENT_ID=...
TWITCH_ACCESS_TOKEN=...
TWITCH_BROADCASTER_ID=...
```

## Discord-visible output

For Discord, share the OBS output manually:

1. In OBS, right-click the program canvas.
2. Open windowed projector.
3. In Discord, join voice.
4. Use Go Live / screen share.
5. Select the OBS projector window.

This lets Discord viewers see the same combined output as Twitch viewers.

## Combining Discord content into Twitch

To include Discord-visible content in Twitch:

```text
Discord window / Activity / chat / overlay
        ↓
OBS window or browser capture
        ↓
OBS mixed scene
        ↓
Twitch RTMP output
```

Do not rely on a Discord API capture of Go Live video. Treat Discord Go Live as a viewer-facing/manual share surface, not an ingest source.

## Bot commands tied to OBS

```text
/watch scene name:Live
/watch scene name:BRB
/watch overlay scene:Live source:"Now Playing" visible:true
/watch title text:"New Title" obs_source:"Stream Title"
/watch stream-start
/watch stream-stop
```

`stream-start` and `stream-stop` require:

```env
ALLOW_STREAM_START_STOP=true
```

