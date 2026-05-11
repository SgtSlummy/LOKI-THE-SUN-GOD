# Test plan

## Build tests

```bash
npm install
npm run typecheck
npm run build
```

## Discord command tests

- [ ] Commands register in dev guild.
- [ ] `/watch status` responds.
- [ ] `/watch set url:<url>` updates backend room state.
- [ ] `/watch play` broadcasts to Activity client.
- [ ] `/watch pause` broadcasts to Activity client.
- [ ] `/watch seek seconds:<n>` updates Activity playback time.
- [ ] `/watch queue` adds queue item.
- [ ] `/watch next` loads queue item.
- [ ] `/watch lock enabled:true` restricts bot controls.
- [ ] `/watch scene name:<scene>` switches OBS scene when OBS is connected.
- [ ] `/watch overlay` toggles an OBS source.
- [ ] `/watch title` updates Twitch metadata when credentials are present.

## Activity tests

- [ ] Activity launches inside Discord.
- [ ] `discordSdk.ready()` completes.
- [ ] Activity receives `guildId`, `channelId`, or `instanceId`.
- [ ] Activity connects to `/ws`.
- [ ] Activity sends `JOIN_ROOM`.
- [ ] Activity receives `ROOM_STATE`.
- [ ] Activity video updates when `/watch set` runs.
- [ ] Two Activity clients stay roughly synced.
- [ ] Late joiner receives current state and approximate timestamp.

## OBS tests

- [ ] OBS WebSocket enabled.
- [ ] `OBS_WEBSOCKET_URL` and password work.
- [ ] `/watch status` reports OBS connected.
- [ ] `/watch scene name:BRB` switches scene.
- [ ] `/watch overlay scene:Live source:<source> visible:false` hides source.
- [ ] `/watch title text:<title> obs_source:<source>` updates text source.

## Twitch tests

- [ ] OBS can stream manually to Twitch.
- [ ] Backend can update stream metadata when tokens are configured.
- [ ] Discord Go Live shares OBS projector window.
- [ ] Twitch and Discord viewers see the same OBS-composited output.

## Failure-mode tests

- [ ] Server still starts without OBS available.
- [ ] `/watch scene` returns a skipped message when OBS is unavailable.
- [ ] Server still starts without Twitch credentials.
- [ ] `/watch title` skips Twitch update when Twitch credentials are unavailable.
- [ ] Bad media URLs are rejected.
- [ ] Invalid WebSocket messages return an error instead of crashing.
