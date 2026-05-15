# LOKI Schemas

Generated: 2026-05-13T22:26:30

Current schemas: `mythos-task-envelope.schema.json`, `camelot-wing.schema.json`, `upgrade-grading.schema.json`, and `discord-context-menu-snapshot.json`.

`discord-context-menu-snapshot.json` guards the programmatic Discord context-menu registry across `cogs/context_menus.py` and `cogs/translate.py`. It tracks the five user menus and five message menus that live outside slash-command decorators, plus a compact SHA-256 contract hash for drift detection.

Planned snapshots include database schema, Activity Bridge payloads, MCP tool inputs/outputs, and environment variable manifests.
