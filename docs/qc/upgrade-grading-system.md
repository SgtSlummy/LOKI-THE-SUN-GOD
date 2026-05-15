# Upgrade Grading System

Updated: 2026-05-14 13:07 UTC

Each LOKI upgrade is graded 0-10 across the following dimensions.

| Dimension | Meaning |
|---|---|
| Functionality | Meets stated objective |
| Stability | Avoids regressions and handles errors |
| Security | Preserves secrets, SSRF safety, permission gates |
| Maintainability | Small, readable, modular change |
| Documentation | Updates relevant docs/run reports |
| Test coverage | Adds or preserves meaningful tests |
| Deployment safety | No unsafe live action; clear health checks |
| Rollback readiness | Revert path and checkpoint documented |
| Memory integration | Camelot/run artifacts updated appropriately |
| Performance | No avoidable latency/resource regression |
| User value | Improves Discord/operator experience |
| Plugin/skill leverage | Uses reusable patterns without unsafe installs |
| Swarm compatibility | Fits Mythos task envelopes and roles |
| Database compatibility | Avoids unsafe schema/data changes |
| Media compatibility | Preserves Lavalink/music requirements |

## Automatic Not-Ready Blockers

- Breaks natural-language Discord UX by default.
- Bypasses admin/permission gates.
- Exposes secrets, private member content, or unredacted tokens.
- Replaces Lavalink production path without approval.
- Performs live posting/deployment/restarts without approval.
- Lacks rollback evidence for risky changes.
- Fails compile, secret scan, or pytest gates.

## This Run Grade Template

```yaml
functionality: 8
stability: 9
security: 9
maintainability: 8
documentation: 9
test_coverage: 8
deployment_safety: 10
rollback_readiness: 9
memory_integration: 8
performance: 10
user_value: 7
plugin_skill_leverage: 7
swarm_compatibility: 9
database_compatibility: 10
media_compatibility: 9
overall: 8.7
risk: low
merge_readiness: ready_if_checks_pass
deployment_readiness: docs_only_no_live_deploy
```

---

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
