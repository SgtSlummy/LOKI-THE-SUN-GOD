# Vercel Preview Deployment

## Scope

The Vercel surface is a sanitized static operator preview under `deploy/vercel-preview`. It is not the production bot runtime.

Production remains Railway-shaped because LOKI needs a persistent Discord worker, Flask dashboard, hosted Postgres, OAuth callback, Lavalink connectivity, and environment-managed secrets.

## Why The Repo Root Is Not Deployed

The repo root currently contains local runtime artifacts such as `data/bot.db` and logs. Git ignores those files, but the fallback Vercel deploy packager does not treat `.gitignore` as a deployment allowlist. Deploying the whole root could package local state.

Only `deploy/vercel-preview` is safe for preview deployment because it contains:

- `index.html`
- `assets/loki-dashboard-icon.svg`
- no `.env`
- no database
- no logs
- no local agent state

## Preview Command

Authenticate first:

```bash
npx --yes vercel@latest login
```

Then deploy from the sanitized folder:

```bash
cd deploy/vercel-preview
npx --yes vercel@latest --yes
```

Do not pass `--prod` for this preview. On headless runners, use a Vercel token
instead of browser login:

```bash
npx --yes vercel@latest --yes --token "$VERCEL_TOKEN"
```

The older claimable deploy endpoint currently returns CLI instructions instead
of a deployment URL, so it is not treated as a passing deployment path.

## Required Production Gates

- Railway web service for `dashboard_app.py`.
- Railway worker service for `python -m bot`.
- Hosted Postgres through `DATABASE_URL`.
- Hosted `REDIRECT_URI` and `DASHBOARD_PUBLIC_URL`.
- Discord OAuth callback test.
- Live Discord `/dashboard`, `/relay status`, and real relay message checks.
- Lavalink node health check for music.
