# LOKI Self-Research Experiments

LOKI's self-guided research loop is a dry-run lab, not a production self-modifying system.

## Safety Model

- Disabled unless `LOKI_RESEARCH_LAB_ENABLED=true`.
- Blocked automatically in Railway or when `LOKI_EXPERIMENT_ENV=production`.
- Sandboxes must stay under `.loki_lab`.
- Candidate changes are scored before any apply step.
- Blocked paths include `.env`, databases, logs, `.git`, virtualenvs, `bot.py`, `dashboard_app.py`, and `cogs/**`.
- Rollback instructions are mandatory before approval.
- Audit details are redacted before storage.
- Promotion means creating a reviewed patch or PR path; it must not hot-edit production code.

## Current First Iteration

The first implemented pass adds:

- bounded experiment config validation
- mutation candidate scoring
- redacted experiment audit rows
- read-only dashboard visibility at `/ops/research`
- local tests for production blocking, path allowlists, rollback requirements, and redaction

Temporal orchestration and Transformers.js diagnostics are deferred adapters. They should remain optional until the dry-run harness has stronger evidence and review coverage.
