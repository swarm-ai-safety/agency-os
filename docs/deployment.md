# Production Deployment Guide

This runbook covers first-time and repeat production deployment for both:

- the backend API (`agency-os-api` on `127.0.0.1:8000`)
- the marketing/signup site (`site/`)

For API-only host-systemd detail, see [deploy/PRODUCTION_BACKEND.md](../deploy/PRODUCTION_BACKEND.md).

## Architecture

Use one of these production topologies.

### Topology A (current default): split domain via Caddy

```text
Browser
  |-- https://<domain> ----------------------> static site files
  |-- https://api.<domain>/api/v1/* ---------> Caddy -> 127.0.0.1:8000 (FastAPI)
```

- Site and API are on different origins.
- `NEXT_PUBLIC_API_URL` should be `https://api.<domain>`.

### Topology B (same-origin): nginx reverse proxy `/api/*`

```text
Browser
  |-- https://<domain> (site + API same origin)
                   |--> static site files
                   |--> /api/v1/* -> nginx -> 127.0.0.1:8000 (FastAPI)
```

- Site and API share one origin.
- `NEXT_PUBLIC_API_URL` should be empty (`""`) so frontend calls `/api/v1/*`.

## 1) Prerequisites

- Ubuntu/Linux server reachable over SSH.
- `deploy` user with:
  - write access to `/home/deploy/agency-os`
  - permission to restart `agency-os-api` via `sudo systemctl`
- Python 3.11+, Node 22.x, npm 10+, `git`.
- Reverse proxy installed:
  - Caddy for Topology A, or
  - nginx for Topology B.
- DNS:
  - Topology A: `<domain>`, `www.<domain>`, and `api.<domain>`
  - Topology B: `<domain>` and `www.<domain>`

## 2) Environment Variables

### Backend (`/etc/agency-os/api.env`)

Set at minimum:

- `DATABASE_URL` (recommended production path; usually Postgres)
- `CORS_ORIGINS` (must include public site origin)

Optional, feature-dependent:

- `ANTHROPIC_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_ID` for the base subscription checkout
- `BILLING_ALLOWED_HOSTS` for checkout/portal redirect allowlisting
- `BILLING_BASE_URL` for default Stripe success/cancel URLs

Credits and usage-based billing:

- `STRIPE_METERED_PRICE_IDS`
  - Comma-separated metered Stripe price IDs that prepaid credits should apply to
- `STRIPE_CREDIT_TOPUP_PRICE_ID`
  - One-time Stripe price used to sell a credit pack
- `STRIPE_CREDIT_TOPUP_AMOUNT_VALUE`
  - Monetary value in the credit grant, in the smallest currency unit
- `STRIPE_CREDIT_TOPUP_CURRENCY`
  - Defaults to `usd`
- `STRIPE_CREDIT_TOPUP_NAME`
  - Operator-facing label stored on the Stripe credit grant
- `STRIPE_BILLING_CREDITS_API_VERSION`
  - Defaults to `2024-10-28.acacia`

Fallback mode:

- If `DATABASE_URL` is unset, app uses SQLite at `DATABASE_PATH` (default `/var/lib/agency-os/agency_os.db`).

### Site (`site/.env.production`)

- `NEXT_PUBLIC_API_URL`
  - Topology A: `https://api.<domain>`
  - Topology B: empty string (`""`) for same-origin `/api/*`
- `AGENCY_OS_API_URL` (server-side route handlers in Next.js, optional)
- `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` (optional analytics)
- OIDC settings if dashboard auth is enabled (`OIDC_*`, `OIDC_BRIDGE_SECRET`)

## 3) Server Bootstrap (First Time)

```bash
sudo mkdir -p /home/deploy
sudo chown -R deploy:deploy /home/deploy
sudo -u deploy git clone https://github.com/rsavitt/agency-os.git /home/deploy/agency-os

sudo mkdir -p /etc/agency-os /var/lib/agency-os /opt/agency-os
sudo chown -R deploy:deploy /opt/agency-os
```

Create backend env file:

```bash
cd /home/deploy/agency-os
sudo cp deploy/systemd/api.env.example /etc/agency-os/api.env
sudo chmod 600 /etc/agency-os/api.env
```

## 4) Build and Publish the Site

From repo root:

```bash
./scripts/site-install.sh
cd site
npm run build
```

Deployment options:

- Static-site serving (Caddy/nginx root): publish site build output to your web root (for example `/var/www/<domain>/out` if using export artifacts).
- Containerized Next.js serving: use `deploy/docker/Dockerfile.site` (`NEXT_OUTPUT=standalone`) and reverse proxy to container port `3000`.

Note:
- The production deploy workflow on `main` now rebuilds and restarts the `site` container with `docker compose -f deploy/compose/docker-compose.prod.yml up -d --build site` after the API health check passes.
- If you are deploying manually on the host, you must run that same compose command after pulling the latest repo, or frontend-only changes like dashboard billing updates will not reach production.

## 5) Configure Reverse Proxy

### Option A: Caddy split-domain

Use [`deploy/caddy/Caddyfile.host.example`](../deploy/caddy/Caddyfile.host.example):

```bash
sudo cp /home/deploy/agency-os/deploy/caddy/Caddyfile.host.example /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

### Option B: nginx same-origin `/api/*`

Use [`deploy/nginx.conf.example`](../deploy/nginx.conf.example) as a baseline:

```bash
sudo cp /home/deploy/agency-os/deploy/nginx.conf.example /etc/nginx/sites-available/agency-os.conf
sudo ln -sf /etc/nginx/sites-available/agency-os.conf /etc/nginx/sites-enabled/agency-os.conf
sudo nginx -t
sudo systemctl reload nginx
```

Critical nginx block:

```nginx
location /api/v1/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 6) Deploy Backend API

First-time/manual:

```bash
cd /home/deploy/agency-os
./scripts/prod-deploy-api.sh
.venv/bin/alembic upgrade head
```

Verify:

```bash
curl -fsS http://127.0.0.1:8000/health
./scripts/prod-verify-waitlist.sh
```

Expected health JSON includes `"status": "ok"` or `"status": "degraded"`.

## 7) Automated Deployment (GitHub Actions)

Repository secrets required:

- `DEPLOY_HOST`
- `DEPLOY_SSH_KEY`
- `DEPLOY_DOMAIN`
- `DEPLOY_SLACK_WEBHOOK` (optional)

On push to `main`, deploy workflow:

1. Backs up current state (`./scripts/pre-deploy-backup.sh backups`)
2. Syncs to `origin/main`
3. Installs dependencies
4. Runs `alembic upgrade head`
5. Restarts `agency-os-api`
6. Rebuilds and restarts the production `site` container
7. Verifies health and waitlist endpoints
8. Auto-rolls back to previous commit if public health fails

## 8) Deployment Checklist (Operator)

- [ ] DNS records exist for chosen topology
- [ ] `/etc/agency-os/api.env` created and secrets populated
- [ ] Database reachable (`DATABASE_URL`) and migrations applied
- [ ] Site built and published (or standalone container running)
- [ ] Reverse proxy config loaded (Caddy or nginx) and TLS valid
- [ ] `https://<domain>/` returns 200/308
- [ ] API health endpoint returns healthy status
- [ ] Signup smoke test succeeds (creates tenant + API key)

Signup/API smoke test:

```bash
curl -fsS -X POST "https://api.<domain>/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"email":"deploy-smoke@example.com","company_name":"Deploy Smoke Co","name":"Deploy Smoke"}'
```

For same-origin nginx topology, call:

```bash
curl -fsS -X POST "https://<domain>/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"email":"deploy-smoke@example.com","company_name":"Deploy Smoke Co","name":"Deploy Smoke"}'
```

## 9) Troubleshooting

Service logs:

```bash
sudo journalctl -u agency-os-api -n 200 --no-pager
```

Local API probe:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Public API probe:

- Topology A: `curl -fsS https://api.<domain>/health`
- Topology B: `curl -fsS -X POST "https://<domain>/api/v1/waitlist" -H "Content-Type: application/json" -d '{"email":"probe@example.com"}'`

If local health is OK but public health fails, inspect proxy config, DNS, and TLS.

## 10) Waitlist Storage Verification

`POST /api/v1/waitlist` persists to `waitlist` with:

- `email`
- `signed_up_at`
- `ip_hash` (SHA-256 hash of client IP)

Postgres verification:

```bash
psql "$DATABASE_URL" -c "SELECT email, signed_up_at, ip_hash FROM waitlist ORDER BY signed_up_at DESC LIMIT 10;"
```

SQLite verification:

```bash
sqlite3 "${DATABASE_PATH:-/var/lib/agency-os/agency_os.db}" "SELECT email, signed_up_at, ip_hash FROM waitlist ORDER BY signed_up_at DESC LIMIT 10;"
```
