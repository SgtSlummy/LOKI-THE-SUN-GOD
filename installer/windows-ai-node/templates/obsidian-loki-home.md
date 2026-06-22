# Loki Hermes Node

This local Obsidian vault is the operator notebook for the autonomous Loki Hermes Windows node.

## Roles
- Loki Discord bot calls this PC through `FAUST_AGI_BASE_URL`.
- Hermexj/iOS reaches this PC over Tailscale or Tailscale Serve.
- Hermes uses a dedicated `loki-node` profile and memory store.
- Ollama provides local backup and cron-task models.
- OpenAI gpt-5.5 is the default high-capability model.

## Safe operating notes
- Keep secrets in env files, never in notes.
- `/agent maintain` is admin-only and requires `FAUST_AGI_ADMIN_EXECUTE_ENABLED=true`.
- Prefer local `127.0.0.1` binding plus Tailscale Serve rather than public internet exposure.
