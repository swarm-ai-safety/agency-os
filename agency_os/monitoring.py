"""Uptime monitoring and error alerting for Agency-OS."""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("agency_os.monitoring")


class ErrorTracker:
    """Sliding-window error rate tracker with threshold alerting.

    Tracks request outcomes over a configurable window and logs alerts
    when the error rate exceeds a threshold.
    """

    def __init__(
        self,
        window_seconds: int = 300,
        alert_threshold: float = 0.10,
        min_requests: int = 10,
    ) -> None:
        self._window_seconds = window_seconds
        self._alert_threshold = alert_threshold
        self._min_requests = min_requests
        self._lock = Lock()
        self._outcomes: deque[tuple[float, bool]] = deque()
        self._total_requests = 0
        self._total_errors = 0
        self._last_alert_time: float = 0
        self._alert_cooldown = 60  # seconds between repeated alerts

    def record(self, *, error: bool) -> None:
        """Record a request outcome."""
        now = time.monotonic()
        with self._lock:
            self._outcomes.append((now, error))
            self._total_requests += 1
            if error:
                self._total_errors += 1
            self._evict(now)
            self._check_alert(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._outcomes and self._outcomes[0][0] < cutoff:
            self._outcomes.popleft()

    def _check_alert(self, now: float) -> None:
        if len(self._outcomes) < self._min_requests:
            return
        errors = sum(1 for _, is_err in self._outcomes if is_err)
        rate = errors / len(self._outcomes)
        if (
            rate >= self._alert_threshold
            and (now - self._last_alert_time) > self._alert_cooldown
        ):
            self._last_alert_time = now
            logger.error(
                "ERROR RATE ALERT: %.1f%% errors in last %ds (%d/%d requests)",
                rate * 100,
                self._window_seconds,
                errors,
                len(self._outcomes),
            )

    def stats(self) -> dict[str, Any]:
        """Return current error tracking statistics."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            window_total = len(self._outcomes)
            window_errors = sum(1 for _, is_err in self._outcomes if is_err)
            return {
                "window_seconds": self._window_seconds,
                "window_requests": window_total,
                "window_errors": window_errors,
                "window_error_rate": window_errors / window_total
                if window_total
                else 0.0,
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "alert_threshold": self._alert_threshold,
            }


class UptimeTracker:
    """Tracks application uptime and last-checked timestamps."""

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._start_datetime = datetime.now(timezone.utc)

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def info(self) -> dict[str, Any]:
        uptime = self.uptime_seconds()
        return {
            "started_at": self._start_datetime.isoformat(),
            "uptime_seconds": round(uptime, 1),
            "uptime_human": _format_duration(uptime),
        }


def _format_duration(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def check_database(db: Any) -> bool:
    """Health check: verify database is responsive."""
    try:
        with db._engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False


def check_database_tables(db: Any) -> bool:
    """Health check: verify critical tables exist."""
    try:
        from sqlalchemy import inspect

        tables = set(inspect(db._engine).get_table_names())
        return {"tenants", "organizations", "tasks", "metering_events"}.issubset(tables)
    except Exception:
        return False


def check_stripe_reachability(
    stripe_billing: Any, *, timeout_seconds: float = 2.0, verify_network: bool = False
) -> bool:
    """Health check: verify Stripe credentials are valid (and optionally reachable)."""
    try:
        if stripe_billing is None:
            return False
        api_key = getattr(stripe_billing, "_api_key", "")
        normalized_key = str(api_key).strip()
        if not normalized_key:
            return False
        if not normalized_key.startswith("sk_"):
            return False
        if not verify_network:
            return True
        request = Request(
            "https://api.stripe.com/v1/account",
            headers={"Authorization": f"Bearer {normalized_key}"},
            method="GET",
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            return int(getattr(response, "status", 0)) == 200
    except URLError:
        return False
    except Exception:
        return False


def check_llm_provider_available(provider_registry: Any, provider: str) -> bool:
    """Health check: verify the requested LLM provider is available."""
    try:
        return provider_registry.get(provider) is not None
    except Exception:
        return False


class RunFailureTracker:
    """Tracks agent run failure rates with alerting.

    Monitors Paperclip agent run outcomes over a sliding window and alerts
    when failure rate exceeds threshold. Designed to be resilient to
    Paperclip API unavailability.
    """

    def __init__(
        self,
        window_seconds: int = 3600,
        alert_threshold: float = 0.15,
        min_runs: int = 5,
        alert_callback: Any | None = None,
    ) -> None:
        self._window_seconds = window_seconds
        self._alert_threshold = alert_threshold
        self._min_runs = min_runs
        self._alert_callback = alert_callback
        self._lock = Lock()
        self._outcomes: deque[tuple[float, bool]] = deque()  # (timestamp, is_failure)
        self._total_runs = 0
        self._total_failures = 0
        self._last_alert_time: float = 0
        self._alert_cooldown = 300  # 5 minutes between repeated alerts
        self._last_api_error: str | None = None

    def record(self, *, failure: bool) -> None:
        """Record a run outcome."""
        now = time.monotonic()
        with self._lock:
            self._outcomes.append((now, failure))
            self._total_runs += 1
            if failure:
                self._total_failures += 1
            self._evict(now)
            self._check_alert(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._outcomes and self._outcomes[0][0] < cutoff:
            self._outcomes.popleft()

    def _check_alert(self, now: float) -> None:
        if len(self._outcomes) < self._min_runs:
            return
        failures = sum(1 for _, is_fail in self._outcomes if is_fail)
        rate = failures / len(self._outcomes)
        if (
            rate >= self._alert_threshold
            and (now - self._last_alert_time) > self._alert_cooldown
        ):
            self._last_alert_time = now
            logger.error(
                "RUN FAILURE RATE ALERT: %.1f%% failures in last %ds (%d/%d runs)",
                rate * 100,
                self._window_seconds,
                failures,
                len(self._outcomes),
            )

            # Trigger alert callback if configured
            if self._alert_callback:
                try:
                    alert_data = {
                        "severity": "critical" if rate >= 0.20 else "warning",
                        "failure_rate": rate,
                        "window_seconds": self._window_seconds,
                        "failures": failures,
                        "total_runs": len(self._outcomes),
                        "threshold": self._alert_threshold,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    self._alert_callback(alert_data)
                except Exception as e:
                    logger.warning("Alert callback failed: %s", e)

    def record_api_error(self, error: str) -> None:
        """Record Paperclip API error for diagnostics."""
        with self._lock:
            self._last_api_error = error

    def stats(self) -> dict[str, Any]:
        """Return current run failure tracking statistics."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            window_total = len(self._outcomes)
            window_failures = sum(1 for _, is_fail in self._outcomes if is_fail)
            return {
                "window_seconds": self._window_seconds,
                "window_runs": window_total,
                "window_failures": window_failures,
                "window_failure_rate": window_failures / window_total
                if window_total
                else 0.0,
                "total_runs": self._total_runs,
                "total_failures": self._total_failures,
                "alert_threshold": self._alert_threshold,
                "last_api_error": self._last_api_error,
            }


class WebhookHealthTracker:
    """Sliding-window tracker for webhook delivery success rate and latency.

    Records delivery outcomes and latency, computes percentiles, and alerts
    when delivery success rate drops below threshold.
    """

    def __init__(
        self,
        window_seconds: int = 3600,
        alert_threshold: float = 0.90,
        min_deliveries: int = 10,
        alert_callback: Any | None = None,
    ) -> None:
        self._window_seconds = window_seconds
        self._alert_threshold = alert_threshold
        self._min_deliveries = min_deliveries
        self._alert_callback = alert_callback
        self._lock = Lock()
        # (timestamp, success, latency_ms)
        self._outcomes: deque[tuple[float, bool, float]] = deque()
        self._total_deliveries = 0
        self._total_failures = 0
        self._last_alert_time: float = 0
        self._alert_cooldown = 300  # 5 minutes between repeated alerts

    def record(self, *, success: bool, latency_ms: float) -> None:
        """Record a webhook delivery outcome with latency."""
        now = time.monotonic()
        with self._lock:
            self._outcomes.append((now, success, latency_ms))
            self._total_deliveries += 1
            if not success:
                self._total_failures += 1
            self._evict(now)
            self._check_alert(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._outcomes and self._outcomes[0][0] < cutoff:
            self._outcomes.popleft()

    def _check_alert(self, now: float) -> None:
        if len(self._outcomes) < self._min_deliveries:
            return
        successes = sum(1 for _, ok, _ in self._outcomes if ok)
        success_rate = successes / len(self._outcomes)
        if (
            success_rate < self._alert_threshold
            and (now - self._last_alert_time) > self._alert_cooldown
        ):
            self._last_alert_time = now
            failures = len(self._outcomes) - successes
            logger.error(
                "WEBHOOK DELIVERY ALERT: %.1f%% success rate in last %ds "
                "(%d/%d deliveries failed)",
                success_rate * 100,
                self._window_seconds,
                failures,
                len(self._outcomes),
            )
            if self._alert_callback:
                try:
                    self._alert_callback(
                        {
                            "severity": "critical"
                            if success_rate < 0.80
                            else "warning",
                            "success_rate": success_rate,
                            "window_seconds": self._window_seconds,
                            "failures": failures,
                            "total_deliveries": len(self._outcomes),
                            "threshold": self._alert_threshold,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except Exception as e:
                    logger.warning("Webhook alert callback failed: %s", e)

    def _latency_percentile(self, p: float) -> float:
        """Compute the p-th percentile of latencies in the window."""
        latencies = sorted(lat for _, _, lat in self._outcomes)
        if not latencies:
            return 0.0
        idx = max(0, min(int(len(latencies) * p / 100.0), len(latencies) - 1))
        return round(latencies[idx], 2)

    def stats(self) -> dict[str, Any]:
        """Return webhook delivery health statistics."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            total_in_window = len(self._outcomes)
            successes = sum(1 for _, ok, _ in self._outcomes if ok)
            failures = total_in_window - successes
            success_rate = successes / total_in_window if total_in_window else 1.0
            p50 = self._latency_percentile(50)
            p95 = self._latency_percentile(95)
            return {
                "window_seconds": self._window_seconds,
                "deliveries_in_window": total_in_window,
                "successes": successes,
                "failures": failures,
                "success_rate": round(success_rate, 4),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "total_deliveries": self._total_deliveries,
                "total_failures": self._total_failures,
                "alert_threshold": self._alert_threshold,
            }


class AutonomyGate:
    """Evaluates whether autonomy should be degraded based on run SLOs.

    When degraded, the gate **enforces** conservative governance: downstream
    callers must check ``is_enforcing`` and apply the ``target_governance_preset``
    to the actual organization config, not just to response metadata.
    """

    def __init__(self, success_threshold: float = 0.95, min_runs: int = 10) -> None:
        self._success_threshold = success_threshold
        self._min_runs = min_runs
        self._enforcing: bool = False

    @property
    def is_enforcing(self) -> bool:
        """True when the gate is actively enforcing conservative governance."""
        return self._enforcing

    def evaluate(self, run_stats: dict[str, Any]) -> dict[str, Any]:
        """Return current autonomy gate status from run failure stats.

        Side effect: updates ``is_enforcing`` so callers can check enforcement
        state without re-evaluating.
        """
        runs = int(run_stats.get("window_runs", 0) or 0)
        failure_rate = float(run_stats.get("window_failure_rate", 0.0) or 0.0)
        success_rate = max(0.0, 1.0 - failure_rate)
        degraded = runs >= self._min_runs and success_rate < self._success_threshold

        self._enforcing = degraded

        if runs < self._min_runs:
            reason = f"insufficient data ({runs}/{self._min_runs} runs in SLO window)"
        elif degraded:
            reason = (
                f"run success {success_rate * 100:.1f}% < SLO "
                f"{self._success_threshold * 100:.1f}%"
            )
        else:
            reason = (
                f"run success {success_rate * 100:.1f}% meets SLO "
                f"{self._success_threshold * 100:.1f}%"
            )

        return {
            "degraded": degraded,
            "enforced": degraded,
            "reason": reason,
            "success_rate": success_rate,
            "success_threshold": self._success_threshold,
            "window_runs": runs,
            "min_runs": self._min_runs,
            "target_governance_preset": "conservative" if degraded else None,
        }

    def enforce_on_org(self, org: Any) -> bool:
        """Apply conservative governance to an org if the gate is degraded.

        Args:
            org: An Organization instance with ``package.governance.preset``.

        Returns:
            True if enforcement was applied, False otherwise.
        """
        if not self._enforcing:
            return False
        try:
            current = org.package.governance.preset
            if current != "conservative":
                org.package.governance.preset = "conservative"
                logger.warning(
                    "AutonomyGate enforcing conservative governance on org %s "
                    "(was: %s)",
                    getattr(org, "org_id", "unknown"),
                    current,
                )
            return True
        except Exception as e:
            logger.error("AutonomyGate enforcement failed: %s", e)
            return False
