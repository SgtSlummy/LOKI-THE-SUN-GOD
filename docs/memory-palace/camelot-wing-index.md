# Camelot Wing Index

Updated: 2026-05-14 13:07 UTC

Camelot is LOKI's durable memory palace model. It separates stable, consent-safe knowledge from ephemeral run logs.

## Wing Schema

```yaml
name: string
entity_type: user | discord_user | bot | concept | idea | repository | plugin | skill | media | test | upgrade | deployment | rollback
summary: string
details: string
sources: list
related_entities: list
tags: list
retrieval_keywords: list
upgrade_relevance: string
priority_score: 0-10
confidence_score: 0-10
risk_score: 0-10
status: active | archived | blocked | needs_review
action_items: list
test_links: list
commit_links: list
last_reviewed: timestamp
```

## Current Wings to Maintain

| Wing | Type | Purpose | Risk |
|---|---|---|---|
| LOKI THE SUN GOD | bot | Product/system memory | Medium |
| Natural-language Discord UX | concept | Preserve member-facing conversational behavior | Low |
| Admin-gated mutation | concept | Permission doctrine for changes | Medium |
| Hermes direct control | concept | Local advisory/branch automation model | High |
| Lavalink music path | media | Production music architecture | Medium |
| Mythos task envelopes | concept | Swarm routing and run packets | Low |
| SgtSlummy GitHub review | repository | Research source map | Medium |
| Railway/container deployment | deployment | Release/runbook memory | High |

## Memory Rules

- Store run progress in `docs/runs/`, not durable memory.
- Store only stable facts, operator preferences, schemas, and reusable procedures in Camelot.
- Redact secrets, tokens, private Discord content, and unnecessary PII.
- Distinguish admin-provided facts from inferred preferences.
- Provide export/delete paths before member-specific memory becomes production-facing.
