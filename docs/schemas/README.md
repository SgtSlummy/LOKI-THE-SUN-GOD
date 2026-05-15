# LOKI Schemas

Generated: 2026-05-13T22:26:30

Current schemas: `mythos-task-envelope.schema.json`, `camelot-wing.schema.json`, `upgrade-grading.schema.json`, `discord-context-menu-snapshot.json`, and `discord-component-custom-id-snapshot.json`.

`discord-context-menu-snapshot.json` guards the programmatic Discord context-menu registry across `cogs/context_menus.py` and `cogs/translate.py`. It tracks the five user menus and five message menus that live outside slash-command decorators, plus a compact SHA-256 contract hash for drift detection.

`discord-component-custom-id-snapshot.json` guards persistent Discord UI component `custom_id` ownership across forms, music jukebox controls, and tickets. It tracks static and dynamic button IDs without importing Discord modules, catches drift or accidental ID collisions before restart-resilient interactions break, and records the 72-character form-name ceiling needed to keep dynamic form button IDs within Discord's 100-character `custom_id` limit.

Planned snapshots include database schema, Activity Bridge payloads, MCP tool inputs/outputs, and environment variable manifests.
