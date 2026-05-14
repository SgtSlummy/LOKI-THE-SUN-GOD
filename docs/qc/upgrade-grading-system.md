# Upgrade Grading System

Generated: 2026-05-13T22:26:30

Canonical JSON schema: `docs/schemas/upgrade-grading.schema.json`.

## Grade dimensions

Every upgrade receives scores from 0 to 10 for: functionality, stability, security, maintainability, documentation, test coverage, deployment safety, rollback readiness, memory integration, performance, user value, plugin/skill leverage, swarm compatibility, database compatibility, and media compatibility.

## Readiness rules

- `ready`: no secrets, no critical regressions, rollback path exists, tests/checks pass or known environment blockers are documented.
- `conditional`: low/medium risk with documented blockers that do not affect changed scope.
- `not_ready`: secrets, unsafe migration/deploy, unreviewed destructive change, missing rollback, or unexplained test failures.

## Current run grade

- Upgrade: `hermes-foundation-20260513-221207`.
- Overall grade: 8.1/10.
- Risk: low.
- Merge readiness: conditional.
- Deployment readiness: not ready; docs/schema scaffold only.
- Rollback: remove added foundation docs/schemas/check files, or use checkpoint/patch artifacts.
