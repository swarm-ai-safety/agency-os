# Operations Runbook

## Overview

Agency-OS includes automated operational health monitoring and recovery systems. This runbook documents monitoring capabilities, alerting thresholds, and response procedures.

## Monitoring Systems

### 1. API Error Tracking

**What it monitors**: HTTP 5xx error rate across all API endpoints

**Configuration**:
- Window: 5 minutes (300 seconds)
- Alert threshold: 10% error rate
- Minimum requests: 10
- Cooldown: 60 seconds between alerts

**Access**: `GET /health/detailed` → `errors` field

**Alert format**:
```
ERROR RATE ALERT: 15.2% errors in last 300s (23/151 requests)
```

**Response procedure**:
1. Check application logs for stack traces
2. Verify database connectivity (`GET /health/detailed` → `checks.database`)
3. Check Stripe API reachability (`checks.stripe`)
4. Review recent deployments or configuration changes
5. If persistent, scale down traffic or rollback

### 2. Run Failure Tracking

**What it monitors**: Paperclip agent run failure rate

**Configuration**:
- Window: 1 hour (3600 seconds)
- Alert threshold: 15% failure rate
- Minimum runs: 5
- Cooldown: 5 minutes between alerts

**Access**: `GET /health/detailed` → `run_failures` field

**Alert format**:
```
RUN FAILURE RATE ALERT: 38.9% failures in last 3600s (272/709 runs)
```

**Response procedure**:
1. Check Paperclip dashboard for failing agents
2. Review agent logs for common failure patterns
3. Check if specific issue types are causing failures
4. Investigate stale execution locks (`cleanup_stale_locks` job should auto-resolve)
5. If budget-related, verify agent spending limits
6. If API-related, check Paperclip API health

**Cost impact**: High failure rates waste budget. At 38.86% failure rate:
- Estimated waste: $325.62/month (based on 272/709 failures)
- Action: Reduce failure rate to <15% to minimize waste

### 3. Uptime Tracking

**What it monitors**: Application uptime since last restart

**Access**: `GET /health/detailed` → `uptime` field

**Fields**:
- `started_at`: ISO timestamp when app started
- `uptime_seconds`: Seconds since startup
- `uptime_human`: Human-readable duration (e.g., "2d 14h 32m 15s")

## Logging Configuration and Rotation

### Runtime Logging Configuration

The API and worker both use centralized logging configuration on startup.

**Environment variables**:
- `LOG_LEVEL` (default: `INFO`)
- `LOG_JSON` (default: `true`; set `false`/`0`/`no` for human-readable logs)

**Correlation**:
- Every API request gets an `X-Request-ID` (existing header preserved if provided).
- Request-scoped logs include `request_id` so API, middleware, and business-logic logs can be correlated.

### Docker Log Rotation (Required in Production)

Containers log to stdout/stderr. Configure Docker daemon log rotation to prevent unbounded disk growth.

Example `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
```

After updating daemon config, restart Docker and verify with:

```bash
docker info | rg -n "Logging Driver"
docker inspect <container> | rg -n "max-size|max-file|LogConfig"
```

## Health Checks

### Database Connectivity (`checks.database`)

**What it checks**: Database responds to `SELECT 1` query

**Failure symptoms**:
- All API endpoints returning 500
- "Database connection failed" errors in logs

**Response**:
1. Verify `DATABASE_URL` (or fallback `DATABASE_PATH`) is set correctly
2. Check database file permissions
3. Check disk space
4. Restart application if persistent

### Database Schema (`checks.database_tables`)

**What it checks**: Critical tables exist (tenants, organizations, tasks, metering_events)

**Failure symptoms**:
- API works but specific endpoints fail with "table not found"

**Response**:
1. Run `alembic upgrade head` to apply missing migrations
2. Check for schema drift: `alembic check`
3. See "Database Schema Drift" section below

### Stripe Reachability (`checks.stripe`)

**What it checks**: Stripe API key is configured

**Failure symptoms**:
- Checkout endpoints return 500
- "Stripe not configured" errors

**Response**:
1. Verify STRIPE_SECRET_KEY environment variable is set
2. Test key with `stripe balance retrieve`
3. Check Stripe dashboard for API outages

