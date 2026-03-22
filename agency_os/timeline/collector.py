"""TimelineCollector — captures agent activity into a replayable timeline.

The collector provides convenience methods for common event types and
persists events to the database when available, with an in-memory buffer
as fallback.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from agency_os.agents.business_agent import BusinessAgent
from agency_os.timeline.models import TimelineEvent, TimelineEventType

logger = logging.getLogger(__name__)

_MAX_BUFFER_SIZE = 10_000


class TimelineCollector:
    """Captures and stores timeline events for the time-lapse feature.

    Events are buffered in memory (bounded) and optionally persisted
    to the database.  The collector is thread-safe.
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._buffer: list[TimelineEvent] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def record(self, event: TimelineEvent) -> None:
        """Record a timeline event."""
        with self._lock:
            if len(self._buffer) < _MAX_BUFFER_SIZE:
                self._buffer.append(event)
        self._persist(event)

    def _persist(self, event: TimelineEvent) -> None:
        """Best-effort database persistence."""
        if self._db is None:
            return
        try:
            self._db.save_timeline_event(event.to_db_row())
        except Exception:
            logger.warning("Failed to persist timeline event", exc_info=True)

    # ------------------------------------------------------------------
    # Convenience emitters
    # ------------------------------------------------------------------

    def org_started(
        self,
        org_id: str,
        tenant_id: str,
        package_name: str,
        agent_count: int,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.ORG_STARTED,
                title=f"Organization started: {package_name}",
                detail=f"{agent_count} agents initialized",
                metadata={"package": package_name, "agent_count": agent_count},
            )
        )

    def org_stopped(self, org_id: str, tenant_id: str) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.ORG_STOPPED,
                title="Organization stopped",
            )
        )

    def agent_joined(self, org_id: str, tenant_id: str, agent: BusinessAgent) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.AGENT_JOINED,
                title=f"{agent.name} joined the organization",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                budget_snapshot=agent.balance,
                metadata={
                    "bid_strategy": agent.economic.bid_strategy.value,
                    "spec_slug": agent.spec.slug,
                },
            )
        )

    def task_submitted(
        self,
        org_id: str,
        tenant_id: str,
        task_id: str,
        description: str,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.TASK_SUBMITTED,
                title=f"Task submitted: {description[:80]}",
                detail=description,
                metadata={"task_id": task_id},
            )
        )

    def bid_placed(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
        task_id: str,
        bid_amount: float,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.TASK_BID_PLACED,
                title=f"{agent.name} bid ${bid_amount:.2f}",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                budget_snapshot=agent.balance,
                metadata={"task_id": task_id, "bid_amount": bid_amount},
            )
        )

    def task_assigned(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
        task_id: str,
        description: str,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.TASK_ASSIGNED,
                title=f"{agent.name} won task: {description[:60]}",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                budget_snapshot=agent.balance,
                detail=description,
                metadata={"task_id": task_id},
            )
        )

    def task_completed(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
        task_id: str,
        artifact_type: str | None = None,
        artifact_ref: str | None = None,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.TASK_COMPLETED,
                title=f"{agent.name} completed task",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                budget_snapshot=agent.balance,
                reputation_snapshot=agent.reputation,
                artifact_type=artifact_type,
                artifact_ref=artifact_ref,
                metadata={"task_id": task_id},
            )
        )

    def task_failed(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
        task_id: str,
        error: str,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.TASK_FAILED,
                title=f"{agent.name} failed task",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                budget_snapshot=agent.balance,
                reputation_snapshot=agent.reputation,
                detail=error,
                metadata={"task_id": task_id},
            )
        )

    def circuit_breaker_tripped(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.CIRCUIT_BREAKER,
                title=f"Circuit breaker tripped: {agent.name} frozen",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                detail=f"{agent._consecutive_failures} consecutive failures",
                metadata={"consecutive_failures": agent._consecutive_failures},
            )
        )

    def governance_audit(
        self,
        org_id: str,
        tenant_id: str,
        agent: BusinessAgent,
        passed: bool,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.GOVERNANCE_AUDIT,
                title=f"Audit {'passed' if passed else 'failed'}: {agent.name}",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_division=agent.spec.division,
                agent_color=agent.spec.color,
                reputation_snapshot=agent.reputation,
                metadata={"passed": passed},
            )
        )

    def workflow_started(
        self,
        org_id: str,
        tenant_id: str,
        workflow_name: str,
        run_id: str,
    ) -> None:
        self.record(
            TimelineEvent(
                org_id=org_id,
                tenant_id=tenant_id,
                event_type=TimelineEventType.WORKFLOW_STARTED,
                title=f"Workflow started: {workflow_name}",
                metadata={"workflow": workflow_name, "run_id": run_id},
            )
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_events(
        self,
        org_id: str,
        tenant_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        event_types: list[str] | None = None,
        agent_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return timeline events from in-memory buffer, filtered."""
        with self._lock:
            results = []
            for ev in reversed(self._buffer):
                if ev.org_id != org_id:
                    continue
                if tenant_id is not None and ev.tenant_id != tenant_id:
                    continue
                if since is not None and ev.timestamp < since:
                    continue
                if until is not None and ev.timestamp > until:
                    continue
                if event_types and ev.event_type.value not in event_types:
                    continue
                if agent_id and ev.agent_id != agent_id:
                    continue
                results.append(ev.to_dict())
                if len(results) >= limit:
                    break
            return results

    def get_replay(
        self,
        org_id: str,
        tenant_id: str | None = None,
        speed: float = 1.0,
    ) -> dict[str, Any]:
        """Build a replay manifest for the given org run.

        Returns a structure containing:
        - events: ordered list of timeline events
        - agents: list of unique agents that appeared
        - duration_seconds: wall-clock duration of the run
        - speed: playback speed multiplier
        """
        with self._lock:
            events = sorted(
                (
                    ev
                    for ev in self._buffer
                    if ev.org_id == org_id
                    and (tenant_id is None or ev.tenant_id == tenant_id)
                ),
                key=lambda e: e.timestamp,
            )

        if not events:
            return {
                "org_id": org_id,
                "events": [],
                "agents": [],
                "duration_seconds": 0,
                "speed": speed,
            }

        start_ts = events[0].timestamp
        end_ts = events[-1].timestamp

        # Build unique agent list with metadata
        agents: dict[str, dict[str, Any]] = {}
        for ev in events:
            if ev.agent_id and ev.agent_id not in agents:
                agents[ev.agent_id] = {
                    "agent_id": ev.agent_id,
                    "name": ev.agent_name,
                    "division": ev.agent_division,
                    "color": ev.agent_color,
                }

        # Build replay frames with relative timestamps
        frames = []
        for ev in events:
            frame = ev.to_dict()
            frame["relative_time"] = ev.timestamp - start_ts
            frame["replay_time"] = (ev.timestamp - start_ts) / speed
            frames.append(frame)

        return {
            "org_id": org_id,
            "events": frames,
            "agents": list(agents.values()),
            "duration_seconds": end_ts - start_ts,
            "replay_duration_seconds": (end_ts - start_ts) / speed,
            "speed": speed,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
        }

    def get_summary(self, org_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Return summary statistics for an org timeline."""
        with self._lock:
            events = [
                ev
                for ev in self._buffer
                if ev.org_id == org_id
                and (tenant_id is None or ev.tenant_id == tenant_id)
            ]

        if not events:
            return {"org_id": org_id, "total_events": 0}

        type_counts: dict[str, int] = {}
        agent_set: set[str] = set()
        for ev in events:
            type_counts[ev.event_type.value] = (
                type_counts.get(ev.event_type.value, 0) + 1
            )
            if ev.agent_id:
                agent_set.add(ev.agent_id)

        return {
            "org_id": org_id,
            "total_events": len(events),
            "unique_agents": len(agent_set),
            "event_types": type_counts,
            "duration_seconds": events[-1].timestamp - events[0].timestamp
            if len(events) > 1
            else 0,
            "start_timestamp": events[0].timestamp,
            "end_timestamp": events[-1].timestamp,
        }
