---
name: loki-relay
version: 0.1.0
description: Project rules for Loki 2.0, a Python Railway-hosted Discord relay bot backend.
---

# Loki Relay Project Rules

Use this skill when working in the Loki 2.0 repository.

## Runtime Shape

- The app starts with `python -m bot.main`.
- Railway health is `GET /healthz`.
- Secrets belong only in `.env` or Railway variables. Never print or write secret values into docs, logs, receipts, or memory.
- Keep Discord relay output mention-safe with `discord.AllowedMentions.none()`.
- Keep clean media mode free of visible raw URLs unless `MEDIA_MODE=native_unfurl`.

## Architecture

- Use the eight plugin slots in `bot/plugins/base.py`.
- Only `admin_config`, `relay_core`, `media_resolver`, and `moderation_audit` are enabled by default.
- Future plugins stay stubs unless explicitly assigned.
- Services are injected through the registry; plugins should not reach around the service container.

## Verification

Run these before claiming completion:

```powershell
python -m pytest
python -m compileall bot
```

For Mythos SWD actions, use `--dry-run` before applying writes and `--run-checks` when finalizing.
