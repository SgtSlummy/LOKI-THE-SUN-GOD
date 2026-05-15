# LOKI Schemas

Generated: 2026-05-13T22:26:30

Current schemas: `mythos-task-envelope.schema.json`, `camelot-wing.schema.json`, and `upgrade-grading.schema.json`.

Current snapshots:

- `database-schema-snapshot.json`, a read-only drift guard for `utils/db.py:CORE_SCHEMA` and its Postgres conversion path.
- `activity-bridge-payload-snapshot.json`, a read-only drift guard for Activity Bridge room state fields, WebSocket message types, and HTTP control actions.

Environment templates are guarded by `tests/test_env_examples.py`. The test keeps committed `.env.example` files placeholder-only for sensitive variable names such as tokens, API keys, client secrets, access tokens, and passwords.

Deployment config is guarded by `tests/test_deployment_config.py`. The test keeps root Railway/Nixpacks settings, Procfile process names, and the Activity Bridge Railway service aligned with the documented multi-service deployment contract.

Planned snapshots include MCP tool inputs/outputs and a full environment variable manifest.
Current schemas: `mythos-task-envelope.schema.json`, `camelot-wing.schema.json`, `upgrade-grading.schema.json`, `discord-context-menu-snapshot.json`, `discord-component-custom-id-snapshot.json`, and `discord-persistent-view-registration-snapshot.json`.

`discord-context-menu-snapshot.json` guards the programmatic Discord context-menu registry across `cogs/context_menus.py` and `cogs/translate.py`. It tracks the five user menus and five message menus that live outside slash-command decorators, plus a compact SHA-256 contract hash for drift detection.

`discord-component-custom-id-snapshot.json` guards persistent Discord UI component `custom_id` ownership across forms, music jukebox controls, and tickets. It tracks static and dynamic button IDs without importing Discord modules, catches drift or accidental ID collisions before restart-resilient interactions break, and records the 72-character form-name ceiling needed to keep dynamic form button IDs within Discord's 100-character `custom_id` limit.

`discord-persistent-view-registration-snapshot.json` guards the startup path for those persistent Discord UI views. It verifies that each persistent view class discovered in the component snapshot is registered with `bot.add_view` from a cog startup method, so restart-resilient button interactions remain routable after the bot reconnects.

Planned snapshots include database schema, Activity Bridge payloads, MCP tool inputs/outputs, and environment variable manifests.
