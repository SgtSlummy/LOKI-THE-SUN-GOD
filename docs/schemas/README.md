# LOKI Schemas

Generated: 2026-05-13T22:26:30

Current schemas: `mythos-task-envelope.schema.json`, `camelot-wing.schema.json`, and `upgrade-grading.schema.json`.

Current snapshots:

- `database-schema-snapshot.json`, a read-only drift guard for `utils/db.py:CORE_SCHEMA` and its Postgres conversion path.
- `activity-bridge-payload-snapshot.json`, a read-only drift guard for Activity Bridge room state fields, WebSocket message types, and HTTP control actions.

Environment templates are guarded by `tests/test_env_examples.py`. The test keeps committed `.env.example` files placeholder-only for sensitive variable names such as tokens, API keys, client secrets, access tokens, and passwords.

Deployment config is guarded by `tests/test_deployment_config.py`. The test keeps root Railway/Nixpacks settings, Procfile process names, and the Activity Bridge Railway service aligned with the documented multi-service deployment contract.

Planned snapshots include MCP tool inputs/outputs and a full environment variable manifest.