### LLM Provider (`checks.llm_provider`)

**What it checks**: Anthropic provider is registered in gateway

**Failure symptoms**:
- Gateway endpoints fail with "provider not found"

**Response**:
1. Verify ANTHROPIC_API_KEY environment variable is set
2. Check Anthropic API status page
3. Verify provider_registry initialization in app.py

## Automated Jobs

### Startup Lock Reconciliation

**Frequency**: Once per API startup/restart

**What it does**: Clears all issue `executionRunId` and `checkoutRunId` locks via Paperclip release calls before recurring jobs begin.

**Logs**:
- `Releasing startup lock(s) on issue ZERA-123 (execution:..., checkout:...)`
- `Cleared N lock(s) across M issue(s) during startup reconciliation`

**Why it's needed**: Server restarts can invalidate in-flight run JWTs and leave orphaned locks that block future checkouts.

### Run Statistics Polling

**Frequency**: Every 5 minutes

**What it does**: Queries Paperclip API for run outcome statistics and records them in RunFailureTracker for alerting

**Logs**: `Successfully polled Paperclip dashboard: {...}`

**Failure handling**: Non-blocking. Logs warning and records API error in `run_failures.last_api_error`

### Stale Lock Cleanup

**Frequency**: Every 10 minutes

**What it does**: Finds issues with executionRunId or checkoutRunId locks older than 15 minutes and releases them via Paperclip API

**Logs**:
- `Starting stale lock cleanup (cutoff: 2026-03-08T03:20:00+00:00)`
- `Releasing stale execution lock on issue ZERA-123 (locked since ...)`
- `Released N stale lock(s)`

**Why it's needed**: Crashed agent runs can leave issues locked indefinitely, blocking other agents from picking up work

**Manual trigger**: Restart the application (cleanup runs on startup and every 10 minutes thereafter)

**Monitoring**: Check logs for `Released N stale lock(s)` messages. If N > 5 consistently, investigate root cause of crashes.

### Orphaned Run Lock Reconciliation

**Frequency**: Every 10 minutes (configurable)

**What it does**: Scans open issues with `executionRunId`/`checkoutRunId`, compares lock run IDs to the issue run history, and releases locks that reference missing runs.

**Logs**:
- `Starting orphaned run lock reconciliation`
- `Releasing orphaned run lock(s) on issue ZERA-123 (execution:<run-id>)`
- `Reconciled orphaned run locks on N issue(s)`

**Configuration**:
- `PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_ENABLED` (default: `true`)
- `PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_MINUTES` (default: `10`)

**Monitoring**:
- `/health/detailed` -> `orphaned_lock_reconciliation`
- `/metrics`:
  - `agency_os_orphaned_run_locks_reconciled_total`
  - `agency_os_orphaned_lock_reconciliations_total`
  - `agency_os_orphaned_lock_reconciliation_last_timestamp_seconds`

### Queued Run Timeout Cleanup

**Frequency**: Every 2 minutes

**What it does**: Detects issues whose `activeRun.status` is `queued` for longer than 5 minutes (configurable) and releases the issue lock so work does not stay blocked indefinitely.

**Logs**:
- `Starting queued run timeout cleanup (cutoff: ...)`
- `Cancelling timed-out queued run <run-id> on issue ZERA-123 (queued since ...)`
- `Cancelled N timed-out queued run(s)`

**Configuration**:
- `PAPERCLIP_QUEUED_RUN_TIMEOUT_MINUTES` (default: `5`)

**Why it's needed**: Runs that never leave queued state can hold execution locks forever and starve assigned work.

### Blocked Task Escalation SLA

**Goal**: Prevent blocked-task wake loops while preserving timely escalation.

**Policy**:
- Do not post repeated blocked comments unless new context appears.
- New context means at least one of:
  - issue status changed since last blocked update
  - a new comment from another author
  - an explicit wake trigger tied to a new comment
- Escalate blocked work to manager if unresolved for 2 hours.

**Dedup key**:
- `issue_id + status + latest_comment_id + updated_at`
- If key is unchanged, suppress duplicate blocked updates.

