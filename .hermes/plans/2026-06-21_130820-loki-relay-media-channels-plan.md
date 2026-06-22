# Loki Discord Relay + Media Channel System Plan

Status: DRAFT — no bot code changes, no Discord changes, no push yet.

## Goal

Design a polished Loki feature set that can create/manage dedicated Discord relay channels for messages, GIFs/moving media, emotes/stickers, pictures, and music-bot relay cleanup while preserving attribution and hiding raw URLs from visible post text.

The final implementation should be tested locally and in dry-run mode before touching live Discord state, then reviewed by an agent council, then pushed only after explicit approval.

## Requested behavior from user

User wants Loki to support:

1. A message channel for Loki relay output.
2. A GIF/moving-media channel.
3. An emote channel.
4. A picture channel.
5. Relay post rules:
   - Show source channel.
   - Show original poster's display name.
   - Contain relay output in Discord embeds.
   - Load social-media embed images/GIFs.
   - Allow content like videos to be playable in the embed where Discord supports it.
   - Any moving media, including GIFs/emotes/anything that changes over time, should be recognized and routed appropriately.
   - Any message posted in any channel should have content loaded with no raw hypertext showing in the post, including reposts into relay channels.
   - If links must remain, simplify them so only the title is a clickable link.
6. Old posts from `Diva Music Bot` named `Wreckingball` should be cleaned up with only the last 2 messages showing.
7. Relay the music bot set channel using webhooks.
8. More requirements may follow.

## Clarifying questions still needing user answers

These should be answered before implementation because they affect destructive permissions and Discord UX.

1. Channel names/category:
   - Should Loki create exactly:
     - `loki-messages`
     - `loki-gifs`
     - `loki-emotes`
     - `loki-pictures`
   - Or should these use different names/category, e.g. `Loki Relay` category?

2. Watch scope:
   - Should Loki watch every text channel in the guild, or only configured channels?
   - Should it ignore staff/admin/private channels?
   - Should it ignore the relay output channels to prevent relay loops?

3. Original-message handling:
   - Should Loki leave original messages untouched?
   - Should Loki delete originals after relaying?
   - Should Loki suppress embeds on the original message if Discord allows it?
   - Should raw-link cleanup apply only to relay output or also to original user posts?

4. Link policy:
   - Should all URLs be removed from visible text and represented as title links in embeds?
   - If multiple URLs exist, should Loki create one embed per URL, or one combined embed with multiple title links?
   - If a page title cannot be fetched, should the title be domain-only, e.g. `View on TikTok`?

5. Supported platforms:
   - Which are required for phase 1?
   - Candidate platforms:
     - X/Twitter
     - TikTok
     - Instagram
     - Reddit
     - YouTube
     - Tenor
     - Giphy
     - Discord CDN
     - Spotify/SoundCloud
   - Are link-fixer/proxy services allowed for richer embeds, e.g. vxtwitter/fxtwitter, ddinstagram, tiktok embed helpers?

6. Moving-media definition:
   - Proposed: route these to moving-media channels:
     - `.gif`
     - animated `.webp`
     - `.mp4`, `.mov`, `.webm`
     - Tenor/Giphy links
     - Discord animated custom emoji `<a:name:id>`
     - animated stickers if detectable
   - Should animated emojis go to `loki-emotes` or `loki-gifs`?

7. Wreckingball cleanup:
   - Which channel(s) contain `Diva Music Bot` / `Wreckingball` posts?
   - Should Loki keep newest 2 per channel or newest 2 globally?
   - Should cleanup be one-time admin command, scheduled, or continuous?
   - Should cleanup use dry-run first and require confirmation before deleting?

8. Music bot webhook relay:
   - What is the source music channel ID/name?
   - What is the destination channel ID/name?
   - Should webhook posts display as:
     - original music bot name/avatar,
     - `Wreckingball`,
     - or `Loki Relay`?

9. Webhook identity:
   - Should relay posts use webhooks to mimic the original poster's display name/avatar?
   - Or should all relay posts be visibly authored by Loki with attribution inside the embed?
   - Recommended safer default: webhooks named `Loki Relay`, attribution in embed, not impersonating users.

