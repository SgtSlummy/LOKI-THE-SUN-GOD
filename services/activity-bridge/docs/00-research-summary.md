# Research summary

## Verified platform facts

1. Discord Activities are web apps hosted in an iframe that communicate with Discord clients using the Embedded App SDK.
   - Source: https://docs.discord.com/developers/activities/overview

2. Discord's Activity networking routes traffic through Discord's proxy. The current supported real-time transport is WebSockets. WebRTC is not supported for Activity networking.
   - Source: https://docs.discord.com/developers/activities/development-guides/networking

3. Discord application commands are the primary native command surface for apps. Slash commands, message commands, user commands, and Entry Point commands can be used as application entry points.
   - Source: https://docs.discord.com/developers/interactions/application-commands
   - Source: https://docs.discord.com/developers/platform/interactions

4. Twitch broadcast ingest expects a video signal from a broadcast tool/encoder over RTMP.
   - Source: https://dev.twitch.tv/docs/video-broadcast/

5. OBS Studio can be externally controlled through its built-in WebSocket endpoint, allowing applications/scripts to interact with OBS.
   - Source: https://obsproject.com/kb/developer-guide
   - Source: https://github.com/obsproject/obs-websocket

## Resulting design decision

Use this system split:

```text
Discord Activity = embedded UI / player / control room
Discord Bot      = slash commands / buttons / permission-aware control surface
Backend          = source of truth / WebSocket sync / service adapter layer
OBS              = video mixer / encoder / output source
Twitch           = RTMP destination
Discord Go Live  = manual human share of OBS projector/window or shared source
```

The bot and Activity should control OBS and shared room state. They should not attempt to become Discord's direct video broadcasting system.