**Escalation window**:
- Warning: 60 minutes blocked
- Escalate: 120 minutes blocked
- Re-escalate only when new context arrives or every 24 hours

**Operator checklist**:
1. Confirm blocker is still active.
2. Verify no new context since last blocked comment.
3. If no new context and SLA window not reached, do not comment again.
4. If SLA breached, post escalation update with owner needed to unblock.

### Governance Policy Rollout + Rollback

**Goal**: Ship governance changes safely with explicit versioning and rollback points.

**API workflow**:
1. Create versioned policy update:
   - `PATCH /api/v1/orgs/{org_id}/governance`
   - Use `rollout_strategy=canary` and `canary_percent` for staged rollout
2. Promote canary:
   - `POST /api/v1/orgs/{org_id}/governance/promote`
3. Roll back:
   - `POST /api/v1/orgs/{org_id}/governance/rollback`
   - Optional `target_version` to pin rollback destination

**Audit requirements**:
- Every policy change emits immutable audit events:
  - `governance.policy.versioned`
  - `governance.policy.promoted`
  - `governance.policy.rolled_back`
- Store org id, policy version, previous version, rollout state, and overrides in event detail.

**Game-day drill (monthly)**:
1. Create a canary governance update on a non-production tenant.
2. Validate policy version increment and rollout status.
3. Promote canary, verify status transitions to active.
4. Roll back to previous version, verify policy restoration.
5. Confirm all three audit events exist and are timestamp-ordered.

## Common Operational Issues

### Agent Workspace Contamination

**Symptoms**: Unrelated modified files appear during a heartbeat, agents interfere with each other's local state, or commits include cross-agent edits.

**Standard fix**: Run each agent in a dedicated git worktree (never shared root workspace).

**Reference**: See [docs/agent-worktree-isolation.md](agent-worktree-isolation.md) for setup and lifecycle.

**Quick commands**:
```bash
scripts/agent-worktree.sh create coo
scripts/agent-worktree.sh env coo
scripts/agent-worktree.sh list
```

### High Run Failure Rate (>15%)

**Symptoms**: RUN FAILURE RATE ALERT in logs, wasted budget

**Investigation**:
1. Check `/health/detailed` → `run_failures.window_failure_rate`
2. Check `/health/detailed` → `run_failures.last_api_error` for API issues
3. Review Paperclip dashboard for specific failing agents
4. Check agent logs for common error patterns

**Common causes**:
- Paperclip API downtime or rate limiting
- Agent configuration errors (bad AGENTS.md, missing dependencies)
- Budget exhaustion (agents paused mid-run)
- Database schema drift (see below)

**Resolution**:
- Fix identified root cause
- Monitor `run_failures.window_failure_rate` until <15%
- If API-related, wait for Paperclip recovery (tracker will auto-resume)

### Database Schema Drift

**Symptoms**: "table does not exist" or "column not found" errors

**Detection**: Run `alembic check` to detect drift

**Resolution**:
1. Generate migration: `alembic revision --autogenerate -m "Fix schema drift"`
2. Review migration SQL carefully (especially FK constraints on existing data)
3. Test on dev database: `alembic upgrade head`
4. Apply to production after validation
5. Verify: `alembic check` should report no drift

**Prevention**: Add `alembic check` to CI pipeline to block PRs with drift

### Stale Execution Locks

**Symptoms**: Agents report "409 Conflict" when checking out issues, issues stuck in `in_progress` with no active run

**Detection**: Check Paperclip dashboard for issues with `executionLockedAt` > 15 minutes ago

**Automatic resolution**: The `cleanup_stale_locks` job runs every 10 minutes and auto-releases locks older than 15 minutes

**Manual resolution** (if job is disabled or failing):
```bash
# Standard release path (agent/run-scoped unlock):
curl -X POST \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/issues/{issue_id}/release"

# Emergency board/admin override for stuck ownership conflicts:
curl -X POST \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  "$PAPERCLIP_API_URL/api/issues/{issue_id}/force-release"
```

Use `force-release` only for manual intervention when normal release cannot
clear a stuck execution lock. This action is audited in Paperclip.

