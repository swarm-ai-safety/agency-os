"""Token usage, API calls, and completions tracking per agent per task."""

from __future__ import annotations

import enum
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


class TaskOutcome(enum.Enum):
    """Outcome of a completed task."""

    success = "success"
    failure = "failure"
    partial = "partial"


@dataclass
class UsageEvent:
    """A single metering event."""

    tenant_id: str
    org_id: str
    agent_id: str
    event_type: str  # "llm_call", "task_completion", "tool_use", "task_outcome"
    tokens_in: int = 0
    tokens_out: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class MeteringCollector:
    """
    Collects usage events for billing and analytics.

    Stores events in-memory with a bounded buffer. Events are also
    persisted to SQLite via the Database layer — this in-memory store
    is for recent lookups and aggregation only.

    Thread-safe: all mutations and reads are protected by a lock.
    """

    _MAX_EVENTS = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[UsageEvent] = []
        self._by_tenant: dict[str, list[UsageEvent]] = defaultdict(list)

    def record(self, event: UsageEvent) -> None:
        """Record a usage event. Drops oldest events when buffer is full."""
        with self._lock:
            if len(self._events) >= self._MAX_EVENTS:
                # Drop oldest 10% and rebuild tenant index from remaining events
                drop_count = self._MAX_EVENTS // 10
                self._events = self._events[drop_count:]
                self._by_tenant.clear()
                for e in self._events:
                    self._by_tenant[e.tenant_id].append(e)
            self._events.append(event)
            self._by_tenant[event.tenant_id].append(event)

    def record_llm_call(
        self,
        tenant_id: str,
        org_id: str,
        agent_id: str,
        tokens_in: int,
        tokens_out: int,
        model: str = "",
    ) -> None:
        """Convenience method for recording an LLM API call."""
        self.record(
            UsageEvent(
                tenant_id=tenant_id,
                org_id=org_id,
                agent_id=agent_id,
                event_type="llm_call",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                metadata={"model": model},
            )
        )

    def record_task_outcome(
        self,
        tenant_id: str,
        org_id: str,
        agent_id: str,
        outcome: TaskOutcome,
        task_id: str = "",
        duration_sec: float | None = None,
    ) -> None:
        """Record the outcome of a completed task."""
        meta: dict[str, Any] = {"outcome": outcome.value}
        if task_id:
            meta["task_id"] = task_id
        if duration_sec is not None:
            meta["duration_sec"] = duration_sec
        self.record(
            UsageEvent(
                tenant_id=tenant_id,
                org_id=org_id,
                agent_id=agent_id,
                event_type="task_outcome",
                metadata=meta,
            )
        )

    def get_agent_outcomes(
        self, agent_id: str, tenant_id: str, limit: int | None = None
    ) -> list[UsageEvent]:
        """Get task_outcome events for a specific agent, most recent first."""
        with self._lock:
            results = [
                e
                for e in reversed(self._events)
                if e.event_type == "task_outcome"
                and e.agent_id == agent_id
                and e.tenant_id == tenant_id
            ]
            if limit is not None:
                results = results[:limit]
            return results

    def get_tenant_events(self, tenant_id: str) -> list[UsageEvent]:
        """Get all events for a tenant."""
        with self._lock:
            return list(self._by_tenant.get(tenant_id, []))

    def get_tenant_totals(self, tenant_id: str) -> dict[str, int]:
        """Get total token usage for a tenant."""
        with self._lock:
            events = self._by_tenant.get(tenant_id, [])
            return {
                "total_events": len(events),
                "total_tokens_in": sum(e.tokens_in for e in events),
                "total_tokens_out": sum(e.tokens_out for e in events),
                "total_tokens": sum(e.tokens_in + e.tokens_out for e in events),
            }

    def get_agent_percentiles(
        self,
        agent_id: str,
        tenant_id: str,
        metric: str = "duration_sec",
        percentiles: tuple[float, ...] = (5.0, 50.0, 95.0),
        limit: int | None = None,
    ) -> dict[str, float | None]:
        """Compute percentile aggregations on task_outcome metadata.

        Args:
            agent_id: Agent to query.
            tenant_id: Tenant to scope query to.
            metric: Metadata key to aggregate (default: duration_sec).
            percentiles: Which percentiles to compute.
            limit: Max recent outcomes to consider (None = all).

        Returns:
            Dict mapping "p{N}" to the percentile value, or None if
            insufficient data.
        """
        outcomes = self.get_agent_outcomes(agent_id, tenant_id, limit=limit)
        values = sorted(
            e.metadata[metric]
            for e in outcomes
            if metric in e.metadata and isinstance(e.metadata[metric], (int, float))
        )
        if not values:
            return {f"p{int(p)}": None for p in percentiles}
        return {f"p{int(p)}": _percentile(values, p) for p in percentiles}

    @property
    def total_events(self) -> int:
        with self._lock:
            return len(self._events)


def _percentile(sorted_values: list[float], p: float) -> float:
    """Compute the p-th percentile from a pre-sorted list using linear interpolation."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Rank on 0-based index scale
    rank = (p / 100.0) * (n - 1)
    low = int(rank)
    high = min(low + 1, n - 1)
    frac = rank - low
    return sorted_values[low] + frac * (sorted_values[high] - sorted_values[low])
