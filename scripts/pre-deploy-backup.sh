#!/usr/bin/env bash
#
# Pre-deployment backup helper.
# Usage: ./scripts/pre-deploy-backup.sh [backup-dir]
#
# If DATABASE_URL points to PostgreSQL, creates a timestamped pg_dump file.
# Otherwise falls back to the SQLite backup workflow.
#

set -euo pipefail

BACKUP_DIR="${1:-backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DATABASE_URL="${DATABASE_URL:-}"

mkdir -p "${BACKUP_DIR}"

if [[ "${DATABASE_URL}" == postgresql* ]]; then
    if ! command -v pg_dump >/dev/null 2>&1; then
        echo "ERROR: pg_dump is required for PostgreSQL backups" >&2
        exit 1
    fi

    BACKUP_FILE="${BACKUP_DIR}/agency_os-${TIMESTAMP}.sql.gz"
    echo "Starting PostgreSQL backup to ${BACKUP_FILE}"
    pg_dump "${DATABASE_URL}" --no-owner --no-privileges | gzip > "${BACKUP_FILE}"

    if [[ ! -s "${BACKUP_FILE}" ]]; then
        echo "ERROR: PostgreSQL backup file ${BACKUP_FILE} was not created" >&2
        exit 1
    fi

    echo "PostgreSQL backup successful: ${BACKUP_FILE}"
    exit 0
fi

echo "DATABASE_URL not set to PostgreSQL, running SQLite backup workflow"
exec ./scripts/backup-database.sh "${BACKUP_DIR}"
