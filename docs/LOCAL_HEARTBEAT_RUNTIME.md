# Local LOKI heartbeat runtime

This checkout adds a loopback-only runtime wrapper around the pinned
`codex/activity-stream-bridge` source revision `95273fe`. It keeps the Python
LOKI process as the only Discord gateway owner.

## Modes

- `heartbeat` (default): opens Discord's gateway with no privileged intents and
  does not load LOKI cogs. It proves login, reconnect/resume, native Discord
  heartbeat latency, and local liveness.
- `full`: loads `bot.py` and its cogs, but requires
  `LOKI_LOCAL_ALLOW_FULL=true`. Slash sync, relay, cloud providers, and Hermes
  fallback remain operator-controlled; do not use this mode until the local
  identity and permission gates are reviewed.

The health surface binds to `127.0.0.1` only. `/healthz` and `/heartbeat`
return `503` until Discord is ready and `200` afterward. The response is
redacted and never includes token values or message bodies.

## Start and stop

```powershell
Set-Location "C:\Users\carme\OneDrive\Documents\LokiTHESunGod (Discord Bot)\runtime-local-heartbeat"
& .\.venv\Scripts\python.exe .\local_loki_runtime.py --preflight
& .\scripts\start_loki_local.ps1 -Mode heartbeat
& .\scripts\check_loki_local.ps1
& .\scripts\stop_loki_local.ps1
```

The runner reads `DISCORD_TOKEN` from the repository `.env` or process
environment. It refuses to start the gateway if the token is absent. Never put
the token in a command argument or log.

## Local collaborators

- Hermes is detected as an advisory executable only; no Hermes gateway, cron,
  or background agent is started.
- Agents Council is detected from the local Tarot council config; its human
  batch gate is informational and grants no mutation authority.
- Ollama is probed only on loopback (`OLLAMA_HOST`, default
  `http://127.0.0.1:11434`) and is allowed as a local model lane.
- Tarot Router is probed only on loopback (`LOKI_TAROT_ROUTER_HEALTH_URL`,
  default `http://127.0.0.1:8642/healthz`) but remains disabled. Cloud and paid
  provider fallback is hard-coded false in the health policy.
