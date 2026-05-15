# LOKI Discord Automated Acceptance

LOKI can automate every Discord production gate that Discord exposes to bot tokens, normal HTTP, or in-process code tests. The only gates that cannot be truthfully completed by the production bot alone are gates that require a real Discord user interaction or a separate listener to confirm audible audio.

## Run the safe bot-token probe

```powershell
python .\scripts\discord_acceptance_probe.py `
  --guild-id $env:TEST_GUILD_ID `
  --text-channel-id $env:LOKI_ACCEPTANCE_CHANNEL_ID `
  --voice-channel-id $env:LOKI_ACCEPTANCE_VOICE_CHANNEL_ID `
  --dashboard-url https://your-dashboard.example `
  --activity-bridge-url https://your-activity-bridge.example `
  --json
```

Environment defaults:

- `DISCORD_TOKEN`: production or staging bot token.
- `TEST_GUILD_ID` or `LOKI_ACCEPTANCE_GUILD_ID`: guild to probe.
- `LOKI_ACCEPTANCE_CHANNEL_ID` or `LOKI_JUKEBOX_CHANNEL_ID`: text channel for read/send/application-command permission checks.
- `LOKI_ACCEPTANCE_VOICE_CHANNEL_ID`: voice/stage channel for Connect/Speak permission checks.
- `DASHBOARD_PUBLIC_URL`: optional dashboard base URL; `/healthz` is probed.
- `ACTIVITY_BRIDGE_PUBLIC_URL`: optional Activity Bridge base URL; `/healthz` is probed.
- `LOKI_ACCEPTANCE_REQUIRED_COMMANDS`: optional comma or space separated slash commands that must be registered.

Optional:

```powershell
python .\scripts\discord_acceptance_probe.py --post-probe-message
```

`--post-probe-message` sends a bot-authored probe message to the configured text channel and immediately deletes it. Use it only in an operator-approved test channel.

For staging or focused releases, override the required slash-command set without editing the script. Values from repeated `--required-command` flags and `LOKI_ACCEPTANCE_REQUIRED_COMMANDS` are unioned into one required set:

```powershell
python .\scripts\discord_acceptance_probe.py `
  --required-command ask `
  --required-command dashboard,play `
  --json
```

## What is fully automated

- Bot token validity and bot identity.
- Guild reachability.
- Bot membership and base permission bits.
- Text channel visibility, send, read-history, embed, and application-command permissions.
- Voice/stage channel visibility, Connect, and Speak permissions.
- Slash command registration for `/ask`, `/npc`, `/play`, `/queue`, `/stop`, and `/dashboard` by default, or the commands provided through `--required-command` / `LOKI_ACCEPTANCE_REQUIRED_COMMANDS`.
- Dashboard and Activity Bridge HTTP health.
- Local command/cog behavior through pytest and `scripts/release_check.py`.

## What cannot be done by the production bot alone

Discord does not let bot tokens create user interactions or invoke their own slash commands. LOKI also ignores bot/webhook authors in the NPC listener, by design, so a bot-authored Discord message cannot prove non-bot NPC reply behavior.

Audible playback is similar: the bot can verify that it may Connect/Speak and that Lavalink is reachable, but only a real listener or separate Discord test client can prove that audio was heard.

Safe substitutes:

- Use pytest/in-process tests for command callback behavior.
- Use the REST probe for deployed command registration and permissions.
- Use a separate staging Discord test client controlled by a real account for full end-to-end slash invocation and audible voice assertions.
- Do not automate a normal user token; Discord user-token automation is unsafe and violates Discord platform expectations.

## Release gate command set

Run these before publishing:

```powershell
python .\scripts\release_check.py --strict-env
python -m pytest tests -q
python .\scripts\discord_acceptance_probe.py --json
```

For Activity Bridge:

```powershell
cd .\services\activity-bridge
npm run test:rooms
npm run typecheck
npm run build
```
