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
