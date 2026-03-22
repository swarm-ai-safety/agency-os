"""Plan executor: drives a ProjectPlan through to completion.

Coordinates the execution loop:
    plan → pick ready tasks → assign to agents → execute in sandbox →
    verify → update status → repeat until done or stuck.

This is the runtime that turns a static ProjectPlan into autonomous execution.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .dag import TaskDAG
from .sandbox import TaskSandbox
from .schema import (
    MilestoneStatus,
    ProjectPlan,
    TaskSpec,
    TaskStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionEvent:
    """A logged event during plan execution."""

    timestamp: float
    event_type: str  # task_started | task_completed | task_failed | milestone_completed | plan_completed | plan_stuck
    task_id: str = ""
    agent_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReport:
    """Summary of a plan execution run."""

    plan_name: str
    status: str  # completed | stuck | error
    total_tasks: int = 0
    tasks_passed: int = 0
    tasks_failed: int = 0
    total_duration_ms: int = 0
    total_tokens_used: int = 0
    events: list[ExecutionEvent] = field(default_factory=list)
    milestone_results: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "status": self.status,
            "total_tasks": self.total_tasks,
            "tasks_passed": self.tasks_passed,
            "tasks_failed": self.tasks_failed,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens_used": self.total_tokens_used,
            "milestone_results": self.milestone_results,
            "events_count": len(self.events),
        }


# Type alias for an agent executor function
# Takes (task_description, context) → dict with response, success, tokens_out, etc.
AgentExecutorFn = Callable[[str, dict[str, Any]], dict[str, Any]]


class PlanExecutor:
    """Executes a ProjectPlan by driving tasks through agents in dependency order.

    Usage::

        from agency_os.planning import PlanExecutor, ProjectDecomposer

        # Create a plan
        plan = ProjectDecomposer().from_template("web_app", "MyApp", "A todo app")

        # Define how to execute tasks (wraps your agent system)
        def execute_via_org(description, context):
            return org.submit_task(description, context, execute=True)

        # Run it
        executor = PlanExecutor(plan, execute_fn=execute_via_org)
        report = executor.run()
        print(report.to_dict())
    """

    def __init__(
        self,
        plan: ProjectPlan,
        execute_fn: Optional[AgentExecutorFn] = None,
        sandbox: Optional[TaskSandbox] = None,
        verification_commands: Optional[list[str]] = None,
        max_retries: int = 1,
        on_event: Optional[Callable[[ExecutionEvent], None]] = None,
    ) -> None:
        """
        Args:
            plan: The project plan to execute.
            execute_fn: Function to execute a task. If None, tasks are
                        marked as passed without execution (dry run).
            sandbox: Task sandbox for isolated execution. If None, no
                     sandbox isolation is used.
            verification_commands: Commands to run for each task verification.
            max_retries: Max retries per failed task before marking as FAILED.
            on_event: Optional callback for execution events.
        """
        self.plan = plan
        self._execute_fn = execute_fn
        self._sandbox = sandbox
        self._verification_commands = verification_commands or []
        self._max_retries = max_retries
        self._on_event = on_event
        self._events: list[ExecutionEvent] = []
        self._retry_counts: dict[str, int] = {}
        self._dag = TaskDAG(plan.all_tasks)

    def run(self, dry_run: bool = False) -> ExecutionReport:
        """Execute the plan to completion.

        The main loop:
        1. Find tasks whose dependencies are satisfied
        2. For each ready task, execute via agent
        3. Verify output in sandbox (if configured)
        4. Update task status
        5. Check if milestones are complete
        6. Repeat until done or stuck

        Args:
            dry_run: If True, mark all tasks as passed without executing.
        """
        start_time = time.monotonic()
        report = ExecutionReport(
            plan_name=self.plan.name,
            status="running",
            total_tasks=self.plan.task_count,
        )

        logger.info(
            f"Executing plan '{self.plan.name}': "
            f"{self.plan.task_count} tasks, "
            f"{len(self.plan.milestones)} milestones"
        )

        iteration = 0
        max_iterations = self.plan.task_count * (self._max_retries + 1) + 1

        while iteration < max_iterations:
            iteration += 1
            ready = self.plan.ready_tasks()

            if not ready:
                # Check if we're done or stuck
                progress = self.plan.progress()
                if progress["by_status"].get("pending", 0) == 0:
                    report.status = "completed"
                    break
                elif progress["by_status"].get("failed", 0) > 0:
                    report.status = "stuck"
                    logger.warning("Plan stuck: failed tasks blocking progress")
                    break
                else:
                    report.status = "stuck"
                    logger.warning(
                        "Plan stuck: no ready tasks but pending tasks remain"
                    )
                    break

            # Execute all ready tasks (could be parallelized in production)
            for task in ready:
                self._execute_task(task, dry_run, report)

            # Update milestone statuses
            self._update_milestones(report)

        # Finalize
        report.total_duration_ms = int((time.monotonic() - start_time) * 1000)
        report.events = self._events

        # Clean up sandbox
        if self._sandbox:
            self._sandbox.cleanup_all()

        logger.info(
            f"Plan '{self.plan.name}' {report.status}: "
            f"{report.tasks_passed}/{report.total_tasks} passed, "
            f"{report.tasks_failed} failed"
        )

        return report

    def _execute_task(
        self,
        task: TaskSpec,
        dry_run: bool,
        report: ExecutionReport,
    ) -> None:
        """Execute a single task and update its status."""
        task.status = TaskStatus.RUNNING
        self._emit(
            ExecutionEvent(
                timestamp=time.time(),
                event_type="task_started",
                task_id=task.id,
                details={"title": task.title, "agent_role": task.agent_role},
            )
        )

        if dry_run or self._execute_fn is None:
            task.status = TaskStatus.PASSED
            report.tasks_passed += 1
            self._emit(
                ExecutionEvent(
                    timestamp=time.time(),
                    event_type="task_completed",
                    task_id=task.id,
                    details={"dry_run": True},
                )
            )
            return

        # Build context for the agent
        context = {
            "task_id": task.id,
            "milestone": task.milestone_id,
            "acceptance_criteria": "; ".join(task.acceptance_criteria),
            "domain_tags": ", ".join(task.domain_tags),
        }

        # Execute via agent
        result = self._execute_fn(task.description, context)
        task.result = result

        tokens_out = result.get("tokens_out", 0)
        report.total_tokens_used += tokens_out

        if not result.get("success"):
            self._handle_failure(task, result, report)
            return

        # Sandbox verification (if configured)
        if self._sandbox and self._verification_commands:
            task.status = TaskStatus.VERIFYING
            work_dir = self._sandbox.create(task)
            sandbox_result = self._sandbox.run_verification(
                task, work_dir, self._verification_commands
            )

            if not sandbox_result.success:
                self._handle_failure(
                    task,
                    {
                        "success": False,
                        "error": f"Verification failed: {sandbox_result.error[:500]}",
                        "sandbox": sandbox_result.to_dict(),
                    },
                    report,
                )
                return

        # Success
        task.status = TaskStatus.PASSED
        report.tasks_passed += 1
        self._emit(
            ExecutionEvent(
                timestamp=time.time(),
                event_type="task_completed",
                task_id=task.id,
                agent_id=task.assigned_agent_id,
                details={"tokens_out": tokens_out},
            )
        )

    def _handle_failure(
        self,
        task: TaskSpec,
        result: dict[str, Any],
        report: ExecutionReport,
    ) -> None:
        """Handle a task failure with optional retry."""
        retries = self._retry_counts.get(task.id, 0)

        if retries < self._max_retries:
            self._retry_counts[task.id] = retries + 1
            task.status = TaskStatus.PENDING  # Re-enter the queue
            logger.info(
                f"Task {task.id} failed, retrying ({retries + 1}/{self._max_retries})"
            )
            self._emit(
                ExecutionEvent(
                    timestamp=time.time(),
                    event_type="task_retry",
                    task_id=task.id,
                    details={
                        "retry": retries + 1,
                        "error": result.get("error", "")[:200],
                    },
                )
            )
        else:
            task.status = TaskStatus.FAILED
            report.tasks_failed += 1
            logger.warning(f"Task {task.id} failed after {retries + 1} attempts")
            self._emit(
                ExecutionEvent(
                    timestamp=time.time(),
                    event_type="task_failed",
                    task_id=task.id,
                    details={"error": result.get("error", "")[:200]},
                )
            )

    def _update_milestones(self, report: ExecutionReport) -> None:
        """Check and update milestone completion status."""
        for milestone in self.plan.milestones:
            if milestone.status == MilestoneStatus.COMPLETED:
                continue

            task_statuses = {t.status for t in milestone.tasks}

            if all(s == TaskStatus.PASSED for s in task_statuses):
                milestone.status = MilestoneStatus.COMPLETED
                report.milestone_results[milestone.id] = "completed"
                self._emit(
                    ExecutionEvent(
                        timestamp=time.time(),
                        event_type="milestone_completed",
                        details={"milestone": milestone.id, "name": milestone.name},
                    )
                )
            elif TaskStatus.FAILED in task_statuses:
                milestone.status = MilestoneStatus.BLOCKED
                report.milestone_results[milestone.id] = "blocked"
            elif any(
                s in (TaskStatus.RUNNING, TaskStatus.PENDING) for s in task_statuses
            ):
                milestone.status = MilestoneStatus.IN_PROGRESS
                report.milestone_results[milestone.id] = "in_progress"

    def _emit(self, event: ExecutionEvent) -> None:
        """Record and optionally callback an execution event."""
        self._events.append(event)
        if self._on_event:
            self._on_event(event)