10. Permissions:
   - Loki will need some or all of:
     - Manage Channels
     - Manage Webhooks
     - Manage Messages
     - Read Message History
     - Send Messages
     - Embed Links
     - Attach Files
     - Use External Emojis/Stickers if relevant
   - Confirm which permissions Loki already has or can be granted.

11. Rollout safety:
   - Recommended rollout:
     1. Unit tests only.
     2. Local dry-run parsing tests.
     3. Discord dry-run command in private/admin channel.
     4. One test channel live relay.
     5. Full guild rollout.

12. Rules text:
   - Provide exact text if the new relay channels should have a pinned rules/embed message.

## Proposed safe default assumptions if user says “use your judgment”

These are intentionally conservative.

1. Create or reuse a category named `Loki Relay`.
2. Create or reuse channels:
   - `loki-messages`
   - `loki-pictures`
   - `loki-gifs`
   - `loki-emotes`
   - `loki-music-relay`
3. Watch all public text channels except:
   - the Loki relay channels,
   - bot command/admin channels unless explicitly included,
   - channels Loki cannot read,
   - DM/private threads.
4. Never delete user originals in phase 1.
5. Never delete Wreckingball posts except via explicit admin command with dry-run output first.
6. Relay posts use Loki-owned webhooks named `Loki Relay`, not user-impersonating webhooks.
7. Each relay embed includes:
   - author: original poster display name + avatar
   - source channel mention
   - jump link to original message
   - timestamp of original message
   - cleaned message text
   - title-link fields for URLs
   - image/video/GIF preview where Discord allows
8. Raw URLs are removed from relay visible text.
9. Original messages are left untouched unless an admin enables original cleanup.
10. `FAUST_AGI_EXECUTE=false` remains unchanged for safe AGI-assisted drafting/testing.

## Discord platform constraints to respect

1. Discord bots cannot fully control every third-party embed preview.
   - They can send embeds and files.
   - They can suppress embeds on messages only with Manage Messages and only in supported contexts.
   - They cannot force every video platform to be playable inline if Discord does not support it.

2. Embed limits matter:
   - 10 embeds per message.
   - 6000 total embed characters per message.
   - 256 character title.
   - 4096 character description.
   - 25 fields per embed.

3. Bulk delete limitation:
   - Discord bulk delete cannot delete messages older than 14 days.
   - Older Wreckingball cleanup must use individual deletes and rate-limit carefully.

4. Message Content Intent:
   - To inspect arbitrary message text and links, Loki needs Discord Message Content Intent enabled in the Developer Portal and in bot code.

5. Webhooks:
   - Webhooks can customize username/avatar per message.
   - Avoid deceptive impersonation unless user explicitly wants mirrored user identity.
   - Safer default: `Loki Relay` webhook with original user attribution in embed.

6. Rate limits:
   - Channel creation, webhook creation, message delete, and repost flows must be queued/rate-limited.
   - Cleanup commands should support max-count limits and progress logs.

## Proposed implementation modules

Likely files to inspect/change in Loki:

- `bot/plugins/relay_core/`
  - existing relay plugin location if present.
- `bot/plugins/admin_config/`
  - admin command surface for setup/dry-run/cleanup.
- `bot/services/`
  - new or extended services for:
    - URL metadata extraction
    - media classification
    - relay routing
    - webhook management
    - cleanup jobs
- `bot/settings.py`
  - env/config for relay behavior.
- `tests/`
  - add focused unit tests.

Potential new files:

- `bot/services/relay_media.py`
- `bot/services/link_sanitizer.py`
- `bot/services/webhook_relay.py`
- `bot/services/wreckingball_cleanup.py`
- `tests/test_relay_media.py`
- `tests/test_link_sanitizer.py`
- `tests/test_webhook_relay.py`
- `tests/test_wreckingball_cleanup.py`

Exact file names should be decided after repo inspection.

## Proposed command UX

Potential slash/admin commands:

1. `/loki-relay setup dry_run:true`
   - Finds or proposes category/channels/webhooks.
   - Does not create anything in dry-run.

