# Database Migrations

## Overview

Agency-OS now uses a single schema authority:

1. **Alembic migrations** (`alembic/versions/`) - source of truth for schema changes
2. **SQLAlchemy models** (`agency_os/models.py`) - application-level schema definitions

`agency_os/storage.py` no longer creates tables with runtime DDL. On startup, `Database()` runs:

```bash
alembic upgrade head
```

against the configured `DATABASE_URL` (or `sqlite:///$DATABASE_PATH` by default).

## Environment Variables

- `DATABASE_URL`: primary SQLAlchemy connection string.
  - PostgreSQL format: `postgresql://user:pass@host:5432/dbname`
  - Recommended driver-explicit format: `postgresql+psycopg://user:pass@host:5432/dbname`
  - Default if unset: `sqlite:///$DATABASE_PATH`
- `DATABASE_PATH`: SQLite file path used when `DATABASE_URL` is not set (default `agency_os.db`).
- `SQLALCHEMY_POOL_SIZE`: connection pool size for non-SQLite databases (default `5`).
- `SQLALCHEMY_MAX_OVERFLOW`: extra temporary connections above pool size (default `10`).

## Operational Contract

- Every schema change must ship as an Alembic migration.
- App startup auto-applies pending migrations.
- `/health/detailed` includes `migration_version` from `alembic_version`.

## Migration Workflow

1. Update `agency_os/models.py`.
2. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "description"
   ```
3. Review/edit the generated file in `alembic/versions/`.
4. Apply and verify:
   ```bash
   alembic upgrade head
   alembic current
   ```
5. Run validation tests:
   ```bash
   pytest tests/unit/test_schema_validation.py -xvs
   ```

## PostgreSQL Setup (Production)

Recommended version: PostgreSQL 14+ (self-hosted or managed: RDS/Cloud SQL/Supabase).

Required extensions: none.

Required DB privileges for migration user: `CREATE`, `ALTER`, `DROP` on the target database.

### Local bootstrap example (Docker)

```bash
docker run --name agency-os-postgres \
  -e POSTGRES_USER=agency_os \
  -e POSTGRES_PASSWORD=change-me \
  -e POSTGRES_DB=agency_os \
  -p 5432:5432 -d postgres:16
```

Set env for API/worker:

```bash
export DATABASE_URL="postgresql+psycopg://agency_os:change-me@127.0.0.1:5432/agency_os"
export SQLALCHEMY_POOL_SIZE=10
export SQLALCHEMY_MAX_OVERFLOW=20
```

Apply schema:

```bash
alembic upgrade head
alembic current
```

## SQLite -> PostgreSQL Migration Guide

1. Stop writes to SQLite (maintenance window).
2. Create backup:
   ```bash
   cp agency_os.db agency_os.db.backup-$(date +%Y%m%d-%H%M%S)
   sqlite3 agency_os.db ".dump" > sqlite-backup.sql
   ```
3. Provision PostgreSQL and set `DATABASE_URL`.
4. Apply schema baseline with Alembic:
   ```bash
   alembic upgrade head
   ```
5. Dry-run migration plan + reconciliation:
   ```bash
   python scripts/migrate-sqlite-to-postgres.py \
     --sqlite-path agency_os.db \
     --postgres-url "$DATABASE_URL" \
     --dry-run \
     --report-path migration-report.dry-run.json
   ```
6. Execute import:
   ```bash
   python scripts/migrate-sqlite-to-postgres.py \
     --sqlite-path agency_os.db \
     --postgres-url "$DATABASE_URL" \
     --report-path migration-report.json
   ```
7. Run integrity checks before cutover.

### Integrity Checklist

- Row counts match per critical table: `tenants`, `organizations`, `tasks`, `metering_events`, `audit_log`.
- API smoke tests pass (`/health`, tenant auth, org create/list, task submit/status).
- `/health/detailed` reports a non-null `migration_version`.
- Tenant isolation tests pass.
- Background worker can read/write without connection errors.

## Rollback Procedure

Rollback one revision:

```bash
alembic downgrade -1
```

Rollback to a specific revision:

```bash
alembic downgrade <revision_id>
```

After rollback, verify app health and migration version:

```bash
alembic current
curl -s http://localhost:8000/health/detailed | jq '.migration_version'
```

## Migration Rerun Procedure

If an import fails partway through, keep the SQLite source as the source of truth and rerun with target truncation:

```bash
python scripts/migrate-sqlite-to-postgres.py \
  --sqlite-path agency_os.db \
  --postgres-url "$DATABASE_URL" \
  --truncate-target \
  --report-path migration-report.rerun.json
```

`--truncate-target` clears selected target tables and restarts identities before re-import, enabling deterministic retries.

## Troubleshooting

### Migration failed on startup

- Check migration history and current head:
  ```bash
  alembic history --verbose
  alembic current
  ```
- Resolve the failing revision, then rerun:
  ```bash
  alembic upgrade head
  ```

### Schema drift suspicion

- Run drift check:
  ```bash
  alembic check
  ```
- If drift is detected, generate and review a corrective migration.

### PostgreSQL connection refused

- Verify `DATABASE_URL` host/port/credentials.
- Confirm firewall/security-group rules allow app host to DB host.
- Validate DB is reachable:
  ```bash
  pg_isready -h <host> -p <port> -U <user> -d <dbname>
  ```

### Connection pool exhausted

- Symptoms: timeouts under load, intermittent DB errors.
- Increase:
  - `SQLALCHEMY_POOL_SIZE`
  - `SQLALCHEMY_MAX_OVERFLOW`
- Ensure long-lived transactions are not left open in app code.

### Migration failed

- Re-run with explicit URL and inspect logs:
  ```bash
  DATABASE_URL=postgresql+psycopg://... alembic upgrade head
  ```
- If a bad migration was partially applied:
  1. restore from DB backup, or
  2. `alembic downgrade -1` and re-apply after fixing the revision.

### SQLite local reset

```bash
rm -f agency_os.db
alembic upgrade head
```

## Notes

- Startup auto-migration is intended for app/runtime safety and local dev ergonomics.
- CI/deploy pipelines should still run `alembic upgrade head` explicitly before traffic cutover.
