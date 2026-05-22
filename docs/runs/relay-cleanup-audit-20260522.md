# Relay Cleanup Audit

Date: 2026-05-22

Purpose: identify old relay configuration and Discord channels that contain
old relay-marker posts so operators can remove bot-authored relay output without
touching user-authored messages.

## Active State

- Railway `worker`: `RELAY_ENABLED=false`.
- Railway `worker`: no `RELAY_GUILD_ID`, target, ignored, or sensitive relay
  variables are currently set.
- Local `.env`: only `TEST_GUILD_ID=1463393482306486387` was present for relay
  discovery; local relay target vars are not currently set.
- `data/bot.db`: no relay-specific config rows and no current `send_dedupe`
  rows.

## Old Relay Config

Recovered from `docs/PROCESS_AND_CONNECTIONS.md`,
`docs/RAILWAY_DEPLOYMENT.md`, and `data/relay.log`.

```text
RELAY_ENABLED=true
RELAY_GUILD_ID=1463393482306486387
RELAY_FRIENDS_ROLE_NAME=Friends
RELAY_TARGET_CHANNEL_IDS=1471988991879549110,1495605587822514287
RELAY_IGNORED_SOURCE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
RELAY_SENSITIVE_CHANNEL_IDS=1486738933961199737,1463393484537856138,1463393484537856139,1494401872151183551,1502371233696841880,1499435617971343491
```

Old log evidence:

```text
Relay ready guild=1463393482306486387 role=1463393482306486394 targets=The Vibez 101 FM (1471988991879549110) | pirate-radio-tower (1495605587822514287)
```

## Relay Targets

| Channel | ID | Notes |
| --- | --- | --- |
| `Club House / The Vibez 101 FM` | `1471988991879549110` | Voice channel with text history; old relay target. |
| `pirate-radio-tower` | `1495605587822514287` | News channel; old relay target. |

## Sensitive/Ignored Config

| Channel | ID | Status |
| --- | --- | --- |
| `OG HOMIES BRAIN TRUST / og-crew` | `1486738933961199737` | Resolved; sensitive/ignored. |
| `OG HOMIES BRAIN TRUST / ideas-wants-needs-todo-lists` | `1494401872151183551` | Resolved; sensitive/ignored forum. |
| `Club House / smuggler-jukebox` | `1499435617971343491` | Resolved; sensitive/ignored. |
| unknown/deleted/inaccessible | `1463393484537856138` | Not resolved by current bot. |
| unknown/deleted/inaccessible | `1463393484537856139` | Not resolved by current bot. |
| unknown/deleted/inaccessible | `1502371233696841880` | Not resolved by current bot. |

## Bot Identities Found

| Bot/user | ID | Cleanup meaning |
| --- | --- | --- |
| Current LOKI THE SUN GOD | `1503830186087415908` | Current Railway bot identity. |
| Old LOKI bot identity | `1497752932345708584` | Primary old-bot cleanup target. |
| Deleted User | `456226577798135808` | User-authored marker posts; do not delete as bot output. |
| `cannabiscannibals` | `294709392798908417` | User-authored marker post; do not delete as bot output. |

## Discord Scan Results

Deep scan used the bot token locally through Discord REST, no deletion.

| Channel | Scanned | Relay marker posts | Old bot posts | Current LOKI posts | User-authored marker posts |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Club House / The Vibez 101 FM` (`1471988991879549110`) | 761 | 159 | 130 | 10 | 19 |
| `pirate-radio-tower` (`1495605587822514287`) | 503 | 454 | 319 | 110 | 25 |
| `Underground Cables / audit-log-shit` (`1495603926890844251`) | 119 | 2 | 2 | 0 | 0 |
| `the-vibez-network` (`1470847673023205438`) | 65 | 1 | 0 | 0 | 1 |

Cleanup candidate totals:

- Old bot only: 451 messages.
- Current LOKI relay posts only: 120 messages.
- All bot-authored relay-marker posts: 571 messages.
- User-authored marker posts: 45 messages; leave these alone unless manually
  reviewed.

## Removal Criteria

Use a dry run before deleting. Delete only messages that match all of:

- Destination channel is one of:
  - `1471988991879549110`
  - `1495605587822514287`
  - `1495603926890844251`
- Author is a bot identity selected for cleanup:
  - old-bot-only cleanup: `1497752932345708584`
  - full bot relay cleanup: `1497752932345708584` or `1503830186087415908`
- Message contains a relay marker:
  - an embed/content URL matching `discord.com/channels/<guild>/<source>/<message>`
  - or legacy text matching `LOKI THE SUN GOD relay source <guild>:<message>`

Do not delete user-authored marker posts by default.

## Source Channels Referenced By Markers

Resolved source channels included:

- `Club House / The Vibez 101 FM` (`1471988991879549110`)
- `pirate-radio-tower` (`1495605587822514287`)
- `Club House / gen-chat` (`1463393484743639105`)
- `FRIENDS / mod-abuse` (`1491977074112725197`)
- `FRIENDS / quote-wall-number-9` (`1498405932944589012`)
- `FRIENDS / 🖼️🛬🐈🚵` (`1463393484743639103`)
- `OG HOMIES BRAIN TRUST / og-crew` (`1486738933961199737`)
- `Club House / smuggler-jukebox` (`1499435617971343491`)
- multiple archived/private/deleted threads under `games`, `resources`, and
  `ideas-wants-needs-todo-lists`.

One marker referenced external/inaccessible channel `686063092681277526`.