2. `/loki-relay setup dry_run:false`
   - Creates missing channels/webhooks if permissions allow.

3. `/loki-relay status`
   - Shows configured source/destination channels and webhook status.

4. `/loki-relay test message:<text> url:<optional>`
   - Sends one test relay embed to a configured test channel.

5. `/loki-relay cleanup-wreckingball dry_run:true keep:2 channel:<optional>`
   - Reports messages that would be deleted.

6. `/loki-relay cleanup-wreckingball dry_run:false keep:2 channel:<optional>`
   - Deletes only after explicit admin invocation.

7. `/loki-relay config ...`
   - Optional later phase for source/destination routing.

## Relay embed design

Embed structure:

- Author:
  - Original poster display name
  - Original poster avatar
- Title:
  - Clean title of the primary URL, clickable
  - Or `Message from #channel` when no URL exists
- Description:
  - Cleaned message text with raw URLs removed
- Fields:
  - Source: `#channel`
  - Original poster: `display_name (@username)`
  - Original: jump URL
  - Attachments: count/type summary if relevant
- Image:
  - Image attachment or metadata image if safe and supported
- Footer:
  - `Relayed by Loki`
- Timestamp:
  - Original message timestamp

## Media routing rules draft

1. Pictures -> `loki-pictures`
   - static image attachments: png, jpg, jpeg, webp if non-animated, avif if supported
   - social image URLs

2. GIFs/moving media -> `loki-gifs`
   - gif attachments
   - animated webp
   - mp4/mov/webm attachments
   - Tenor/Giphy links
   - social posts whose primary preview is moving/video content

3. Emotes/stickers -> `loki-emotes`
   - custom emoji tokens `<:name:id>` and `<a:name:id>`
   - stickers
   - animated emojis may be duplicated/routed here instead of `loki-gifs`, pending user preference

4. General messages -> `loki-messages`
   - text-only messages
   - links without image/video/moving-media classification

5. Music bot -> `loki-music-relay`
   - Wreckingball/Diva Music Bot messages from configured source channel only

## Testing plan

1. Agent council preflight before code:
   - Architecture scout: inspect existing relay/plugin/admin command patterns.
   - Discord API scout: verify discord.py webhook/channel/message APIs and permission constraints.
   - Test strategy scout: identify existing mocks/fakes and safest test seams.

2. Unit tests:
   - URL stripping and title-link conversion.
   - Multi-link message cleaning.
   - Discord custom emoji parsing.
   - Attachment media classification.
   - Social URL classification.
   - Embed payload shape and length truncation.
   - Routing decision matrix.
   - Wreckingball keep-last-2 selection logic.
   - Webhook identity policy.

3. Integration-ish tests with mocked Discord objects:
   - Relay skips relay channels to prevent loops.
   - Webhook creation/reuse behavior.
   - Dry-run cleanup returns planned deletes, performs no deletes.
   - Live cleanup path calls delete only for selected messages.

4. Live dry-run validation:
   - `/loki-relay setup dry_run:true`
   - `/loki-relay test ...`
   - `/loki-relay cleanup-wreckingball dry_run:true keep:2`

5. Final local verification:
   - `python -m pytest -q -p no:cacheprovider`
   - Loki health endpoint remains ok.
   - No duplicate guardian/bot processes.
   - Faust remains dry-run safe unless user explicitly changes it.

## Agent council execution plan after user answers

After questions are answered:

1. Run read-only agent council.
2. Synthesize exact implementation plan.
3. Write tests first.
4. Implement small modules in isolated steps.
5. Run test suite.
6. Run spec review subagent.
7. Run quality/security review subagent.
8. Fix review issues.
9. Run live-safe dry-run commands only.
10. Ask user before live Discord mutation.
11. Commit and push only after explicit approval.

## Immediate next step

Wait for user answers to the clarifying questions, especially:

- exact channel names/category,
- source/destination routing,
- whether originals should be deleted or only relay text cleaned,
- whether Wreckingball cleanup can delete messages,
- whether webhook relay should mimic users/bot or use Loki identity,
- live rollout safety preference.
