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
