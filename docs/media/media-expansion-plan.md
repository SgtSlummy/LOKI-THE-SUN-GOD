# Media Expansion Plan

Generated: 2026-05-13T22:26:30

## Target pipeline

Receive media request, validate source URL and permissions, check cache/dedupe, queue action, extract metadata, store reference, index metadata, update allowed memory only, prepare playback/retrieval, log and grade reliability.

## Safety constraints

Validate schemes/hosts, avoid storing copyrighted/private content without policy, separate Discord voice/live tests from unit tests, and never expose Lavalink/Discord/Twitch/OBS/OpenAI secrets in logs or memory.

## Next safe work

Add media metadata schema, queue/dedupe fixtures, and playback health-check runbook.