### Application Crashes or Restarts

**Detection**: `uptime.uptime_seconds` resets to low value

**Investigation**:
1. Check application logs for unhandled exceptions before restart
2. Check system logs (journalctl, container logs) for OOM kills or signals
3. Review recent deployments

**Common causes**:
- Unhandled exception in request handler
- OOM (out of memory) if metering data accumulates
- Database lock timeout
- Missing required environment variables

## Metrics to Monitor

### Critical (alert immediately)

- `checks.database.healthy` → false
- `run_failures.window_failure_rate` > 0.15 (15%)
- `errors.window_error_rate` > 0.10 (10%)

### Warning (investigate within 1 hour)

- `run_failures.window_failure_rate` > 0.10 (10%)
- `errors.window_error_rate` > 0.05 (5%)
- `run_failures.last_api_error` is not null
- `uptime_seconds` < 300 (recent restart)

### Informational

- `run_failures.total_runs` (throughput)
- `run_failures.total_failures` (cumulative failures)
- `errors.total_requests` (API traffic)
- `uptime.uptime_human` (stability)

## Adding New Health Checks

Health checks are registered in `app.py` during `create_app()`:

```python
health_check.register_check("my_check", lambda: my_check_function())
```

Check functions should return `bool` (True = healthy, False = unhealthy).

## Prometheus Metrics (Optional)

To export metrics in Prometheus format, implement `GET /metrics` endpoint:

```python
@app.get("/metrics")
async def metrics() -> Response:
    output = []

    # Run failures
    stats = run_failure_tracker.stats()
    output.append(f"run_failure_rate {stats['window_failure_rate']}")
    output.append(f"run_failures_total {stats['total_failures']}")
    output.append(f"runs_total {stats['total_runs']}")

    # API errors
    error_stats = error_tracker.stats()
    output.append(f"api_error_rate {error_stats['window_error_rate']}")
    output.append(f"api_errors_total {error_stats['total_errors']}")
    output.append(f"api_requests_total {error_stats['total_requests']}")

    # Uptime
    uptime_info = uptime_tracker.info()
    output.append(f"uptime_seconds {uptime_info['uptime_seconds']}")

    return Response(content="\n".join(output), media_type="text/plain")
```

Then configure Prometheus to scrape `http://your-api/metrics` every 30s.

## Emergency Contacts

- **Application owner**: Check CODEOWNERS or git log
- **Paperclip support**: https://github.com/anthropics/claude-code/issues (for Paperclip API issues)
- **Stripe support**: https://support.stripe.com (for billing/payment issues)

## Maintenance Windows

**Recommended**: Deploy during low-traffic periods (weekends, off-hours)

**Pre-deployment checklist**:
1. Run `alembic check` to verify no schema drift
2. Run test suite: `pytest tests/`
3. Check `/health/detailed` on current production instance
4. Verify environment variables are set in new environment
5. Have rollback plan ready

**Post-deployment verification**:
1. Check `/health` returns `{"status": "ok"}`
2. Check `/health/detailed` for all checks passing
3. Monitor logs for 10 minutes for errors or alerts
4. Verify scheduled jobs started: look for "Scheduled jobs started" log

## Troubleshooting Decision Tree

```
Start: Application not responding
├─ Can reach /health?
│  ├─ No → Check if process is running, check network/firewall
│  └─ Yes → Check /health/detailed
│     ├─ checks.database = false → See "Database Connectivity" section
│     ├─ checks.stripe = false → See "Stripe Reachability" section
│     ├─ errors.window_error_rate > 0.10 → See "High Error Rate" investigation
│     └─ run_failures.window_failure_rate > 0.15 → See "High Run Failure Rate" section
│
Start: Agents stuck, can't checkout issues
├─ Check Paperclip dashboard for executionLockedAt timestamps
│  ├─ Locks < 15 min old → Wait for agent run to complete
│  └─ Locks > 15 min old → See "Stale Execution Locks" section
│
Start: High costs / wasted budget
├─ Check /health/detailed → run_failures
│  └─ window_failure_rate > 0.15 → See "High Run Failure Rate" section
```
