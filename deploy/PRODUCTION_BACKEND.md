# FastAPI Production Deployment (zero-human-labs.com)

This runbook deploys the FastAPI backend on the production host so Caddy can proxy `https://api.zero-human-labs.com` to `127.0.0.1:8000`.

## 1) Sync code on server

```bash
sudo mkdir -p /opt/agency-os
sudo chown -R "$USER":"$USER" /opt/agency-os
cd /opt/agency-os
git pull --rebase
```

## 2) Configure API environment

```bash
sudo mkdir -p /etc/agency-os /var/lib/agency-os
sudo cp deploy/systemd/api.env.example /etc/agency-os/api.env
sudo chmod 600 /etc/agency-os/api.env
```

Edit `/etc/agency-os/api.env` and set:
- `DATABASE_URL` (recommended): `postgresql+psycopg://user:pass@host:5432/dbname`
- `SQLALCHEMY_POOL_SIZE` (optional; default `5`)
- `SQLALCHEMY_MAX_OVERFLOW` (optional; default `10`)
- `DATABASE_PATH` (fallback only when `DATABASE_URL` is unset; default `/var/lib/agency-os/agency_os.db`)
- `CORS_ORIGINS` (must include `https://zero-human-labs.com`)

Optional (only needed for related features):
- `ANTHROPIC_API_KEY` for gateway LLM endpoints
- `STRIPE_SECRET_KEY` for billing endpoints

## 3) Database migrations

Migrations run automatically on every deployment:

- **Docker Compose**: The `migrate` init service runs `alembic upgrade head` before the API starts. If it fails, the API and worker will not start.
- **Systemd**: `ExecStartPre` in the service unit runs `alembic upgrade head` before uvicorn. If it fails, the service won't start.

No manual `alembic upgrade head` or SSH is required.

To verify migration status after deployment:

```bash
curl -s http://127.0.0.1:8000/health/detailed | jq '.migration_version'
```

## 4) Install and start systemd service

```bash
cd /opt/agency-os
./scripts/prod-deploy-api.sh
sudo systemctl status agency-os-api --no-pager
```

The service listens on `127.0.0.1:8000`.

## 5) Configure Caddy (host-installed)

Use [`deploy/caddy/Caddyfile.host.example`](./caddy/Caddyfile.host.example) as the baseline for `/etc/caddy/Caddyfile`.

Critical API block:

```caddy
api.zero-human-labs.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then validate and reload:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 6) Verify endpoint

Local backend:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

Public endpoint:

```bash
./scripts/prod-verify-waitlist.sh
```

What this script now checks:
- DNS resolution for `api.zero-human-labs.com` (when `getent` is available)
- Local backend `/health` and local waitlist POST on `127.0.0.1:8000`
- Public `/health` and public waitlist POST via Caddy/TLS
- HTTP status code and response body for each step

Expected response:

```json
{"status":"ok"}
```

## 7) Where waitlist signups are stored

`POST /api/v1/waitlist` persists to the `waitlist` table with:

- `email` (primary key)
- `signed_up_at` (unix timestamp)
- `ip_hash` (SHA-256 hash of client IP)

Backend selection:

- `DATABASE_URL` set: writes to that database (typically Postgres in production).
- `DATABASE_URL` unset: falls back to SQLite at `DATABASE_PATH` (default `/var/lib/agency-os/agency_os.db`).

Verify in Postgres:

```bash
psql "$DATABASE_URL" -c "SELECT email, signed_up_at, ip_hash FROM waitlist ORDER BY signed_up_at DESC LIMIT 10;"
```

Verify in SQLite:

```bash
sqlite3 "${DATABASE_PATH:-/var/lib/agency-os/agency_os.db}" "SELECT email, signed_up_at, ip_hash FROM waitlist ORDER BY signed_up_at DESC LIMIT 10;"
```
