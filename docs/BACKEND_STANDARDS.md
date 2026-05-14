# Backend Standards Sources

LOKI uses this file as a compact source map for backend engineering standards
that should influence Codex reviews, implementation plans, and Mythos evidence
runs. Project-local tests and security gates still take precedence.

## Futurice Backend Best Practices

- Source: https://github.com/futurice/backend-best-practices
- Snapshot reviewed: `14ded2397a8dcf3a318230193ca464b0e63d42a1`
- License: Creative Commons Attribution 4.0 International
- Mythos run slug: `futurice-backend-best-practices`

Apply these practices when changing LOKI backend, bot, dashboard, MCP,
Activity Bridge, deployment, and database code:

- Keep the root README and local operations docs sufficient for setup,
  operation, and recovery. Futurice emphasizes root README documentation,
  single-command run/deploy flows, reproducible builds, build bill of
  materials, and UTC time handling.
- Document the full development and server environment, including databases,
  application servers, proxy/runtime services, SDK versions, and dependency
  versions. Prefer automatable setup over manual instructions.
- Treat persistent data as an operational contract: verified backups,
  restore tests, cross-environment copy tooling, schema-change plans,
  database update plans, scaling plans, and health monitoring are required
  before promoting risky storage changes.
- Preserve the environment ladder: local, CI, test, staging, and production.
  Local should be runnable without shared external development services where
  practical. Staging should rehearse production changes before production.
- Include build provenance in release artifacts: SDK/tool versions,
  dependencies, git revision, build environment variables, and failed checks.
- Keep Docker and hosted runtimes least-privilege: avoid untrusted binaries,
  run as non-root where possible, rebuild periodically, keep hosts patched,
  and avoid unnecessary container capabilities or network access.
- Keep secrets out of version control. Use ignored local secret files,
  environment variables, or generated config from safe templates.
- For sensitive or powerful actions, maintain audit logs with timestamp,
  originator, and action. Prefer tamper-resistant logging boundaries when the
  system handles sensitive data or broad administrative control.
- Avoid logging personally identifiable or sensitive data. When correlation is
  required, hash or otherwise minimize logged identifiers.
- Treat temporary files and shared hosts as hostile by default. Use protected
  directories or restrictive permissions for temp files, logs, config,
  startup scripts, private keys, crash dumps, and version-control metadata.
- Provide lightweight application status endpoints that aggregate subsystem
  checks. Overall failure should return an appropriate 5xx; load-balancer
  health can be stricter or narrower than the full operator status.
- Release checklists must cover same-process deploys across environments,
  known environment names, stack parity, version mapping, rollback,
  verified backups, logging, release notes, server updates, load testing, and
  automation for repeated release work.

Source evidence map:

- README commandments and build/release basics: lines 62-69.
- Environment setup and automation: lines 75-81.
- Persistence obligations: lines 83-94.
- Environment ladder: lines 136-164.
- Build bill of materials: lines 166-174.
- Security, Docker, secrets, audit, and sensitive-data guidance:
  lines 177-245.
- Shared host and file-permission guidance: lines 260-277.
- Application status and health guidance: lines 279-447.
- Release checklist: lines 474-502.
