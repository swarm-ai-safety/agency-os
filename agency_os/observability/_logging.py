"""Centralized logging and observability module for agency_os."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Metric name constants
# ---------------------------------------------------------------------------

METRIC_TASK_SUBMITTED = "task.submitted"
METRIC_TASK_COMPLETED = "task.completed"
METRIC_BID_PLACED = "bid.placed"
METRIC_BUDGET_DEPLETED = "budget.depleted"
METRIC_CIRCUIT_BREAKER_TRIPPED = "circuit_breaker.tripped"
METRIC_REQUEST_COMPLETED = "request.completed"
METRIC_PAYMENT_FAILED = "payment.failed"

# ---------------------------------------------------------------------------
# JSON log formatter
# ---------------------------------------------------------------------------

_LOG_PREFIX = "agency_os"
_REQUEST_ID_VAR: ContextVar[str | None] = ContextVar("request_id", default=None)


class _RequestContextFilter(logging.Filter):
    """Injects request correlation metadata into each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _REQUEST_ID_VAR.get()
        record.request_id = request_id or "-"
        return True


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        return json.dumps(payload)


# ---------------------------------------------------------------------------
# Public API — configure_logging / get_logger
# ---------------------------------------------------------------------------


def configure_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure the root logger (and the agency_os hierarchy).

    Parameters
    ----------
    level:
        Any stdlib level name, e.g. ``"DEBUG"``, ``"INFO"``, ``"WARNING"``.
    json_format:
        When *True* each log record is emitted as a JSON line; otherwise a
        human-readable format is used.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s [request_id=%(request_id)s] — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_RequestContextFilter())

    root_logger = logging.getLogger(_LOG_PREFIX)
    root_logger.setLevel(numeric_level)
    # Avoid duplicating handlers on repeated calls.
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    # Prevent propagation to the stdlib root logger to keep output clean.
    root_logger.propagate = False


def bind_request_id(request_id: str | None) -> Token[str | None]:
    """Attach request_id to the current context for correlated logging."""
    return _REQUEST_ID_VAR.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Reset the request context after request completion."""
    _REQUEST_ID_VAR.reset(token)


def get_logger(name: str) -> logging.Logger:
    """Return a :class:`logging.Logger` namespaced under *agency_os*.

    Parameters
    ----------
    name:
        Short module/component name, e.g. ``"orchestration"`` or
        ``"economic.wallet"``.  The returned logger will be named
        ``agency_os.<name>``.
    """
    return logging.getLogger(f"{_LOG_PREFIX}.{name}")


# ---------------------------------------------------------------------------
# EventTracker
# ---------------------------------------------------------------------------


class _Event:
    """Internal record for a single tracked event."""

    __slots__ = ("name", "timestamp", "metadata")

    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.timestamp: datetime = datetime.now(tz=timezone.utc)
        self.metadata = metadata


class EventTracker:
    """In-process event store for key system events.

    All events are kept in memory; the tracker is intentionally lightweight
    and carries no external dependencies.

    Example
    -------
    >>> tracker = EventTracker()
    >>> tracker.track(METRIC_TASK_SUBMITTED, task_id="t-1", agent="dev")
    >>> tracker.summary()
    {'task.submitted': 1}
    """

    def __init__(self) -> None:
        self._events: list[_Event] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def track(self, event_name: str, **kwargs: Any) -> None:
        """Record *event_name* together with any keyword metadata.

        Parameters
        ----------
        event_name:
            Name of the event (use one of the ``METRIC_*`` constants where
            applicable).
        **kwargs:
            Arbitrary key/value metadata stored alongside the event.
        """
        self._events.append(_Event(event_name, dict(kwargs)))

    def get_events(
        self,
        event_name: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return recorded events, optionally filtered.

        Parameters
        ----------
        event_name:
            When supplied, only events with this name are returned.
        since:
            When supplied, only events whose timestamp is *>=* this value are
            returned.  Must be a timezone-aware :class:`datetime`.

        Returns
        -------
        list[dict]:
            Each element has keys ``"name"``, ``"timestamp"`` (ISO-8601
            string), and ``"metadata"``.
        """
        results: list[dict[str, Any]] = []
        for ev in self._events:
            if event_name is not None and ev.name != event_name:
                continue
            if since is not None and ev.timestamp < since:
                continue
            results.append(
                {
                    "name": ev.name,
                    "timestamp": ev.timestamp.isoformat(),
                    "metadata": dict(ev.metadata),
                }
            )
        return results

    def summary(self) -> dict[str, int]:
        """Return a mapping of *event_name* → count for all recorded events."""
        counts: dict[str, int] = defaultdict(int)
        for ev in self._events:
            counts[ev.name] += 1
        return dict(counts)


