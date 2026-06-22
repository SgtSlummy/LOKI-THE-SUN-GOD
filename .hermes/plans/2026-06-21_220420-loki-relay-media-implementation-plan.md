# Loki Discord Relay + Media Channel System Implementation Plan

> For Hermes: this plan was executed in the safe order requested: fill questionnaire defaults, inspect project, write/verify tests, then implement dry-run-first relay/media helpers.

Goal: Build Loki relay/media-channel foundations safely: clean embed-first relay output, media classification/routing, idempotent channel/webhook setup planning, and Wreckingball cleanup dry-run/live selection.

Architecture: Keep destructive Discord behavior behind explicit admin commands and confirmation strings. Put pure classification/setup/cleanup logic in service modules with unit tests. Integrate embed-first relay formatting and safe webhook identity into the existing relay_core plugin without changing live Discord state during local verification.

Tech Stack: Python 3.11, discord.py 2.x, pytest, existing Loki plugin/service structure.

---

## Decisions Filled From Questionnaire

- Category: `Loki Relay`
- Output channels: `loki-messages`, `loki-pictures`, `loki-gifs`, `loki-emotes`, `loki-music-relay`
- Originals: left untouched in phase 1
- Raw URLs: removed from relay-visible text; represented as clean embed title links where possible
- Watch scope: start with configured/test channels, exclude relay output/admin/staff/private/bot-log channels
- Webhook identity: `Loki Relay`, not original-user impersonation
- Wreckingball cleanup: newest 2 per channel; dry-run by default; live delete requires `confirm: DELETE`
- Setup live mutation: requires `dry_run:false` and `confirm: CREATE`

Filled questionnaire saved at:
`C:\Users\carme\Documents\Loki 2.0\.hermes\plans\2026-06-21_220420-loki-relay-questionnaire-filled.txt`

---

## Implementation Tasks Completed

### Task 1: Add media-routing service

Files:
- Created: `bot/services/relay_media.py`
- Created tests: `tests/test_relay_media_routing.py`

Implemented:
- `RelayMediaConfig`
- `select_relay_channel_key()`
- `should_ignore_source_channel()`

Behavior:
- text -> messages
- images -> pictures
- GIF/video/video cards -> gifs
- stickers/custom emotes -> emotes
- configured relay output channels are ignored to prevent loops

### Task 2: Extend media resolver

Files:
- Modified: `bot/models/media.py`
- Modified: `bot/services/media_resolver.py`
- Created tests: `tests/test_media_resolver_extra.py`

Implemented:
- New `MediaKind.EMOTE`
- Custom Discord emoji parsing for `<:name:id>` and `<a:name:id>`
- Tenor/Giphy moving-media cards
- Direct video link classification for `.mp4`, `.mov`, `.webm`, `.m4v`
- Video filename fallback classification

### Task 3: Add embed-first relay formatting

Files:
- Modified: `bot/plugins/relay_core/formatting.py`
- Modified: `bot/plugins/relay_core/plugin.py`
- Created tests: `tests/test_relay_embed_formatting.py`

Implemented:
- `build_relay_embeds()` primary attribution embed
- Source field, original poster field, jump link, timestamp, footer
- Media card embeds now set `embed.url`, making title links clickable
- Relay send now includes primary relay embed before media embeds

### Task 4: Make webhook relay identity safe by default

Files:
- Modified: `bot/plugins/relay_core/plugin.py`

Implemented:
- Webhook sends now use `username="Loki Relay"`
- Original-user attribution stays inside embeds instead of webhook name/avatar impersonation

### Task 5: Add setup dry-run/apply planner

Files:
- Created: `bot/services/relay_setup.py`
- Created tests: `tests/test_relay_setup_plan.py`
- Modified: `bot/plugins/admin_config/plugin.py`

Implemented:
- `plan_relay_setup()`
- Default category/channel names
- Idempotent category/channel/webhook reuse
- Dry-run returns planned actions with no mutation
- `/relay setup` admin command
- Live setup requires `confirm: CREATE`

### Task 6: Add Wreckingball cleanup selector/executor

Files:
- Created: `bot/services/wreckingball_cleanup.py`
- Created tests: `tests/test_wreckingball_cleanup.py`
- Modified: `bot/plugins/admin_config/plugin.py`

Implemented:
- Strict bot-authored Wreckingball/Diva selector
- Keep newest N per channel, default N=2
- Dry-run returns planned delete IDs without deleting
- Live mode deletes only selected messages
- `/relay cleanup_wreckingball` admin command
- Live cleanup requires `confirm: DELETE`

### Task 7: Wire media-channel routing configuration and safety hardening

Files:
- Modified: `bot/settings.py`
- Modified: `bot/plugins/relay_core/plugin.py`
- Modified: `bot/services/media_resolver.py`
- Created tests: `tests/test_relay_media_settings.py`

Implemented:
- `RELAY_MEDIA_CHANNEL_IDS_JSON` parses `{messages,pictures,gifs,emotes,music}` channel IDs
- Relay core uses configured media channel IDs to route by media type
- Relay output channel IDs are skipped to prevent loops
- Relay embed count is capped at Discord's 10-embed limit
- Private/local/non-http URLs are not fetched or relayed as media cards
- Native-unfurl mode no longer reintroduces raw URLs by default

### Task 8: Fix environment-sensitive Faust test isolation

Files:
- Modified: `tests/test_faust_agi.py`

Reason:
- Existing `.env` values (`FAUST_AGI_PROVIDER=codex`, `FAUST_AGI_EXECUTE=false`) contaminated a settings test that expected defaults.

Implemented:
- Test now explicitly sets `FAUST_AGI_PROVIDER=""` and `FAUST_AGI_EXECUTE="true"` before calling `Settings.from_env()`.

---

## Verification

Focused feature tests:

```bash
python -m pytest -q -p no:cacheprovider tests/test_relay_media_routing.py tests/test_media_resolver_extra.py tests/test_relay_embed_formatting.py tests/test_relay_setup_plan.py tests/test_wreckingball_cleanup.py
```

Result:

```text
24 passed, 1 warning in 0.29s
```

Full suite:

```bash
python -m pytest -q -p no:cacheprovider
```

Result:

```text
66 passed, 1 warning in 3.35s
```

Warning:
- `discord.player` imports deprecated Python stdlib `audioop`; external dependency warning only.

---

## Safe Live Rollout Steps Not Yet Run

No live Discord mutation was performed locally.

After `/relay setup dry_run:false confirm:CREATE`, configure media routing with `RELAY_MEDIA_CHANNEL_IDS_JSON`, for example:

```json
{"messages": 111, "pictures": 222, "gifs": 333, "emotes": 444, "music": 555}
```

Recommended next live sequence:

1. Run `/relay setup dry_run:true` in Discord.
2. Review planned category/channel/webhook actions.
3. If correct, run `/relay setup dry_run:false confirm:CREATE`.
4. Configure/add one test source route only.
5. Post test messages with text/image/GIF/emote/video links.
6. Run `/relay cleanup_wreckingball channel:<music-channel> dry_run:true keep:2 limit:100`.
7. Only if the dry-run delete IDs are correct, run with `dry_run:false confirm:DELETE`.

Do not enable broad watch-all or destructive original-message cleanup without a separate approval.
