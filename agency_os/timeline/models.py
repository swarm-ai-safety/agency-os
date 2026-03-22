"""Data models for timeline events."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TimelineEventType(str, Enum):
    """Types of events that appear in the company time-lapse."""

    # Organization lifecycle
    ORG_STARTED = "org.started"
    ORG_STOPPED = "org.stopped"

    # Agent activity
    AGENT_JOINED = "agent.joined"
    AGENT_FROZEN = "agent.frozen"
    AGENT_UNFROZEN = "agent.unfrozen"

    # Task lifecycle
    TASK_SUBMITTED = "task.submitted"
    TASK_BID_PLACED = "task.bid_placed"
    TASK_ASSIGNED = "task.assigned"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Economic
    BUDGET_UPDATE = "budget.update"
    PAYMENT_MADE = "payment.made"

    # Governance
    GOVERNANCE_AUDIT = "governance.audit"
    CIRCUIT_BREAKER = "governance.circuit_breaker"

    # Artifacts
    ARTIFACT_PRODUCED = "artifact.produced"

    # Workflow
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STAGE_PASSED = "workflow.stage_passed"
    WORKFLOW_COMPLETED = "workflow.completed"


@dataclass
class TimelineEvent:
    """A single event in the company time-lapse timeline."""

    org_id: str
    tenant_id: str
    event_type: TimelineEventType
    title: str
    timestamp: float = field(default_factory=time.time)
    agent_id: str | None = None
    agent_name: str | None = None
    agent_division: str | None = None
    agent_color: str | None = None
    detail: str | None = None
    artifact_type: str | None = None
    artifact_ref: str | None = None
    budget_snapshot: float | None = None
    reputation_snapshot: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response. Excludes tenant_id to prevent leakage."""
        return {
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_division": self.agent_division,
            "agent_color": self.agent_color,
            "event_type": self.event_type.value,
            "title": self.title,
            "detail": self.detail,
            "artifact_type": self.artifact_type,
            "artifact_ref": self.artifact_ref,
            "budget_snapshot": self.budget_snapshot,
            "reputation_snapshot": self.reputation_snapshot,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    _MAX_METADATA_BYTES = 16 * 1024  # 16 KB cap on serialized metadata

    def to_db_row(self) -> dict[str, Any]:
        """Serialize for SQLAlchemy insert."""
        metadata_json = None
        if self.metadata:
            raw = json.dumps(self.metadata)
            # Cap metadata size to prevent abuse from agent-controlled data
            metadata_json = raw if len(raw) <= self._MAX_METADATA_BYTES else None
        return {
            "tenant_id": self.tenant_id,
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_division": self.agent_division,
            "agent_color": self.agent_color,
            "event_type": self.event_type.value,
            "title": self.title,
            "detail": self.detail,
            "artifact_type": self.artifact_type,
            "artifact_ref": self.artifact_ref,
            "budget_snapshot": self.budget_snapshot,
            "reputation_snapshot": self.reputation_snapshot,
            "metadata_json": metadata_json,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> TimelineEvent:
        """Reconstruct from a database row."""
        meta = row.get("metadata_json")
        return cls(
            org_id=row["org_id"],
            tenant_id=row["tenant_id"],
            agent_id=row.get("agent_id"),
            agent_name=row.get("agent_name"),
            agent_division=row.get("agent_division"),
            agent_color=row.get("agent_color"),
            event_type=TimelineEventType(row["event_type"]),
            title=row["title"],
            detail=row.get("detail"),
            artifact_type=row.get("artifact_type"),
            artifact_ref=row.get("artifact_ref"),
            budget_snapshot=row.get("budget_snapshot"),
            reputation_snapshot=row.get("reputation_snapshot"),
            metadata=json.loads(meta) if meta else {},
            timestamp=row["timestamp"],
        )