# ---------------------------------------------------------------------------
# HealthCheck
# ---------------------------------------------------------------------------


class HealthCheck:
    """Registry of named health-check callables.

    Each check is a zero-argument callable that returns a :class:`bool`.
    ``run_all`` executes every registered check and measures its wall-clock
    latency using :func:`time.monotonic`.

    Example
    -------
    >>> hc = HealthCheck()
    >>> hc.register_check("db", lambda: True)
    >>> hc.run_all()
    {'db': {'healthy': True, 'latency_ms': ...}}
    >>> hc.is_healthy()
    True
    """

    def __init__(self, check_timeout_seconds: float | None = None) -> None:
        self._checks: dict[str, Callable[[], bool]] = {}
        self._check_timeout_seconds = check_timeout_seconds

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def register_check(self, name: str, check_fn: Callable[[], bool]) -> None:
        """Register a health check.

        Parameters
        ----------
        name:
            Unique identifier for this check, e.g. ``"database"`` or
            ``"message_bus"``.
        check_fn:
            A zero-argument callable that returns ``True`` when the component
            is healthy and ``False`` (or raises an exception) otherwise.
        """
        self._checks[name] = check_fn

    def run_all(self) -> dict[str, dict[str, Any]]:
        """Execute every registered check.

        Returns
        -------
        dict[str, dict]:
            Maps each check name to a result dict with keys:

            * ``"healthy"`` (:class:`bool`) — outcome of the check.
            * ``"latency_ms"`` (:class:`float`) — wall-clock time in
              milliseconds measured with :func:`time.monotonic`.
            * ``"error"`` (:class:`str`, only present on exception) — the
              string representation of any exception raised by the check.
        """
        results: dict[str, dict[str, Any]] = {}
        for name, fn in self._checks.items():
            start = time.monotonic()
            if (
                self._check_timeout_seconds is not None
                and self._check_timeout_seconds > 0
            ):
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(fn)
                try:
                    healthy = bool(future.result(timeout=self._check_timeout_seconds))
                    latency_ms = (time.monotonic() - start) * 1000.0
                    results[name] = {"healthy": healthy, "latency_ms": latency_ms}
                except FutureTimeoutError:
                    latency_ms = (time.monotonic() - start) * 1000.0
                    results[name] = {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "timed_out": True,
                        "error": f"timeout after {self._check_timeout_seconds}s",
                    }
                    future.cancel()
                except Exception as exc:  # noqa: BLE001
                    latency_ms = (time.monotonic() - start) * 1000.0
                    results[name] = {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            else:
                try:
                    healthy = bool(fn())
                    latency_ms = (time.monotonic() - start) * 1000.0
                    results[name] = {"healthy": healthy, "latency_ms": latency_ms}
                except Exception as exc:  # noqa: BLE001
                    latency_ms = (time.monotonic() - start) * 1000.0
                    results[name] = {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
        return results

    def is_healthy(self) -> bool:
        """Return ``True`` only if every registered check reports healthy.

        If no checks are registered this returns ``True``.
        """
        return all(result["healthy"] for result in self.run_all().values())
