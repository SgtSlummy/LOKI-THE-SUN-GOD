# Loki Hermes Windows AI Node Installer

This folder is a one-click package for setting up a separate Windows PC as a continuously running Loki/Hermes/Ollama AI node.

Double-click:

```text
Install-LokiHermesNode.cmd
```

The installer intelligently verifies or installs:

- Hermes Agent with a dedicated `loki-node` profile, isolated memory, skills, sessions, and cron state.
- Ollama local LLM runtime for backup reasoning and cron/offline tasks.
- OpenAI/Codex `gpt-5.5` as the primary Hermes model for normal high-capability reasoning.
- Tailscale for private tailnet access from Hermexj/iOS.
- Obsidian and a local `Loki-Hermes-Vault` for durable local AI notes.
- A Faust-compatible bridge at `http://127.0.0.1:8765/api/faust/run` so Loki can call the PC from Discord DM, `/agent council`, or admin-only `/agent maintain`.
- Windows Startup persistence so the node runs autonomously after login.
- The Loki Discord bot application itself, copied to `%LOCALAPPDATA%\LokiHermesNode\LokiBot` and supervised by `scripts.loki_guardian` when this installer is run from the full repo/package.
- A compact 1-bit/BitNet install-aide prompt. If a BitNet GGUF is placed at `%LOCALAPPDATA%\LokiHermesNode\models\bitnet-b1.58.gguf`, the installer creates an Ollama `bitnet-install-aide` model; otherwise it uses the configured Ollama fallback model with the same prompt.

## Security defaults

- Local services bind to `127.0.0.1`.
- Tailscale Serve is used for private tailnet access; no public tunnel is created.
- Loki admin self-maintenance is enabled only through `FAUST_AGI_ADMIN_EXECUTE_ENABLED=true` and the bot's `BOT_ADMIN_USER_IDS` permission gate.
- Secrets are collected locally into `%LOCALAPPDATA%\LokiHermesNode\loki-node.env` and the dedicated Hermes profile `.env`.

## After install

The installer now writes a pairing bundle under `%LOCALAPPDATA%\LokiHermesNode`:

- `PAIR_WITH_LOKI.env` — copy/apply this on the PC that runs Loki.
- `PAIR_WITH_THIS_PC.cmd` — prompts for the local Loki repo path and applies the pairing file.
- `scripts\Apply-LokiHermesNodePairing.ps1` — safe updater that changes only Loki/Faust pairing keys in `.env` and `Loki.env`; it does not print or alter Discord/OpenAI secrets.

Point Loki at the node manually or by applying `PAIR_WITH_LOKI.env`:

```text
FAUST_AGI_BASE_URL=http://127.0.0.1:8765
FAUST_AGI_RUN_PATH=/api/faust/run
FAUST_AGI_PROVIDER=codex
FAUST_AGI_EXECUTE=false
FAUST_AGI_ADMIN_EXECUTE_ENABLED=true
FAUST_AGI_ADMIN_TARGET_COMPONENT=loki_self
FAUST_AGI_ADMIN_WORKSPACE=.
```

If Loki runs on another machine, use the Tailscale Serve HTTPS URL printed by the installer for `FAUST_AGI_BASE_URL`.

## Health checks

```powershell
Invoke-RestMethod http://127.0.0.1:8765/healthz
```

Expected fields include `primary_provider=openai-codex`, `primary_model=gpt-5.5`, and `backup_provider=ollama`.

## Files installed

- `%LOCALAPPDATA%\LokiHermesNode\Start-LokiHermesNode.cmd`
- `%LOCALAPPDATA%\LokiHermesNode\scripts\loki_hermes_bridge.py`
- `%LOCALAPPDATA%\LokiHermesNode\loki-node.env`
- `%USERPROFILE%\.hermes\profiles\loki-node\`
- `%USERPROFILE%\Obsidian\Loki-Hermes-Vault\`
- Startup launcher: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Start-LokiHermesNode.cmd`
