"""Data models for project plans produced by the planning layer.

These are the structured outputs that the Project Planner agent generates
and the PlanExecutor consumes. They bridge natural-language descriptions
to machine-executable task graphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ComponentType(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    SERVICE = "service"
    INFRASTRUCTURE = "infrastructure"
    QUEUE = "queue"
    CACHE = "cache"


class Protocol(str, Enum):
    REST = "REST"
    GRAPHQL = "GraphQL"
    WEBSOCKET = "WebSocket"
    EVENT = "event"
    SHARED_DB = "shared_db"
    GRPC = "gRPC"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    VERIFYING = "verifying"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class SandboxRequirements:
    """What an isolated task sandbox needs."""

    needs_network: bool = False
    needs_filesystem: bool = True
    needs_browser: bool = False
    max_duration_seconds: int = 300
    max_memory_mb: int = 512
    environment_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class ArchitectureComponent:
    """A component in the system architecture graph."""

    id: str
    type: ComponentType
    description: str
    tech: str = ""
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "tech": self.tech,
            "dependencies": self.dependencies,
        }


@dataclass
class DataFlow:
    """A data flow between architecture components."""

    from_component: str
    to_component: str
    protocol: Protocol
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_component,
            "to": self.to_component,
            "protocol": self.protocol.value,
            "description": self.description,
        }


@dataclass
class TechChoice:
    """A technology recommendation for a specific layer."""

    layer: str
    technology: str
    rationale: str = ""
    risk: RiskLevel = RiskLevel.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "technology": self.technology,
            "rationale": self.rationale,
            "risk": self.risk.value,
        }


@dataclass
class TaskSpec:
    """An atomic, executable task within a milestone.

    Each task is:
    - Completable by a single agent in one session
    - Independently testable via acceptance criteria
    - Executable in an isolated sandbox
    """

    id: str
    milestone_id: str
    title: str
    description: str
    agent_role: str  # e.g., "engineering/senior-developer"
    domain_tags: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    estimated_tokens: int = 10000
    sandbox: SandboxRequirements = field(default_factory=SandboxRequirements)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "milestone_id": self.milestone_id,
            "title": self.title,
            "description": self.description,
            "agent_role": self.agent_role,
            "domain_tags": self.domain_tags,
            "depends_on": self.depends_on,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_tokens": self.estimated_tokens,
            "sandbox": {
                "needs_network": self.sandbox.needs_network,
                "needs_filesystem": self.sandbox.needs_filesystem,
                "needs_browser": self.sandbox.needs_browser,
            },
            "status": self.status.value,
        }


@dataclass
class Milestone:
    """A shippable milestone containing multiple tasks."""

    id: str
    name: str
    acceptance_criteria: list[str] = field(default_factory=list)
    effort_days: float = 0.0
    depends_on: list[str] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)
    status: MilestoneStatus = MilestoneStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "acceptance_criteria": self.acceptance_criteria,
            "effort_days": self.effort_days,
            "depends_on": self.depends_on,
            "tasks": [t.to_dict() for t in self.tasks],
            "status": self.status.value,
        }


@dataclass
class ProjectPlan:
    """Complete project plan: architecture + milestones + executable task graph.

    This is the central artifact of the planning-first approach. It bridges
    a natural-language project description to a machine-executable plan.
    """

    name: str
    description: str
    architecture: list[ArchitectureComponent] = field(default_factory=list)
    data_flows: list[DataFlow] = field(default_factory=list)
    tech_stack: list[TechChoice] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    execution_order: list[str] = field(
        default_factory=list
    )  # topologically sorted task IDs

    # Metadata
    estimated_total_tokens: int = 0
    estimated_total_days: float = 0.0
    critical_path: list[str] = field(default_factory=list)

    @property
    def all_tasks(self) -> list[TaskSpec]:
        """Flat list of all tasks across all milestones."""
        tasks = []
        for milestone in self.milestones:
            tasks.extend(milestone.tasks)
        return tasks

    @property
    def task_count(self) -> int:
        return sum(len(m.tasks) for m in self.milestones)

    def get_task(self, task_id: str) -> Optional[TaskSpec]:
        for task in self.all_tasks:
            if task.id == task_id:
                return task
        return None

    def get_milestone(self, milestone_id: str) -> Optional[Milestone]:
        for m in self.milestones:
            if m.id == milestone_id:
                return m
        return None

    def ready_tasks(self) -> list[TaskSpec]:
        """Tasks whose dependencies are all satisfied (PASSED)."""
        completed = {t.id for t in self.all_tasks if t.status == TaskStatus.PASSED}
        return [
            t
            for t in self.all_tasks
            if t.status == TaskStatus.PENDING
            and all(dep in completed for dep in t.depends_on)
        ]

    def progress(self) -> dict[str, Any]:
        """Current execution progress summary."""
        tasks = self.all_tasks
        total = len(tasks)
        by_status: dict[str, int] = {}
        for t in tasks:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        passed = by_status.get("passed", 0)
        return {
            "total_tasks": total,
            "by_status": by_status,
            "completion_pct": (passed / total * 100) if total > 0 else 0,
            "ready_tasks": len(self.ready_tasks()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "architecture": [c.to_dict() for c in self.architecture],
            "data_flows": [f.to_dict() for f in self.data_flows],
            "tech_stack": [t.to_dict() for t in self.tech_stack],
            "milestones": [m.to_dict() for m in self.milestones],
            "execution_order": self.execution_order,
            "estimated_total_tokens": self.estimated_total_tokens,
            "estimated_total_days": self.estimated_total_days,
            "critical_path": self.critical_path,
            "progress": self.progress(),
        }
