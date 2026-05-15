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

---

# Camelot Memory Wing Index

Generated: 2026-05-13T22:26:30

Camelot is the durable memory palace for LOKI. It stores structured, source-backed records with privacy boundaries. This repo currently uses docs and adapter scaffolds as the local contract until a live Camelot service is connected.

## Wing hierarchy

Users, Bots, Concepts, Ideas, Repositories, Skills, Plugins, Media, Upgrades, Tests, Deployment, Mutations, and Rollbacks each get dedicated wings with source links, confidence, risk, status, action items, test links, and commit links.

## Privacy rules

- Never store raw tokens, API keys, OAuth secrets, cookies, private keys, or webhook URLs.
- Store environment variable names only when mapping configuration.
- Discord member memory must be minimal, relevant, redactable, and source-aware.
- Private-channel content should not be captured as durable memory unless explicitly permitted.
- Support export/delete workflows before enabling broad user memory.

## Candidate records from this run

- `camelot.github_source_availability`: public source availability for LOKI/upstreams.
- `camelot.autonomous_evolution_sources`: public inspirations for safe research/evolution loops.
- `camelot.quantum_roots_confidence`: conceptual scoring for corroboration, contradiction checks, confidence decay, and source health.
- `camelot.env_template_safety`: test-backed contract that `.env.example` files contain placeholders only for sensitive keys; tags: `security`, `secrets`, `deployment`, `rollback`, `tests`.
- `camelot.deployment_config_contracts`: test-backed contract for Railway/Nixpacks/Procfile deployment invariants; tags: `deployment`, `railway`, `nixpacks`, `procfile`, `activity-bridge`, `tests`, `rollback`.
- `camelot.activity_bridge_payload_contracts`: test-backed contract for Activity Bridge room state fields, WebSocket payload types, and HTTP room-control actions; tags: `activity-bridge`, `discord-activity`, `websocket`, `payloads`, `tests`, `rollback`.

Canonical record schema: `docs/schemas/camelot-wing.schema.json`.
