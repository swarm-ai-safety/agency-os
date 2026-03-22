# Disaster Recovery

## Database Backup Strategy

Agency-OS uses SQLite for data persistence. All critical data (tenants, organizations, tasks, metering events, audit logs) is stored in `agency_os.db`.

### Automated Backups

**Backup Script**: `scripts/backup-database.sh`

```bash
# Manual backup
./scripts/backup-database.sh

# Custom backup directory
./scripts/backup-database.sh /path/to/backups

# Custom retention (days)
RETENTION_DAYS=60 ./scripts/backup-database.sh
```

**Schedule**: Recommended daily via cron:

```bash
# Add to crontab (daily at 2 AM)
0 2 * * * cd /path/to/agency-os && ./scripts/backup-database.sh >> logs/backup.log 2>&1
```

**Retention Policy**: 30 days by default (configurable via `RETENTION_DAYS` env var)

### Backup Location

- **Development**: `./backups/` (git-ignored)
- **Production**: Configure via Docker volume mount (see Docker section)

### Backup Verification

The backup script automatically:
1. Creates ACID-compliant backup using SQLite `.backup` command (safe during writes)
2. Verifies backup file exists and has non-zero size
3. Reports backup size in logs

Manual verification:

```bash
# Integrity check
sqlite3 backups/agency_os-YYYYMMDD-HHMMSS.db "PRAGMA integrity_check;"

# Table count verification
sqlite3 backups/agency_os-YYYYMMDD-HHMMSS.db ".tables"

# Row count check
sqlite3 backups/agency_os-YYYYMMDD-HHMMSS.db "SELECT COUNT(*) FROM tenants;"
```

## Restore Procedure

### Pre-Restore Checklist

- [ ] Stop application/API server (`systemctl stop agency-os` or `docker-compose down`)
- [ ] Verify backup file integrity (`PRAGMA integrity_check`)
- [ ] Create backup of current database (in case restore fails)
- [ ] Note current database size and table counts for comparison

### Restore Steps

```bash
# 1. Stop application
# Docker:
docker-compose down

# Systemd:
sudo systemctl stop agency-os

# 2. Backup current database (safety)
cp agency_os.db agency_os.db.pre-restore-$(date +%Y%m%d-%H%M%S)

# 3. Restore from backup
cp backups/agency_os-YYYYMMDD-HHMMSS.db agency_os.db

# 4. Verify restore
sqlite3 agency_os.db "PRAGMA integrity_check;"
sqlite3 agency_os.db "SELECT COUNT(*) FROM tenants;"

# 5. Restart application
docker-compose up -d
# OR
sudo systemctl start agency-os
```

### Post-Restore Verification

1. Check application logs for startup errors
2. Verify API health endpoints (`GET /health`, `GET /health/detailed`)
3. Test critical workflows (tenant login, task submission, billing)
4. Verify recent data exists (check latest tenant signup dates, task timestamps)

### Recovery Time Objective (RTO)

**Target**: < 15 minutes from decision to restore

- Stop app: ~30 seconds
- Backup current DB: ~5 seconds
- Restore from backup: ~5 seconds
- Restart app: ~30 seconds
- Verification: ~2 minutes

### Recovery Point Objective (RPO)

**Target**: 24 hours (daily backups)

**Data Loss Window**: Maximum 24 hours of data if restoring from previous day's backup

**Improvement**: For RPO < 1 hour, implement WAL archiving or incremental backups

## Docker Volume Configuration

### Production Deployment

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  api:
    image: agency-os:latest
    volumes:
      # Database persistence
      - db-data:/app/agency_os.db
      # Backup directory
      - backup-data:/app/backups
    environment:
      - DATABASE_PATH=/app/agency_os.db

volumes:
  db-data:
    driver: local
  backup-data:
    driver: local
    driver_opts:
      type: none
      device: /backup/agency-os  # Host path for backup access
      o: bind
```

### Backup from Docker Container

```bash
# Execute backup inside running container
docker-compose exec api ./scripts/backup-database.sh

# Copy backup to host
docker cp agency-os-api-1:/app/backups/agency_os-YYYYMMDD.db ./host-backups/

# Automated via cron (on Docker host)
0 2 * * * docker-compose -f /path/to/docker-compose.yml exec -T api ./scripts/backup-database.sh
```

## Monitoring & Alerting

### Backup Monitoring

Monitor backup script exit codes:

```bash
# Success: exit 0
# Failure: exit 1 with error message on stderr
```

**Alert on**:
- Backup script failures (exit code != 0)
- No new backups in 36 hours (missed backup window)
- Backup file size anomalies (< 50% or > 200% of average)

### Integration Examples

**Healthchecks.io**:

```bash
# Append to backup script or cron job
./scripts/backup-database.sh && curl -m 10 --retry 5 https://hc-ping.com/YOUR-UUID
```

**Email alerts** (via mailx):

```bash
./scripts/backup-database.sh 2>&1 | tee /tmp/backup.log
if [ $? -ne 0 ]; then
    mail -s "Agency-OS backup FAILED" ops@example.com < /tmp/backup.log
fi
```

## Failure Scenarios & Response

| Scenario | Detection | Response | RTO |
|----------|-----------|----------|-----|
| Database corruption | App startup failure, integrity check fail | Restore from latest backup | 15 min |
| Accidental data deletion | User report, audit log review | Restore from backup before deletion | 30 min |
| Hardware failure | Server unreachable | Provision new instance, restore from backup | 2 hours |
| Backup script failure | Monitoring alert, cron failure email | Investigate logs, manual backup if needed | 1 hour |
| Ransomware/malicious deletion | Anomaly detection, integrity check fail | Restore from off-site backup | 4 hours |

## Testing

**Disaster recovery testing cadence**: Quarterly

**Test checklist**:
- [ ] Restore from 1-day-old backup
- [ ] Restore from 7-day-old backup
- [ ] Restore from 30-day-old backup
- [ ] Verify data integrity post-restore
- [ ] Measure actual RTO
- [ ] Document any issues or improvements

## Off-Site Backup Strategy

**Current**: Backups stored locally only

**Recommended for production**:
1. Copy backups to S3/GCS/Azure Blob (encrypted at rest)
2. Separate AWS account or GCP project for isolation
3. Versioning enabled
4. Lifecycle policy: delete after 90 days
5. Test restore from off-site backup quarterly

**Example S3 sync** (add to backup script):

```bash
# After local backup succeeds
aws s3 cp "${BACKUP_FILE}" "s3://agency-os-backups/$(date +%Y/%m/)/" \
    --storage-class STANDARD_IA \
    --server-side-encryption AES256
```
