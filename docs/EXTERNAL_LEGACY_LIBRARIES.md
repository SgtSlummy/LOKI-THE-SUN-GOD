# External Legacy Libraries

LOKI can read external, read-only legacy libraries without making the old bot part of the LOKI codebase.

## Ralph Wiggum / CarlClone

The extracted Ralph Wiggum library is stored outside this repository at:

`C:\Users\carme\OneDrive\Desktop\Codex\loki-libraries\ralph-wiggum-legacy`

It contains:

- `ralph_wiggum_legacy_library.json` — machine-readable index of components, commands, source file inventory, sanitized source snapshots, environment example keys, and SQLite schema/row counts.
- `docs/legacy_capabilities.md` — human-readable capability and command summary.
- `source_snapshots/` — sanitized text snapshots for source/docs/config files. Live `.env` values and database rows are not copied.

## Access path

LOKI defaults to `C:\Users\<you>\OneDrive\Desktop\Codex\loki-libraries` via `utils.operator_surface.external_library_root()`.

Override with:

```env
LOKI_EXTERNAL_LIBRARY_ROOT=C:\path\to\loki-libraries
```

Or pin one or more exact libraries with `LOKI_EXTERNAL_LIBRARY_PATHS`. Separate multiple paths with the OS path separator.

## Runtime surfaces

The LOKI MCP server exposes:

- Resource: `loki://external-legacy-libraries`
- Tool: `loki_search_external_legacy_libraries`

The regular AI docs search also includes markdown files found inside each external library and its `docs/` directory.

## Use policy

Use these libraries as historical knowledge only. LOKI should replicate, improve, or continue useful behavior in LOKI modules rather than importing legacy runtime code directly.
