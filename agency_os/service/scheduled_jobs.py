"""Background scheduled jobs for operational health monitoring and cleanup."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

if TYPE_CHECKING:
    from agency_os.monitoring import RunFailureTracker
    from agency_os.storage import Database

logger = logging.getLogger("agency_os.scheduled_jobs")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class OrphanedLockReconciliationMetrics:
    """Thread-safe counters for orphaned lock reconciliation telemetry."""

    reconciled_locks_total: int = 0
    reconciled_issues_total: int = 0
    last_reconciliation_timestamp: float | None = None


@dataclass
class QueuedRunTimeoutMetrics:
    """Thread-safe counters for queued run timeout cleanup telemetry."""

    timed_out_runs_total: int = 0
    timed_out_issues_total: int = 0
    last_timeout_timestamp: float | None = None


@dataclass
class WorkspaceDriftMetrics:
    """Thread-safe counters for workspace configuration drift detection."""

    scanned_workspaces_total: int = 0
    drifted_workspaces_total: int = 0
    last_scan_timestamp: float | None = None


_orphaned_lock_metrics = OrphanedLockReconciliationMetrics()
_orphaned_lock_metrics_lock = threading.Lock()
_queued_run_timeout_metrics = QueuedRunTimeoutMetrics()
_queued_run_timeout_metrics_lock = threading.Lock()
_workspace_drift_metrics = WorkspaceDriftMetrics()
_workspace_drift_metrics_lock = threading.Lock()


def record_orphaned_lock_reconciliation(
    *, reconciled_locks: int, reconciled_issues: int, timestamp: float | None = None
) -> None:
    """Update process-local orphaned lock reconciliation metrics."""
    ts = timestamp if timestamp is not None else datetime.now(timezone.utc).timestamp()
    with _orphaned_lock_metrics_lock:
        _orphaned_lock_metrics.reconciled_locks_total += max(0, reconciled_locks)
        _orphaned_lock_metrics.reconciled_issues_total += max(0, reconciled_issues)
        _orphaned_lock_metrics.last_reconciliation_timestamp = ts


def get_orphaned_lock_reconciliation_metrics() -> dict[str, object]:
    """Return a snapshot of orphaned lock reconciliation metrics."""
    with _orphaned_lock_metrics_lock:
        ts = _orphaned_lock_metrics.last_reconciliation_timestamp
        return {
            "reconciled_locks_total": _orphaned_lock_metrics.reconciled_locks_total,
            "reconciled_issues_total": _orphaned_lock_metrics.reconciled_issues_total,
            "last_reconciliation_timestamp": ts,
            "last_reconciliation_at": (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if ts is not None
                else None
            ),
        }


def reset_orphaned_lock_reconciliation_metrics() -> None:
    """Reset orphaned lock metrics (for app startup and tests)."""
    with _orphaned_lock_metrics_lock:
        _orphaned_lock_metrics.reconciled_locks_total = 0
        _orphaned_lock_metrics.reconciled_issues_total = 0
        _orphaned_lock_metrics.last_reconciliation_timestamp = None


def record_queued_run_timeouts(
    *, timed_out_runs: int, timed_out_issues: int, timestamp: float | None = None
) -> None:
    """Update process-local queued run timeout metrics."""
    ts = timestamp if timestamp is not None else datetime.now(timezone.utc).timestamp()
    with _queued_run_timeout_metrics_lock:
        _queued_run_timeout_metrics.timed_out_runs_total += max(0, timed_out_runs)
        _queued_run_timeout_metrics.timed_out_issues_total += max(0, timed_out_issues)
        _queued_run_timeout_metrics.last_timeout_timestamp = ts


def get_queued_run_timeout_metrics() -> dict[str, object]:
    """Return a snapshot of queued run timeout metrics."""
    with _queued_run_timeout_metrics_lock:
        ts = _queued_run_timeout_metrics.last_timeout_timestamp
        return {
            "timed_out_runs_total": _queued_run_timeout_metrics.timed_out_runs_total,
            "timed_out_issues_total": _queued_run_timeout_metrics.timed_out_issues_total,
            "last_timeout_timestamp": ts,
            "last_timeout_at": (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if ts is not None
                else None
            ),
        }


def reset_queued_run_timeout_metrics() -> None:
    """Reset queued run timeout metrics (for app startup and tests)."""
    with _queued_run_timeout_metrics_lock:
        _queued_run_timeout_metrics.timed_out_runs_total = 0
        _queued_run_timeout_metrics.timed_out_issues_total = 0
        _queued_run_timeout_metrics.last_timeout_timestamp = None


def record_workspace_drift_scan(
    *, scanned_workspaces: int, drifted_workspaces: int, timestamp: float | None = None
) -> None:
    """Update process-local workspace drift scan metrics."""
    ts = timestamp if timestamp is not None else datetime.now(timezone.utc).timestamp()
    with _workspace_drift_metrics_lock:
        _workspace_drift_metrics.scanned_workspaces_total += max(0, scanned_workspaces)
        _workspace_drift_metrics.drifted_workspaces_total += max(0, drifted_workspaces)
        _workspace_drift_metrics.last_scan_timestamp = ts


def get_workspace_drift_metrics() -> dict[str, object]:
    """Return a snapshot of workspace drift detection metrics."""
    with _workspace_drift_metrics_lock:
        ts = _workspace_drift_metrics.last_scan_timestamp
        return {
            "scanned_workspaces_total": _workspace_drift_metrics.scanned_workspaces_total,
            "drifted_workspaces_total": _workspace_drift_metrics.drifted_workspaces_total,
            "last_scan_timestamp": ts,
            "last_scan_at": (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if ts is not None
                else None
            ),
        }


def reset_workspace_drift_metrics() -> None:
    """Reset workspace drift metrics (for app startup and tests)."""
    with _workspace_drift_metrics_lock:
        _workspace_drift_metrics.scanned_workspaces_total = 0
        _workspace_drift_metrics.drifted_workspaces_total = 0
        _workspace_drift_metrics.last_scan_timestamp = None


class ScheduledJobsManager:
    """Manages background scheduled jobs for monitoring and cleanup."""

    def __init__(
        self,
        run_failure_tracker: RunFailureTracker,
        db: Database,
    ) -> None:
        self.run_failure_tracker = run_failure_tracker
        self.db = db
        self.paperclip_api_url = os.environ.get("PAPERCLIP_API_URL", "")
        self.paperclip_api_key = os.environ.get("PAPERCLIP_API_KEY", "")
        self.paperclip_company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
        self.paperclip_run_id = os.environ.get("PAPERCLIP_RUN_ID", "")
        self.stale_lock_ttl_minutes = int(
            os.environ.get("PAPERCLIP_STALE_LOCK_TTL_MINUTES", "15")
        )
        self.queued_run_timeout_minutes = int(
            os.environ.get("PAPERCLIP_QUEUED_RUN_TIMEOUT_MINUTES", "5")
        )
        self.orphaned_lock_reconciliation_enabled = _env_flag(
            "PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_ENABLED", default=True
        )
        self.orphaned_lock_reconciliation_minutes = int(
            os.environ.get("PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_MINUTES", "10")
        )
        self.workspace_drift_detection_enabled = _env_flag(
            "PAPERCLIP_WORKSPACE_DRIFT_DETECTION_ENABLED", default=True
        )
        self.workspace_drift_detection_minutes = int(
            os.environ.get("PAPERCLIP_WORKSPACE_DRIFT_DETECTION_MINUTES", "30")
        )
        self.workspace_drift_git_remote = os.environ.get(
            "PAPERCLIP_WORKSPACE_DRIFT_GIT_REMOTE", "origin"
        )
        # Track previous run counts to compute deltas
        self._prev_succeeded = 0
        self._prev_failed = 0
        self._run_success_statuses = {"completed", "success", "succeeded", "passed"}
        self._run_failure_statuses = {
            "failed",
            "error",
            "cancelled",
            "canceled",
            "timed_out",
            "timeout",
        }
        self._run_terminal_statuses = (
            self._run_success_statuses | self._run_failure_statuses
        )

    def _list_open_issues(self) -> list[dict]:
        """Fetch open issues from Paperclip API."""
        import httpx

        url = (
            f"{self.paperclip_api_url}/api/companies/{self.paperclip_company_id}/issues"
        )
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        params = {"status": "todo,in_progress,blocked"}
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items", payload)
            if isinstance(items, list):
                return cast(list[dict[str, Any]], items)
            return []
        return cast(list[dict[str, Any]], payload)

    def _release_issue(self, issue_id: str) -> None:
        """Release issue lock via standard Paperclip run-scoped endpoint.

        This scheduler intentionally uses ``/api/issues/{id}/release`` for
        automated cleanup. Manual emergency unlocks (board/admin initiated)
        are handled out-of-band via ``/api/issues/{id}/force-release`` in the
        Paperclip control plane.
        """
        import httpx

        release_url = f"{self.paperclip_api_url}/api/issues/{issue_id}/release"
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        if self.paperclip_run_id:
            headers["X-Paperclip-Run-Id"] = self.paperclip_run_id
        release_response = httpx.post(release_url, headers=headers, timeout=10.0)
        release_response.raise_for_status()

    def _list_issue_runs(self, issue_id: str) -> list[dict]:
        """Fetch run history for a specific issue."""
        import httpx

        url = f"{self.paperclip_api_url}/api/issues/{issue_id}/runs"
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items", payload)
            if isinstance(items, list):
                return cast(list[dict[str, Any]], items)
            return []
        return cast(list[dict[str, Any]], payload)

    def _list_company_runs(self, limit: int = 200) -> list[dict]:
        """Fetch run history for a company."""
        import httpx

        url = f"{self.paperclip_api_url}/api/companies/{self.paperclip_company_id}/runs"
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        response = httpx.get(
            url, headers=headers, params={"limit": limit}, timeout=30.0
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("runs") or payload
            if isinstance(items, list):
                return cast(list[dict[str, Any]], items)
            return []
        return cast(list[dict[str, Any]], payload)

    def _list_projects(self) -> list[dict]:
        """Fetch projects from Paperclip API."""
        import httpx

        url = f"{self.paperclip_api_url}/api/companies/{self.paperclip_company_id}/projects"
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items", payload)
            if isinstance(items, list):
                return cast(list[dict[str, Any]], items)
            return []
        return cast(list[dict[str, Any]], payload)

    def _list_project_workspaces(self, project_id: str) -> list[dict]:
        """Fetch workspaces for a project from Paperclip API."""
        import httpx

        url = f"{self.paperclip_api_url}/api/projects/{project_id}/workspaces"
        headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items", payload)
            if isinstance(items, list):
                return cast(list[dict[str, Any]], items)
            return []
        return cast(list[dict[str, Any]], payload)

    def _normalize_repo_url(self, repo_url: str) -> str:
        """Normalize repo URLs for robust drift comparisons."""
        normalized = repo_url.strip()
        if normalized.endswith(".git"):
            normalized = normalized[: -len(".git")]
        if normalized.startswith("git@"):
            host_and_path = normalized.split("@", 1)[1]
            if ":" in host_and_path:
                host, path = host_and_path.split(":", 1)
                normalized = f"https://{host}/{path}"
        parsed = urlparse(normalized)
        if parsed.scheme and parsed.netloc:
            host = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            return f"{host}{path}".lower()
        return normalized.rstrip("/").lower()

    def _workspace_remote_url(self, cwd: str) -> str | None:
        """Return git remote URL for a workspace path when available."""
        git_dir = os.path.join(cwd, ".git")
        if not os.path.isdir(cwd) or not os.path.exists(git_dir):
            return None
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", self.workspace_drift_git_remote],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        remote_url = result.stdout.strip()
        return remote_url or None

    def audit_workspace_configuration_drift(self) -> None:
        """Detect repoUrl drift between Paperclip workspace config and git remote."""
        if not self.workspace_drift_detection_enabled:
            logger.debug("Workspace drift detection disabled, skipping scan")
            return
        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping workspace drift scan"
            )
            return

        try:
            projects = self._list_projects()
            scanned = 0
            drifted = 0

            for project in projects:
                project_id = project.get("id")
                if not isinstance(project_id, str) or not project_id:
                    continue
                workspaces: list[dict[str, Any]] = []
                project_workspaces = project.get("workspaces")
                if isinstance(project_workspaces, list):
                    workspaces = cast(list[dict[str, Any]], project_workspaces)
                else:
                    try:
                        workspaces = self._list_project_workspaces(project_id)
                    except Exception as workspace_error:
                        logger.warning(
                            "Failed to list workspaces for project %s: %s",
                            project.get("name", project_id),
                            workspace_error,
                        )
                        continue

                for workspace in workspaces:
                    cwd = workspace.get("cwd")
                    repo_url = workspace.get("repoUrl")
                    if not isinstance(cwd, str) or not isinstance(repo_url, str):
                        continue
                    remote_url = self._workspace_remote_url(cwd)
                    if remote_url is None:
                        continue

                    scanned += 1
                    if self._normalize_repo_url(repo_url) != self._normalize_repo_url(
                        remote_url
                    ):
                        drifted += 1
                        logger.warning(
                            "Workspace repoUrl drift detected (workspace=%s, configured=%s, actual=%s, cwd=%s)",
                            workspace.get("name") or workspace.get("id"),
                            repo_url,
                            remote_url,
                            cwd,
                        )

            record_workspace_drift_scan(
                scanned_workspaces=scanned, drifted_workspaces=drifted
            )
            if drifted > 0:
                logger.warning(
                    "Workspace drift scan complete: %d drifted of %d scanned",
                    drifted,
                    scanned,
                )
            else:
                logger.debug(
                    "Workspace drift scan complete: no drift across %d scanned workspace(s)",
                    scanned,
                )
        except Exception as e:
            logger.error("Failed to run workspace drift scan: %s", e)

    def _count_run_outcomes(self, runs: list[dict]) -> tuple[int, int]:
        """Count succeeded/failed runs from a list of run objects."""
        succeeded = 0
        failed = 0
        for run in runs:
            if not isinstance(run, dict):
                continue
            if "success" in run:
                if bool(run.get("success")):
                    succeeded += 1
                else:
                    failed += 1
                continue
            status = (
                str(run.get("status") or run.get("outcome") or run.get("result") or "")
                .strip()
                .lower()
            )
            if status in self._run_success_statuses:
                succeeded += 1
            elif status in self._run_failure_statuses:
                failed += 1
        return succeeded, failed

    def _extract_dashboard_run_totals(
        self, data: dict[str, Any]
    ) -> tuple[int, int] | None:
        """Extract cumulative succeeded/failed totals from dashboard payload."""
        candidates = [
            data.get("runs"),
            data.get("runStats"),
            (data.get("metrics") or {}).get("runs")
            if isinstance(data.get("metrics"), dict)
            else None,
        ]
        for block in candidates:
            if not isinstance(block, dict):
                continue
            succeeded = (
                block.get("succeeded") or block.get("success") or block.get("completed")
            )
            failed = block.get("failed") or block.get("errors")
            if isinstance(succeeded, int) and isinstance(failed, int):
                return succeeded, failed

            series = block.get("series")
            if isinstance(series, list):
                series_success, series_failed = self._count_run_outcomes(series)
                if series_success > 0 or series_failed > 0:
                    return series_success, series_failed
        return None

    def cleanup_stale_queued_runs(self) -> None:
        """Cancel queued runs older than timeout by releasing locked issues."""
        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping queued run timeout cleanup"
            )
            return

        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(
                minutes=self.queued_run_timeout_minutes
            )
            logger.info(
                "Starting queued run timeout cleanup (cutoff: %s)",
                cutoff_time.isoformat(),
            )

            issues = self._list_open_issues()
            cancelled_count = 0
            timed_out_runs_count = 0
            for issue in issues:
                active_run = issue.get("activeRun") or {}
                if active_run.get("status") != "queued":
                    continue

                issue_id = issue.get("id")
                queued_at = active_run.get("createdAt")
                if not issue_id or not queued_at:
                    continue

                queued_time = datetime.fromisoformat(queued_at.replace("Z", "+00:00"))
                if queued_time >= cutoff_time:
                    continue

                run_id = active_run.get("id") or issue.get("executionRunId")
                logger.warning(
                    "Cancelling timed-out queued run %s on issue %s (queued since %s)",
                    run_id,
                    issue.get("identifier", issue_id),
                    queued_at,
                )
                try:
                    self._release_issue(issue_id)
                except Exception as release_error:
                    logger.warning(
                        "Failed to release timed-out queued run lock on issue %s: %s",
                        issue.get("identifier", issue_id),
                        release_error,
                    )
                    continue
                cancelled_count += 1
                timed_out_runs_count += 1

            record_queued_run_timeouts(
                timed_out_runs=timed_out_runs_count,
                timed_out_issues=cancelled_count,
            )

            if cancelled_count > 0:
                logger.info("Cancelled %d timed-out queued run(s)", cancelled_count)
            else:
                logger.debug("No timed-out queued runs found")

        except Exception as e:
            logger.error("Failed to cleanup timed-out queued runs: %s", e)

    def poll_run_statistics(self) -> None:
        """Poll Paperclip API for run statistics and update tracker.

        This job runs periodically to fetch run outcome data from the
        Paperclip control plane and record it in the RunFailureTracker
        for monitoring and alerting.
        """
        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping run statistics poll"
            )
            return

        try:
            import httpx

            # Query dashboard endpoint for run statistics
            url = f"{self.paperclip_api_url}/api/companies/{self.paperclip_company_id}/dashboard"
            headers = {"Authorization": f"Bearer {self.paperclip_api_key}"}

            response = httpx.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            run_totals = self._extract_dashboard_run_totals(data)
            source = "dashboard"
            if run_totals is None:
                try:
                    company_runs = self._list_company_runs(limit=200)
                    run_totals = self._count_run_outcomes(company_runs)
                    source = "company_runs"
                except Exception as runs_error:
                    logger.warning(
                        "Company runs endpoint unavailable, falling back to per-issue run history: %s",
                        runs_error,
                    )
                    issues = self._list_open_issues()
                    issue_runs: list[dict] = []
                    for issue in issues:
                        issue_id = issue.get("id")
                        if not issue_id:
                            continue
                        try:
                            issue_runs.extend(self._list_issue_runs(issue_id))
                        except Exception as issue_error:
                            logger.debug(
                                "Skipping runs for issue %s due to API error: %s",
                                issue_id,
                                issue_error,
                            )
                    run_totals = self._count_run_outcomes(issue_runs)
                    source = "issue_runs"
            succeeded, failed = run_totals

            # Compute delta since last poll (only on subsequent polls)
            if self._prev_succeeded > 0 or self._prev_failed > 0:
                delta_succeeded = max(0, succeeded - self._prev_succeeded)
                delta_failed = max(0, failed - self._prev_failed)

                # Record individual run outcomes based on delta
                for _ in range(delta_failed):
                    self.run_failure_tracker.record(failure=True)
                for _ in range(delta_succeeded):
                    self.run_failure_tracker.record(failure=False)

                logger.debug(
                    "Recorded %d failures, %d successes (source=%s, total: %d/%d, rate: %.1f%%)",
                    delta_failed,
                    delta_succeeded,
                    source,
                    failed,
                    succeeded + failed,
                    (failed / (succeeded + failed) * 100.0)
                    if (succeeded + failed) > 0
                    else 0.0,
                )
            else:
                logger.debug(
                    "First poll - establishing baseline from %s (succeeded=%d, failed=%d)",
                    source,
                    succeeded,
                    failed,
                )

            # Update previous counts for next poll
            self._prev_succeeded = succeeded
            self._prev_failed = failed

        except Exception as e:
            error_msg = f"Failed to poll Paperclip API: {e}"
            logger.warning(error_msg)
            self.run_failure_tracker.record_api_error(error_msg)

    def cleanup_stale_locks(self) -> None:
        """Release stale execution and checkout locks on issues.

        Finds issues with executionRunId or checkoutRunId that are older
        than 15 minutes and releases them via the Paperclip API. This
        prevents agents from being permanently blocked by crashed runs.
        """
        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping lock cleanup"
            )
            return

        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(
                minutes=self.stale_lock_ttl_minutes
            )
            logger.info(
                "Starting stale lock cleanup (cutoff: %s)", cutoff_time.isoformat()
            )

            issues = self._list_open_issues()

            released_count = 0
            for issue in issues:
                issue_id = issue.get("id")
                if not issue_id:
                    continue

                stale_lock = None
                execution_locked_at = issue.get("executionLockedAt")
                checkout_locked_at = issue.get("checkoutLockedAt")
                if execution_locked_at:
                    locked_time = datetime.fromisoformat(
                        execution_locked_at.replace("Z", "+00:00")
                    )
                    if locked_time < cutoff_time:
                        stale_lock = ("execution", execution_locked_at)
                if stale_lock is None and checkout_locked_at:
                    locked_time = datetime.fromisoformat(
                        checkout_locked_at.replace("Z", "+00:00")
                    )
                    if locked_time < cutoff_time:
                        stale_lock = ("checkout", checkout_locked_at)

                if stale_lock is None:
                    continue

                lock_type, locked_at = stale_lock
                logger.warning(
                    "Releasing stale %s lock on issue %s (locked since %s)",
                    lock_type,
                    issue.get("identifier", issue_id),
                    locked_at,
                )
                try:
                    self._release_issue(issue_id)
                except Exception as release_error:
                    logger.warning(
                        "Failed to release stale %s lock on issue %s: %s",
                        lock_type,
                        issue.get("identifier", issue_id),
                        release_error,
                    )
                    continue
                released_count += 1

            if released_count > 0:
                logger.info("Released %d stale lock(s)", released_count)
            else:
                logger.debug("No stale locks found")

        except Exception as e:
            logger.error("Failed to cleanup stale locks: %s", e)

    def cleanup_orphaned_run_locks(self) -> None:
        """Release stale locks with missing or detached run ownership.

        Reconciles:
        - orphaned locks whose run IDs are missing from issue run history
        - detached execution locks whose run is terminal but activeRun is null
        """
        if not self.orphaned_lock_reconciliation_enabled:
            logger.debug("Orphaned run lock reconciliation disabled, skipping cleanup")
            return

        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping orphaned run lock cleanup"
            )
            return

        try:
            logger.info("Starting orphaned run lock reconciliation")
            issues = self._list_open_issues()
            released_count = 0
            reconciled_locks_count = 0

            for issue in issues:
                issue_id = issue.get("id")
                if not issue_id:
                    continue

                execution_run_id = issue.get("executionRunId")
                checkout_run_id = issue.get("checkoutRunId")
                active_run = issue.get("activeRun")

                if not (execution_run_id or checkout_run_id):
                    continue

                try:
                    issue_runs = self._list_issue_runs(issue_id)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch issue run history for %s: %s",
                        issue.get("identifier", issue_id),
                        e,
                    )
                    continue

                issue_run_ids = {
                    str(run_id)
                    for run in issue_runs
                    for run_id in [run.get("runId") or run.get("id")]
                    if run_id
                }
                issue_run_statuses = {
                    str(run_id): str(status).lower()
                    for run in issue_runs
                    for run_id in [run.get("runId") or run.get("id")]
                    for status in [run.get("status")]
                    if run_id and status
                }
                active_run_is_present = bool(active_run)

                orphaned_locks = []
                if execution_run_id:
                    if str(execution_run_id) not in issue_run_ids:
                        orphaned_locks.append(("execution", execution_run_id))
                    else:
                        execution_status = issue_run_statuses.get(str(execution_run_id))
                        if (
                            not active_run_is_present
                            and execution_status in self._run_terminal_statuses
                        ):
                            orphaned_locks.append(
                                ("execution-detached", execution_run_id)
                            )
                if checkout_run_id:
                    if str(checkout_run_id) not in issue_run_ids:
                        orphaned_locks.append(("checkout", checkout_run_id))

                if not orphaned_locks:
                    continue

                orphaned_labels = ", ".join(
                    f"{lock_type}:{run_id}" for lock_type, run_id in orphaned_locks
                )
                logger.warning(
                    "Releasing orphaned run lock(s) on issue %s (%s)",
                    issue.get("identifier", issue_id),
                    orphaned_labels,
                )
                try:
                    self._release_issue(issue_id)
                except Exception as release_error:
                    logger.warning(
                        "Failed to release orphaned run lock(s) on issue %s: %s",
                        issue.get("identifier", issue_id),
                        release_error,
                    )
                    continue
                released_count += 1
                reconciled_locks_count += len(orphaned_locks)

            if released_count > 0:
                logger.info(
                    "Reconciled orphaned run locks on %d issue(s)", released_count
                )
            else:
                logger.debug("No orphaned run locks found")
            record_orphaned_lock_reconciliation(
                reconciled_locks=reconciled_locks_count,
                reconciled_issues=released_count,
            )

        except Exception as e:
            logger.error("Failed to reconcile orphaned run locks: %s", e)

    def clear_startup_execution_locks(self) -> None:
        """Clear all issue execution/checkout locks once at server startup."""
        if not all(
            [self.paperclip_api_url, self.paperclip_api_key, self.paperclip_company_id]
        ):
            logger.debug(
                "Paperclip API credentials not configured, skipping startup lock clear"
            )
            return

        try:
            issues = self._list_open_issues()
            released_count = 0
            cleared_lock_count = 0

            for issue in issues:
                issue_id = issue.get("id")
                if not issue_id:
                    continue

                execution_run_id = issue.get("executionRunId")
                checkout_run_id = issue.get("checkoutRunId")
                if not execution_run_id and not checkout_run_id:
                    continue

                lock_labels = []
                if execution_run_id:
                    lock_labels.append(f"execution:{execution_run_id}")
                if checkout_run_id:
                    lock_labels.append(f"checkout:{checkout_run_id}")

                logger.warning(
                    "Releasing startup lock(s) on issue %s (%s)",
                    issue.get("identifier", issue_id),
                    ", ".join(lock_labels),
                )
                try:
                    self._release_issue(issue_id)
                except Exception as release_error:
                    logger.warning(
                        "Failed to release startup lock(s) on issue %s: %s",
                        issue.get("identifier", issue_id),
                        release_error,
                    )
                    continue
                released_count += 1
                cleared_lock_count += len(lock_labels)

            if released_count > 0:
                logger.info(
                    "Cleared %d lock(s) across %d issue(s) during startup reconciliation",
                    cleared_lock_count,
                    released_count,
                )
            else:
                logger.debug("No startup execution locks found")

        except Exception as e:
            logger.error("Failed to clear startup execution locks: %s", e)

    # ------------------------------------------------------------------
    # Nurture email sequence (day 1 / 3 / 7)
    # ------------------------------------------------------------------

    def process_nurture_emails(self) -> None:
        """Send day-1/3/7 nurture emails to tenants who are due.

        Runs periodically. For each active tenant with an email:
        - Computes days since signup
        - Sends the nurture email for that day if not already sent
        - Skips opted-out tenants
        - Records sent emails in tenant metadata
        """
        from agency_os.service.email import NURTURE_DAYS, send_nurture_email

        if self.db is None:
            return

        try:
            tenants = self.db.list_tenants()
        except Exception as e:
            logger.error("Nurture job: failed to list tenants: %s", e)
            return

        now = time.time()
        sent_count = 0
        skipped_count = 0

        for tenant_row in tenants:
            if not tenant_row.get("active", True):
                continue
            meta = tenant_row.get("metadata") or {}
            email = meta.get("email")
            signed_up_at = meta.get("signed_up_at")
            if not email or not signed_up_at:
                continue
            if meta.get("email_opt_out"):
                continue

            try:
                signed_up_at_ts = float(signed_up_at)
            except (TypeError, ValueError):
                continue

            days_since_signup = (now - signed_up_at_ts) / 86400
            nurture_sent: list[int] = list(meta.get("nurture_emails_sent", []))
            nurture_sent_before = len(nurture_sent)

            for day in NURTURE_DAYS:
                if day in nurture_sent:
                    continue
                if days_since_signup < day:
                    break
                # Send the email
                tenant_id = tenant_row["tenant_id"]
                tenant_name = tenant_row.get("name", "there")
                try:
                    ok = send_nurture_email(email, tenant_name, tenant_id, day)
                except Exception:
                    logger.exception(
                        "Nurture job: failed to send day-%d email to %s",
                        day,
                        tenant_id,
                    )
                    continue
                if ok:
                    nurture_sent.append(day)
                    sent_count += 1
                    logger.info(
                        "Nurture day-%d email sent to tenant %s",
                        day,
                        tenant_id,
                    )
                else:
                    skipped_count += 1

            # Persist updated nurture state if anything changed
            if len(nurture_sent) > nurture_sent_before:
                meta["nurture_emails_sent"] = nurture_sent
                tenant_row["metadata"] = meta
                try:
                    self.db.save_tenant(tenant_row)
                except Exception:
                    logger.exception(
                        "Nurture job: failed to save metadata for %s",
                        tenant_row["tenant_id"],
                    )

        if sent_count or skipped_count:
            logger.info(
                "Nurture job complete: %d sent, %d skipped", sent_count, skipped_count
            )


def start_scheduled_jobs(
    run_failure_tracker: RunFailureTracker,
    db: Database,
) -> Any | None:
    """Start background scheduled jobs using APScheduler.

    Startup reconciliation:
    - Clear execution/checkout locks left behind by a server restart
    - Reconcile orphaned run locks
    - Cleanup timed-out queued runs
    - Cleanup stale locks
    - Audit workspace repoUrl drift

    Recurring jobs:
    - Poll run statistics: Every 5 minutes
    - Reconcile orphaned run locks: Every 10 minutes (configurable)
    - Cleanup timed-out queued runs: Every 2 minutes
    - Cleanup stale locks: Every 10 minutes
    - Audit workspace repoUrl drift: Every 30 minutes (configurable)
    - Process nurture emails: Every 60 minutes (configurable)
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        manager = ScheduledJobsManager(run_failure_tracker, db)
        scheduler = BackgroundScheduler()

        # Reconcile run locks once on startup before periodic polling.
        manager.clear_startup_execution_locks()
        manager.cleanup_orphaned_run_locks()
        manager.cleanup_stale_queued_runs()
        manager.cleanup_stale_locks()
        manager.audit_workspace_configuration_drift()

        # Poll run statistics every 5 minutes
        scheduler.add_job(
            manager.poll_run_statistics,
            "interval",
            minutes=5,
            id="poll_run_statistics",
            name="Poll Paperclip run statistics",
        )

        # Cleanup queued runs that are stuck beyond timeout
        scheduler.add_job(
            manager.cleanup_stale_queued_runs,
            "interval",
            minutes=2,
            id="cleanup_stale_queued_runs",
            name="Cleanup timed-out queued runs",
        )

        # Cleanup stale locks every 10 minutes
        scheduler.add_job(
            manager.cleanup_stale_locks,
            "interval",
            minutes=10,
            id="cleanup_stale_locks",
            name="Cleanup stale execution locks",
        )

        # Reconcile orphaned run locks every 10 minutes (configurable)
        if manager.orphaned_lock_reconciliation_enabled:
            scheduler.add_job(
                manager.cleanup_orphaned_run_locks,
                "interval",
                minutes=manager.orphaned_lock_reconciliation_minutes,
                id="cleanup_orphaned_run_locks",
                name="Reconcile orphaned run locks",
            )
        else:
            logger.info(
                "Skipping orphaned run lock reconciliation scheduler (disabled)"
            )

        # Audit workspace config drift every 30 minutes (configurable)
        if manager.workspace_drift_detection_enabled:
            scheduler.add_job(
                manager.audit_workspace_configuration_drift,
                "interval",
                minutes=manager.workspace_drift_detection_minutes,
                id="audit_workspace_configuration_drift",
                name="Audit workspace configuration drift",
            )
        else:
            logger.info("Skipping workspace drift scheduler (disabled)")

        # Process nurture emails every 60 minutes
        nurture_minutes = int(os.environ.get("NURTURE_JOB_INTERVAL_MINUTES", "60"))
        if _env_flag("NURTURE_JOB_ENABLED", default=True):
            scheduler.add_job(
                manager.process_nurture_emails,
                "interval",
                minutes=nurture_minutes,
                id="process_nurture_emails",
                name="Process day 1/3/7 nurture email sequence",
            )
        else:
            logger.info("Skipping nurture email scheduler (disabled)")

        scheduler.start()
        logger.info(
            "Scheduled jobs started (run stats: 5min, orphan reconciliation: %s, queued timeout: 2min, lock cleanup: 10min, workspace drift: %s)",
            (
                f"{manager.orphaned_lock_reconciliation_minutes}min"
                if manager.orphaned_lock_reconciliation_enabled
                else "disabled"
            ),
            (
                f"{manager.workspace_drift_detection_minutes}min"
                if manager.workspace_drift_detection_enabled
                else "disabled"
            ),
        )
        return scheduler

    except ImportError:
        logger.warning(
            "APScheduler not installed, scheduled jobs disabled. "
            "Install with: pip install 'agency-os[api]'"
        )
        return None
    except Exception as e:
        logger.error("Failed to start scheduled jobs: %s", e)
        return None


def stop_scheduled_jobs(scheduler: Any | None) -> None:
    """Stop APScheduler instance if one was started."""
    if scheduler is None:
        return
    shutdown = getattr(scheduler, "shutdown", None)
    if not callable(shutdown):
        return
    try:
        shutdown(wait=False)
    except TypeError:
        shutdown()
    except Exception as e:
        logger.warning("Failed to stop scheduled jobs: %s", e)
