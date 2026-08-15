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

## Prepare an install and server handoff

The installer requires `py -3.12`, creates or verifies a release-specific
Python 3.12 environment, installs checked-in runtime and development
requirements, and runs pywin32 imports, compile, Ruff, secret scan, redacted
preflight, release checks, and repository tests. It never starts Discord or
registers a Windows service:

```powershell
& .\scripts\install_loki_local.ps1 `
  -VenvPath .venv-local312 `
  -VerificationRoot "$env:LOCALAPPDATA\Loki\verification\manual"
```

Create a clean transfer archive from the committed source when the server is
ready to receive it:

```powershell
& C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe `
  -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\prepare_loki_server_bundle.ps1
if ($LASTEXITCODE -ne 0) { throw "Immutable bundle preparation failed." }
```

The archive is written under `handoff/` with a JSON SHA-256 sidecar, portable
digest, external service bootstrap, and separate bootstrap digest. It excludes
`.env`, virtual environments, data, logs, and Git metadata. The script does not
upload, extract, deploy, register services, or start Discord.

For manual development, the runner keeps repository `.env` fallback. Managed
Windows precedence is Credential Manager, then process environment, then
`.env`; stable service config lives at
`C:\ProgramData\Loki\config\lokithesungod.env`. Never put a credential in a
command argument or log.

Full immutable Windows deployment, credential seeding, service registration,
verification, human-gated test-guild acceptance, upgrade, and rollback are in
[WINDOWS_SERVICE_DEPLOYMENT.md](WINDOWS_SERVICE_DEPLOYMENT.md). Provision and
verify the external bootstrap first; it creates the immutable release and venv
and installs stopped services. Then seed Credential Manager and start the
services in order.

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
