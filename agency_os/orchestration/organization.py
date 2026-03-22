"""Organization — a running 'company' instance built from a package."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agency_os.agents.agent_factory import AgentFactory
from agency_os.agents.business_agent import BusinessAgent
from agency_os.agents.registry import AgentRegistry
from agency_os.memory.decay import run_decay_sweep
from agency_os.orchestration.workflow_engine import WorkflowEngine, WorkflowRun
from agency_os.packages.loader import load_package, load_package_from_name
from agency_os.packages.schema import PackageSpec
from agency_os.planning.decomposer import ProjectDecomposer
from agency_os.planning.executor import ExecutionReport, PlanExecutor
from agency_os.planning.sandbox import TaskSandbox
from agency_os.planning.schema import ProjectPlan

logger = logging.getLogger(__name__)


class OrgStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Organization:
    """
    A running autonomous organization instance.

    Created from a PackageSpec, it instantiates all agents via the factory,
    manages their lifecycle, and routes tasks to agents.
    """

    def __init__(
        self,
        package: PackageSpec,
        registry: AgentRegistry | None = None,
        org_id: str | None = None,
    ):
        self.org_id = org_id or f"org-{uuid.uuid4().hex[:8]}"
        self.package = package
        self._registry = registry or AgentRegistry()
        self._status = OrgStatus.CREATED
        self._agents: list[BusinessAgent] = []
        self._task_history: list[dict[str, Any]] = []
        self._workflow_engine: WorkflowEngine | None = None
        self._active_runs: dict[str, WorkflowRun] = {}
        self._decomposer = ProjectDecomposer()
        self._active_plans: dict[str, ProjectPlan] = {}

    @classmethod
    def from_file(cls, path: str, **kwargs: Any) -> Organization:
        """Create an organization from a package YAML file."""
        package = load_package(path)
        return cls(package=package, **kwargs)

    @classmethod
    def from_builtin(cls, name: str, **kwargs: Any) -> Organization:
        """Create an organization from a built-in package name."""
        package = load_package_from_name(name)
        return cls(package=package, **kwargs)

    def start(self) -> None:
        """Initialize agents and start the organization."""
        if self._status == OrgStatus.RUNNING:
            logger.warning(f"Organization {self.org_id} is already running")
            return

        factory = AgentFactory(self._registry, self.package.deployment)
        self._agents = factory.create_agents(self.package.agents)
        if self.package.workflows:
            self._workflow_engine = WorkflowEngine(self.package.workflows)
        self._status = OrgStatus.RUNNING

        logger.info(
            f"Organization {self.org_id} started: "
            f"{len(self._agents)} agents, "
            f"package={self.package.metadata.name}"
        )

    def stop(self, agents_dir: str | Path | None = None) -> None:
        """Stop the organization.

        If *agents_dir* is provided, runs a memory decay sweep for each
        agent that has a matching directory under that path, compacting
        knowledge graphs into priority-ordered summaries.
        """
        if agents_dir is not None:
            self._run_memory_sweep(Path(agents_dir))
        self._status = OrgStatus.STOPPED
        logger.info(f"Organization {self.org_id} stopped")

    def _run_memory_sweep(self, agents_dir: Path) -> None:
        """Run memory decay for all agents with on-disk PARA stores."""
        for agent in self._agents:
            # Convention: agent directory name matches the slug's last segment
            slug_tail = (
                agent.spec.slug.split("/")[-1]
                if "/" in agent.spec.slug
                else agent.spec.slug
            )
            agent_home = agents_dir / slug_tail
            if agent_home.is_dir():
                results = run_decay_sweep(agent_home, write=True)
                if results:
                    logger.info(
                        f"Memory sweep for {agent.agent_id}: "
                        f"{sum(len(v) for v in results.values())} facts across "
                        f"{len(results)} entities"
                    )

    @property
    def status(self) -> OrgStatus:
        return self._status

    @property
    def agents(self) -> list[BusinessAgent]:
        return list(self._agents)

    def get_agent(self, agent_id: str) -> Optional[BusinessAgent]:
        """Look up an agent by ID."""
        for agent in self._agents:
            if agent.agent_id == agent_id:
                return agent
        return None

    def submit_task(
        self,
        description: str,
        metadata: dict[str, Any] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        """
        Submit a task to the organization.

        For MVP: finds the best agent by bid and assigns the task.
        Full implementation will use task_router with proper bidding.

        Args:
            description: Task description.
            metadata: Optional metadata dict.
            execute: If True, actually call the winning agent's LLM to
                     execute the task and include the result in the record.

        Returns:
            Task record with assignment info (and ``result`` if *execute* is True).
        """
        if self._status != OrgStatus.RUNNING:
            raise RuntimeError(
                f"Organization {self.org_id} is not running (status: {self._status})"
            )

        if not self._agents:
            raise RuntimeError("No agents available")

        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # Exclude frozen agents (circuit breaker tripped)
        eligible = [a for a in self._agents if not a.is_frozen]
        if not eligible:
            raise RuntimeError("All agents are frozen (circuit breakers tripped)")

        # Filter to agents whose permissions allow the requested tool (if any)
        required_tool = (metadata or {}).get("required_tool")
        if required_tool:
            eligible = [a for a in eligible if a.is_tool_allowed(required_tool)]
            if not eligible:
                raise RuntimeError(
                    f"No agent is permitted to use tool {required_tool!r}"
                )

        # Simple bid-based assignment: highest bid wins
        bids = [(agent, agent.compute_bid(description)) for agent in eligible]
        bids.sort(key=lambda x: x[1], reverse=True)
        winner, winning_bid = bids[0]

        task_record: dict[str, Any] = {
            "task_id": task_id,
            "description": description,
            "metadata": metadata or {},
            "assigned_to": winner.agent_id,
            "bid_amount": winning_bid,
            "status": "assigned",
            "bids": [{"agent_id": a.agent_id, "bid": b} for a, b in bids],
        }

        if execute:
            result = winner.execute_task(description, metadata)
            task_record["result"] = result
            task_record["status"] = "completed" if result.get("success") else "failed"

        self._task_history.append(task_record)

        logger.info(
            f"Task {task_id} assigned to {winner.agent_id} (bid: {winning_bid:.2f})"
        )
        return task_record

    # -- Planning-first execution --

    def plan_project(
        self,
        description: str,
        template: str | None = None,
    ) -> ProjectPlan:
        """Generate a project plan from a description.

        Uses the planning-first approach: research → architecture →
        milestones → tasks before any code is written.

        If a planner agent is available in the org, uses LLM-powered
        planning. Otherwise falls back to template-based planning.

        Args:
            description: Natural language project description.
            template: Force a specific template (web_app, api_service, cli_tool).

        Returns:
            A validated ProjectPlan with execution order and critical path.
        """
        if self._status != OrgStatus.RUNNING:
            raise RuntimeError(
                f"Organization {self.org_id} is not running (status: {self._status})"
            )

        # Find planner and researcher agents if available
        planner = self._find_agent_by_role("strategy/project-planner")
        researcher = self._find_agent_by_role("strategy/architecture-researcher")

        if template:
            # Template mode: no LLM needed
            name = description.split(".")[0].split("\n")[0][:60]
            plan = self._decomposer.from_template(template, name, description)
        else:
            # LLM-powered or template fallback
            plan = self._decomposer.from_description(
                description,
                planner_agent=planner,
                researcher_agent=researcher,
            )

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        self._active_plans[plan_id] = plan

        logger.info(
            f"Plan generated for '{plan.name}': "
            f"{plan.task_count} tasks, "
            f"{len(plan.milestones)} milestones, "
            f"critical path length={len(plan.critical_path)}"
        )
        return plan

    def execute_plan(
        self,
        plan: ProjectPlan,
        dry_run: bool = False,
        sandbox_enabled: bool = True,
        verification_commands: list[str] | None = None,
    ) -> ExecutionReport:
        """Execute a project plan through the agent organization.

        Drives each task through the planning-first pipeline:
        pick ready tasks → assign to agents → execute in sandbox →
        verify → update status → repeat.

        Args:
            plan: The plan to execute.
            dry_run: If True, mark tasks as passed without execution.
            sandbox_enabled: Whether to use isolated sandboxes per task.
            verification_commands: Shell commands for sandbox verification.

        Returns:
            ExecutionReport with results and telemetry.
        """
        if self._status != OrgStatus.RUNNING:
            raise RuntimeError(
                f"Organization {self.org_id} is not running (status: {self._status})"
            )

        # Build the executor
        sandbox = TaskSandbox() if sandbox_enabled else None

        def agent_execute(description: str, context: dict[str, Any]) -> dict[str, Any]:
            """Route task to best agent via bidding."""
            return self.submit_task(description, context, execute=True)

        executor = PlanExecutor(
            plan=plan,
            execute_fn=None if dry_run else agent_execute,
            sandbox=sandbox,
            verification_commands=verification_commands or [],
            max_retries=1,
        )

        report = executor.run(dry_run=dry_run)

        logger.info(
            f"Plan '{plan.name}' execution {report.status}: "
            f"{report.tasks_passed}/{report.total_tasks} passed"
        )
        return report

    def _find_agent_by_role(self, slug_suffix: str) -> Optional[BusinessAgent]:
        """Find the first agent whose spec slug ends with the given suffix."""
        for agent in self._agents:
            if agent.spec.slug.endswith(slug_suffix):
                return agent
        return None

    def start_workflow(self, workflow_name: str) -> WorkflowRun:
        """Start a named workflow, enforcing quality gates between stages."""
        if self._workflow_engine is None:
            raise RuntimeError("No workflows configured for this organization")
        run = self._workflow_engine.create_run(workflow_name)
        self._active_runs[run.run_id] = run
        run.status = "running"
        logger.info(f"Workflow {workflow_name} started: {run.run_id}")
        return run

    def advance_workflow(
        self,
        run_id: str,
        evidence: list[dict[str, Any]] | None = None,
        approvals: int = 0,
    ) -> bool:
        """Advance a workflow run past its current quality gate.

        Returns True if the stage advanced, False if the gate blocked it.
        Raises KeyError if the run_id is unknown.
        """
        run = self._active_runs.get(run_id)
        if run is None:
            raise KeyError(f"No active workflow run: {run_id}")
        if self._workflow_engine is None:
            raise RuntimeError("No workflows configured")
        return self._workflow_engine.advance_stage(run, evidence, approvals)

    def status_dict(self) -> dict[str, Any]:
        """Return org status as a dictionary."""
        return {
            "org_id": self.org_id,
            "status": self._status.value,
            "package": self.package.metadata.name,
            "agent_count": len(self._agents),
            "agents": [a.status_dict() for a in self._agents],
            "tasks_submitted": len(self._task_history),
            "governance_preset": self.package.governance.preset,
            "budget_limit_usd": self.package.deployment.budget_limit_usd,
            "active_plans": {
                pid: plan.progress() for pid, plan in self._active_plans.items()
            },
        }

    def __repr__(self) -> str:
        return (
            f"Organization(id={self.org_id!r}, "
            f"status={self._status.value}, "
            f"agents={len(self._agents)}, "
            f"package={self.package.metadata.name!r})"
        )
