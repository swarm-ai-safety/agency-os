#!/usr/bin/env bash
#
# Database backup script for agency-os SQLite database
# Usage: ./scripts/backup-database.sh [backup-dir]
#
# Creates timestamped backup using SQLite .backup command
# Implements 30-day retention policy
# Logs to stdout for monitoring integration
#

set -euo pipefail

# Configuration
DB_FILE="${DB_FILE:-agency_os.db}"
BACKUP_DIR="${1:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/agency_os-${TIMESTAMP}.db"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Check database file exists
if [[ ! -f "${DB_FILE}" ]]; then
    echo "ERROR: Database file ${DB_FILE} not found" >&2
    exit 1
fi

# Create backup using SQLite .backup command (ACID-compliant, safe during writes)
echo "Starting backup: ${DB_FILE} -> ${BACKUP_FILE}"
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
else
    echo "WARN: sqlite3 not found, falling back to file copy"
    cp "${DB_FILE}" "${BACKUP_FILE}"
fi

# Verify backup file was created and has content
if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file ${BACKUP_FILE} was not created" >&2
    exit 1
fi

BACKUP_SIZE=$(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null)
if [[ "${BACKUP_SIZE}" -eq 0 ]]; then
    echo "ERROR: Backup file ${BACKUP_FILE} is empty" >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

echo "Backup successful: ${BACKUP_FILE} ($(numfmt --to=iec-i --suffix=B ${BACKUP_SIZE} 2>/dev/null || echo ${BACKUP_SIZE} bytes))"

# Retention policy: delete backups older than RETENTION_DAYS
echo "Applying retention policy: ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name "agency_os-*.db" -type f -mtime +${RETENTION_DAYS} -delete

# Summary
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "agency_os-*.db" -type f | wc -l | tr -d ' ')
echo "Retention complete: ${BACKUP_COUNT} backups in ${BACKUP_DIR}"
