# Media and Music Expansion Plan

Updated: 2026-05-14 13:07 UTC

LOKI's production music target remains Lavalink/Wavelink. Local audio/DCA assets may support fallback demos or curated clips, but they do not replace the production playback path without operator approval.

## Requirements

| Area | Requirement |
|---|---|
| Playback | Lavalink/Wavelink primary for Discord voice |
| Queue | Preserve metadata, requester, source URL, and permission context |
| Permissions | DJ/admin controls gate disruptive actions |
| Health | Detect Lavalink availability, reconnects, and degraded mode |
| Safety | Validate URLs/sources; avoid SSRF and unsafe downloads |
| Observability | Log queue/playback errors without secrets |
| Tests | Offline unit tests for queue logic; live voice tests only with credentials/channel approval |
| Rollback | Disable new media feature flags and return to known queue/playback path |

## Next Safe Work

1. Add offline queue/reconnect tests where code is separable from Discord voice.
2. Document Lavalink environment variables and health checks without secret values.
3. Add operator runbook for degraded playback and restart ordering.
4. Keep link-preview SSRF tests green because media URLs are a common input path.

---

# Media Expansion Plan

Generated: 2026-05-13T22:26:30

## Target pipeline

Receive media request, validate source URL and permissions, check cache/dedupe, queue action, extract metadata, store reference, index metadata, update allowed memory only, prepare playback/retrieval, log and grade reliability.

## Safety constraints

Validate schemes/hosts, avoid storing copyrighted/private content without policy, separate Discord voice/live tests from unit tests, and never expose Lavalink/Discord/Twitch/OBS/OpenAI secrets in logs or memory.

## Next safe work

Add media metadata schema, queue/dedupe fixtures, and playback health-check runbook.
