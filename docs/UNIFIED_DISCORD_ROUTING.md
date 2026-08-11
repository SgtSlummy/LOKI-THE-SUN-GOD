# Unified Loki, AutoDM, Mythos, and Tarot routing

Loki owns the only Discord gateway connection. The optional AutoDM cog receives
normal messages in configured campaign channels, Mythos classifies each action
deterministically, and the AutoDM solo API owns campaign state and narration.
Loki's existing `/ask` command uses Tarot when `TAROT_ROUTER_ENABLED=true`.

## Local configuration

Copy the relevant variables from `.env.example` into the runtime's protected
environment. Reuse an existing Discord token through `DISCORD_TOKEN` or the
compatibility alias `DISCORD_BOT_TOKEN`; never configure both bot processes to
connect with the same token.

```dotenv
DISCORD_TOKEN=

AUTODM_DISCORD_ENABLED=true
AUTODM_DISCORD_CHANNEL_IDS=<campaign channel or parent channel id>
AUTODM_BASE_URL=http://127.0.0.1:8000/v1/solo
MYTHOS_ROUTER_ENABLED=true

TAROT_ROUTER_ENABLED=true
TAROT_ROUTER_BASE_URL=http://127.0.0.1:8642/v1
LOKI_LLM_MODEL=<model exposed by Tarot>
```

Set `AUTODM_DISCORD_BACKEND_TOKEN` only when the AutoDM service requires it. A
non-loopback AutoDM URL is rejected unless `AUTODM_ALLOW_REMOTE=true`, and a
remote route also requires that backend token.

## Message ownership

- Normal messages in an AutoDM channel go to AutoDM through the deterministic
  Mythos route. Messages are serialized per channel and user, and the Discord
  message ID becomes the AutoDM idempotency key.
- Messages that mention or directly address Loki stay with Loki's NPC route.
- Prefix commands stay with the Discord command framework.
- AutoDM receives Discord metadata and text, never the Discord bot token or a
  Tarot/provider key.

All four integrations remain locally staged until their enable flags, service
health, and protected secret bindings are confirmed.
