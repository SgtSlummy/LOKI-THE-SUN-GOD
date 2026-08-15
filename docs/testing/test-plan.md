# LOKI Test Plan

Updated: 2026-08-14

## Baseline Gates

Run before commit/push:

```powershell
py -3.12 -m compileall -q .
py -3.12 .\scripts\secret_scan.py
py -3.12 -m ruff check .
py -3.12 -m pytest tests -q
```

Record exact counts only with the candidate commit and command output that
produced them. Do not carry a prior run's count forward as current evidence.

## Windows service CI gates

The `windows-services` GitHub Actions job uses `windows-latest` and Python 3.12.
It installs both requirements files, compiles the repository, runs the secret
scan, then executes:

```powershell
python -m pytest tests/test_windows_service_host.py tests/test_service_stop_runtime.py -q
python -m pytest tests/test_credential_store.py tests/test_local_runtime.py -q
python -m pytest tests/test_installer_archive_trust.py tests/test_service_install_transaction.py tests/test_loki_service_bootstrap.py -q
```

These are unit/runtime checks only. A test may invoke the service installer in
its read-only `-EvidenceOnly` mode or prove that a noncanonical bootstrap copy
fails closed. CI must never run either installer in production mode, register
an SCM service, start Discord, seed Credential Manager, or mutate a live guild.

## Test Categories

| Category | Coverage target |
|---|---|
| Natural-language UX | LOKI responds to conversational prompts and does not require slash commands by default |
| Admin gates | Mutating actions require Discord/admin/dashboard permissions |
| Link/media safety | URL parsing, SSRF guards, preview sanitization, music metadata extraction |
| Music/Lavalink | Queue state, permission controls, reconnect/degraded behavior where offline-testable |
| MCP | Local tools/resources/prompts stay offline-safe and gated |
| Activity Bridge | Local bridge status, posting gates, retry/degraded behavior |
| Dashboard/Desktop | Health endpoints, operator controls, local bridge surfaces |
| Persistence | Schema bootstrap and future drift checks |
| Deployment | Preflight, env-name manifest, rollback evidence |
| Native Windows services | Command/env construction, stop semantics, duplicate detection, Credential Manager fallback, service-safe logs |

## Live Windows acceptance

Follow [WINDOWS_SERVICE_DEPLOYMENT.md](../WINDOWS_SERVICE_DEPLOYMENT.md). Live
acceptance is separate from CI and requires both loopback health endpoints,
exact process/release evidence, redacted log scanning, dashboard OAuth, and
bounded command/permission checks in the configured test guild. Relay, slash
sync, production-guild mutation, recovery exercise, and reboot remain separate
operator approvals.

## New Regression Added This Run

`tests/test_link_previews.py` now explicitly blocks IPv6 loopback, link-local, unspecified, and `0.0.0.0` preview URLs. This is a test-only SSRF regression guard for Discord relay/media preview inputs.
