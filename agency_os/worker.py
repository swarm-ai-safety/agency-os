"""Multi-tenant task consumer worker.

Polls the database for pending tasks across all tenants/orgs,
executes them, and updates results. Designed to scale horizontally.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from agency_os.governance.trust import compute_trust_score
from agency_os.metering.aggregator import (
    DEFAULT_COST_PER_1K_INPUT,
    DEFAULT_COST_PER_1K_OUTPUT,
    DEFAULT_MARGIN_RATE,
)
from agency_os.metering.collector import MeteringCollector, TaskOutcome, UsageEvent
from agency_os.observability import configure_logging
from agency_os.observability.shadow_git import ShadowGit
from agency_os.observability.state import StateManager
from agency_os.observability.trajectory import TrajectoryRecorder
from agency_os.orchestration.organization import Organization
from agency_os.service.webhooks import CIRCUIT_BREAKER_TRIPPED, WebhookEvent
from agency_os.storage import Database

configure_logging(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    json_format=os.environ.get("LOG_JSON", "true").lower() not in ("0", "false", "no"),
)
logger = logging.getLogger(__name__)

# Graceful shutdown support
_shutdown_requested = False


def signal_handler(sig: int, frame: Any) -> None:
    global _shutdown_requested
    logger.info("Shutdown signal received, will exit after current task")
    _shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class TaskWorker:
    """Multi-tenant task consumer that polls and executes tasks."""

    def __init__(
        self,
        db: Database,
        metering: MeteringCollector | None = None,
        webhook_dispatcher: Any | None = None,
        poll_interval_sec: float = 5.0,
        worker_id: str | None = None,
    ):
        self.db = db
        self.metering = metering
        self.webhook_dispatcher = webhook_dispatcher
        self.poll_interval_sec = poll_interval_sec
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._org_cache: dict[str, tuple[Organization, float]] = {}
        self._cache_ttl_sec = 300.0  # 5 minutes
        self._budget_lock = threading.Lock()

        logger.info(f"TaskWorker initialized: {self.worker_id}")

    def _get_or_create_org(self, org_id: str, tenant_id: str) -> Organization:
        """Get organization from cache or create it.

        Organizations are cached for 5 minutes to avoid repeated package loading.
        """
        now = time.time()

        # Check cache
        if org_id in self._org_cache:
            org, cached_at = self._org_cache[org_id]
            if now - cached_at < self._cache_ttl_sec:
                return org

        # Load from database
        org_data = self.db.get_org(org_id, tenant_id=tenant_id)
        if org_data is None:
            raise RuntimeError(f"Organization {org_id} not found in database")

        # Create and start organization
        package_name = org_data.get("package_name")
        if not package_name:
            raise RuntimeError(f"Organization {org_id} has no package_name")

        org = Organization.from_builtin(package_name, org_id=org_id)
        org.start()

        # Cache it
        self._org_cache[org_id] = (org, now)

        logger.info(
            f"Loaded organization {org_id} (package={package_name}, tenant={tenant_id})"
        )

        return org

    @staticmethod
    def _calc_task_customer_cost(tokens_in: int, tokens_out: int) -> float:
        """Calculate customer cost for task execution using default rates."""
        provider_cost = (tokens_in / 1000) * DEFAULT_COST_PER_1K_INPUT + (
            tokens_out / 1000
        ) * DEFAULT_COST_PER_1K_OUTPUT
        return provider_cost * (1 + DEFAULT_MARGIN_RATE)

    def _check_tenant_budget(self, tenant_id: str) -> tuple[bool, float, float]:
        """Check if tenant has budget remaining.

        Returns (allowed, spent, limit). Loads tenant from DB directly
        to get the freshest metadata (avoids stale in-memory state).
        """
        tenant_data = self.db.get_tenant(tenant_id)
        if tenant_data is None:
            # Tenant not found — allow execution (soft enforcement)
            return True, 0.0, 100.0
        metadata = tenant_data.get("metadata") or {}
        spent = float(metadata.get("total_spent_usd", 0.0))
        limit = float(metadata.get("budget_limit_usd", 100.0))
        return spent < limit, spent, limit

    def _update_tenant_spend(self, tenant_id: str, cost: float) -> tuple[float, float]:
        """Atomically update tenant total_spent_usd and persist.

        Returns (new_spent, budget_limit).
        """
        with self._budget_lock:
            tenant_data = self.db.get_tenant(tenant_id)
            if tenant_data is None:
                return cost, 100.0
            metadata = tenant_data.get("metadata") or {}
            spent = float(metadata.get("total_spent_usd", 0.0))
            limit = float(metadata.get("budget_limit_usd", 100.0))
            new_spent = spent + cost
            metadata["total_spent_usd"] = new_spent
            tenant_data["metadata"] = metadata
            self.db.save_tenant(tenant_data)
            return new_spent, limit

    def _flag_tenant_over_budget(
        self, tenant_id: str, spent: float, limit: float, task_id: str
    ) -> None:
        """Log a budget-exceeded event after task execution."""
        self.db.save_metering_event(
            {
                "tenant_id": tenant_id,
                "org_id": "worker",
                "agent_id": "worker",
                "event_type": "budget.exceeded_post_task",
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": time.time(),
                "metadata": {
                    "task_id": task_id,
                    "total_spent_usd": spent,
                    "budget_limit_usd": limit,
                    "worker_id": self.worker_id,
                },
            }
        )
        logger.warning(
            "budget.exceeded_post_task tenant=%s spent=%.6f limit=%.6f task=%s",
            tenant_id,
            spent,
            limit,
            task_id,
        )

    def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single task and update its status."""
        task_id = task["task_id"]
        org_id = task["org_id"]
        tenant_id = task["tenant_id"]
        agent_id = task.get("assigned_to")
        description = task.get("description", "")
        metadata = task.get("metadata", {})

        logger.info(
            f"Executing task {task_id}: org={org_id}, agent={agent_id}, tenant={tenant_id}"
        )

        # Pre-execution budget check
        allowed, spent, limit = self._check_tenant_budget(tenant_id)
        if not allowed:
            logger.warning(
                "Task %s rejected: tenant %s over budget (spent=%.2f, limit=%.2f)",
                task_id,
                tenant_id,
                spent,
                limit,
            )
            self.db.update_task_status(
                task_id,
                "failed",
                {"error": "Tenant budget exceeded", "worker_id": self.worker_id},
                tenant_id=tenant_id,
            )
            self.db.save_metering_event(
                {
                    "tenant_id": tenant_id,
                    "org_id": org_id,
                    "agent_id": agent_id or "worker",
                    "event_type": "budget.task_rejected",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "timestamp": time.time(),
                    "metadata": {
                        "task_id": task_id,
                        "total_spent_usd": spent,
                        "budget_limit_usd": limit,
                    },
                }
            )
            return

        start_time = time.time()
        recorder = self._create_trajectory_recorder(
            agent_id=agent_id or "unknown",
            task_id=task_id,
            tenant_id=tenant_id,
            org_id=org_id,
        )

        # Optional shadow git file tracking
        state_mgr = self._init_state_tracking(metadata, task_id)

        try:
            # Load organization
            org = self._get_or_create_org(org_id, tenant_id)

            # Get agent
            if not agent_id:
                raise RuntimeError(f"Task {task_id} has no assigned agent")
            agent = org.get_agent(agent_id)
            if agent is None:
                raise RuntimeError(f"Agent {agent_id} not found in org {org_id}")

            # Record pre-execution steps in trajectory
            recorder.record_system_step(agent.llm_config.system_prompt or "")
            recorder.record_user_step(description)

            # Execute task
            result = agent.execute_task(description, metadata or None)
            duration_sec = time.time() - start_time
            success = result.get("success", False)

            # Check for file changes after execution
            if state_mgr is not None:
                state_mgr.check_for_writes(step_id=recorder._step_counter + 1)
                recorder.set_file_changes(state_mgr.to_changelog())

            # Record agent response in trajectory
            recorder.record_agent_step(
                response_text=result.get("response", ""),
                tokens_in=result.get("tokens_in", 0),
                tokens_out=result.get("tokens_out", 0),
            )

            # Record metering
            if self.metering is not None:
                self.metering.record(
                    UsageEvent(
                        tenant_id=tenant_id,
                        org_id=org_id,
                        agent_id=agent_id,
                        event_type="llm_call",
                        tokens_in=result.get("tokens_in", 0),
                        tokens_out=result.get("tokens_out", 0),
                        metadata={"task_id": task_id},
                    )
                )

                # Record task outcome for trust scoring
                outcome = TaskOutcome.success if success else TaskOutcome.failure
                self.metering.record_task_outcome(
                    tenant_id=tenant_id,
                    org_id=org_id,
                    agent_id=agent_id,
                    outcome=outcome,
                    task_id=task_id,
                    duration_sec=duration_sec,
                )

            # Persist metering events
            self.db.save_metering_event(
                {
                    "tenant_id": tenant_id,
                    "org_id": org_id,
                    "agent_id": agent_id,
                    "event_type": "llm_call",
                    "tokens_in": result.get("tokens_in", 0),
                    "tokens_out": result.get("tokens_out", 0),
                    "timestamp": time.time(),
                    "metadata": {"task_id": task_id},
                }
            )

            self.db.save_metering_event(
                {
                    "tenant_id": tenant_id,
                    "org_id": org_id,
                    "agent_id": agent_id,
                    "event_type": "task_outcome",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "timestamp": time.time(),
                    "metadata": {
                        "task_id": task_id,
                        "outcome": outcome.value if self.metering else "unknown",
                        "duration_sec": duration_sec,
                    },
                }
            )

            # Track spend on tenant budget
            tokens_in = result.get("tokens_in", 0)
            tokens_out = result.get("tokens_out", 0)
            task_cost = self._calc_task_customer_cost(tokens_in, tokens_out)
            if task_cost > 0:
                new_spent, budget_limit = self._update_tenant_spend(
                    tenant_id, task_cost
                )
                if new_spent > budget_limit:
                    self._flag_tenant_over_budget(
                        tenant_id, new_spent, budget_limit, task_id
                    )

            # Update agent reputation
            reputation_delta = 0.05 if success else -0.1
            agent.record_task_outcome(success, reputation_delta)

            # Persist wallet snapshot
            self.db.save_wallet_snapshot(
                {
                    "org_id": org_id,
                    "agent_id": agent_id,
                    "balance": agent.balance,
                    "reputation": agent.reputation,
                    "snapshot_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Persist trust score snapshot
            if self.metering is not None:
                trust = compute_trust_score(self.metering, agent_id, tenant_id)
                self.db.save_trust_score(
                    {
                        "tenant_id": tenant_id,
                        "org_id": org_id,
                        "agent_id": agent_id,
                        "score": trust.score,
                        "tier": trust.tier,
                        "total_tasks": trust.total_tasks,
                        "successes": trust.successes,
                        "failures": trust.failures,
                        "partials": trust.partials,
                        "computed_at": time.time(),
                    }
                )

            # Attach governance metadata + persist trajectory
            if self.metering is not None:
                recorder.set_governance(
                    preset=task.get("governance_preset", "unknown"),
                    trust_tier=trust.tier,
                    trust_score=trust.score,
                )
            self._persist_trajectory(recorder, task_id, tenant_id)

            # Update task status
            status = "completed" if success else "failed"
            self.db.update_task_status(task_id, status, result, tenant_id=tenant_id)

            if not success:
                self._maybe_emit_circuit_breaker_trip(
                    org=org,
                    task_id=task_id,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    agent_id=agent_id,
                    duration_sec=duration_sec,
                    reason=result.get("error", "task execution failed"),
                )

            # Dispatch webhook notification
            if self.webhook_dispatcher is not None:
                try:
                    from agency_os.service.webhooks import TASK_COMPLETED, WebhookEvent

                    event = WebhookEvent(
                        event_type=TASK_COMPLETED,
                        org_id=org_id,
                        payload={
                            "task_id": task_id,
                            "agent_id": agent_id,
                            "status": status,
                            "success": success,
                            "tokens_in": result.get("tokens_in", 0),
                            "tokens_out": result.get("tokens_out", 0),
                            "duration_sec": duration_sec,
                        },
                    )
                    self.webhook_dispatcher.dispatch(event)
                except Exception:
                    logger.exception(f"Failed to dispatch webhook for task {task_id}")

            logger.info(
                f"Task {task_id} {status}: tokens_in={result.get('tokens_in', 0)}, "
                f"tokens_out={result.get('tokens_out', 0)}, duration={duration_sec:.1f}s"
            )

        except Exception as e:
            logger.exception(f"Task {task_id} failed with exception: {e}")
            duration_sec = time.time() - start_time

            # Record error in trajectory and persist
            recorder.record_error_step(str(e))
            self._persist_trajectory(recorder, task_id, tenant_id)

            # Record failure outcome
            if self.metering is not None:
                self.metering.record_task_outcome(
                    tenant_id=tenant_id,
                    org_id=org_id,
                    agent_id=agent_id or "unknown",
                    outcome=TaskOutcome.failure,
                    task_id=task_id,
                    duration_sec=duration_sec,
                )

            self.db.save_metering_event(
                {
                    "tenant_id": tenant_id,
                    "org_id": org_id,
                    "agent_id": agent_id or "unknown",
                    "event_type": "task_outcome",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "timestamp": time.time(),
                    "metadata": {
                        "task_id": task_id,
                        "outcome": "failure",
                        "duration_sec": duration_sec,
                        "error": str(e),
                    },
                }
            )

            # Update task status to failed
            self.db.update_task_status(
                task_id,
                "failed",
                {"error": str(e), "worker_id": self.worker_id},
                tenant_id=tenant_id,
            )

            if agent_id:
                try:
                    org = self._get_or_create_org(org_id, tenant_id)
                    self._maybe_emit_circuit_breaker_trip(
                        org=org,
                        task_id=task_id,
                        tenant_id=tenant_id,
                        org_id=org_id,
                        agent_id=agent_id,
                        duration_sec=duration_sec,
                        reason=str(e),
                    )
                except Exception:
                    logger.exception(
                        "Failed circuit-breaker evaluation for task %s", task_id
                    )

            # Dispatch webhook notification for failed task
            if self.webhook_dispatcher is not None:
                try:
                    from agency_os.service.webhooks import TASK_COMPLETED, WebhookEvent

                    event = WebhookEvent(
                        event_type=TASK_COMPLETED,
                        org_id=org_id,
                        payload={
                            "task_id": task_id,
                            "agent_id": agent_id or "unknown",
                            "status": "failed",
                            "success": False,
                            "error": str(e),
                            "duration_sec": duration_sec,
                        },
                    )
                    self.webhook_dispatcher.dispatch(event)
                except Exception:
                    logger.exception(
                        f"Failed to dispatch webhook for failed task {task_id}"
                    )

    @staticmethod
    def _init_state_tracking(
        metadata: dict[str, Any] | None, task_id: str
    ) -> StateManager | None:
        """Initialize shadow git file tracking if task has a work_dir."""
        work_dir_str = (metadata or {}).get("work_dir")
        if not work_dir_str:
            return None
        try:
            from pathlib import Path

            work_dir = Path(work_dir_str)
            if not work_dir.is_dir():
                return None
            git_dir = work_dir / ".shadow_git" / task_id
            sg = ShadowGit(work_dir, git_dir)
            sg.init()
            sg.commit_baseline()
            return StateManager(work_dir, sg)
        except Exception:
            logger.exception(
                "Failed to init shadow git for task %s work_dir=%s",
                task_id,
                work_dir_str,
            )
            return None

    @staticmethod
    def _create_trajectory_recorder(
        agent_id: str,
        task_id: str,
        tenant_id: str,
        org_id: str,
        agent_name: str | None = None,
        model_name: str | None = None,
    ) -> "TrajectoryRecorder":
        """Create a TrajectoryRecorder for a task execution."""
        return TrajectoryRecorder(
            agent_id=agent_id,
            agent_name=agent_name or agent_id,
            model_name=model_name,
            task_id=task_id,
            tenant_id=tenant_id,
            org_id=org_id,
        )

    def _persist_trajectory(
        self,
        recorder: "TrajectoryRecorder",
        task_id: str,
        tenant_id: str,
    ) -> None:
        """Persist the trajectory to the database, swallowing errors."""
        try:
            import json as _json

            trajectory_dict = recorder.to_dict()
            self.db.save_trajectory(
                task_id, _json.dumps(trajectory_dict), tenant_id=tenant_id
            )
        except Exception:
            logger.exception("Failed to persist trajectory for task %s", task_id)

    def _circuit_breaker_threshold(self, org: Organization) -> int | None:
        """Return configured circuit-breaker threshold for this org."""
        from agency_os.governance.presets import resolve_governance

        try:
            resolved = resolve_governance(org.package.governance)
            if not resolved.circuit_breaker_enabled:
                return None
            threshold = int(resolved.freeze_threshold_violations)
            return max(1, threshold)
        except Exception:
            logger.exception(
                "Failed to resolve circuit-breaker config for %s", org.org_id
            )
            return None

    def _consecutive_failures(self, tenant_id: str, org_id: str, agent_id: str) -> int:
        """Count current trailing failure streak for an agent."""
        tasks = self.db.list_tasks(org_id, tenant_id=tenant_id)
        relevant = [t for t in tasks if t.get("assigned_to") == agent_id]
        relevant.sort(key=lambda t: t.get("created_at") or "")

        streak = 0
        for task in reversed(relevant):
            status = task.get("status")
            if status == "failed":
                streak += 1
                continue
            if status == "completed":
                break
        return streak

    def _maybe_emit_circuit_breaker_trip(
        self,
        *,
        org: Organization,
        task_id: str,
        tenant_id: str,
        org_id: str,
        agent_id: str | None,
        duration_sec: float,
        reason: str,
    ) -> None:
        """Emit true circuit-breaker trip event when failure streak reaches threshold."""
        if not agent_id:
            return
        threshold = self._circuit_breaker_threshold(org)
        if threshold is None:
            return

        streak = self._consecutive_failures(tenant_id, org_id, agent_id)
        if streak != threshold:
            return

        metadata = {
            "task_id": task_id,
            "agent_id": agent_id,
            "threshold": threshold,
            "consecutive_failures": streak,
            "duration_sec": duration_sec,
            "reason": reason,
            "worker_id": self.worker_id,
        }
        self.db.save_metering_event(
            {
                "tenant_id": tenant_id,
                "org_id": org_id,
                "agent_id": agent_id,
                "event_type": CIRCUIT_BREAKER_TRIPPED,
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": time.time(),
                "metadata": metadata,
            }
        )

        if self.webhook_dispatcher is not None:
            try:
                self.webhook_dispatcher.dispatch(
                    WebhookEvent(
                        event_type=CIRCUIT_BREAKER_TRIPPED,
                        org_id=org_id,
                        payload=metadata,
                    )
                )
            except Exception:
                logger.exception(
                    "Failed dispatching circuit breaker webhook for task %s", task_id
                )

        logger.warning(
            "circuit_breaker.tripped tenant=%s org=%s agent=%s threshold=%d streak=%d",
            tenant_id,
            org_id,
            agent_id,
            threshold,
            streak,
        )

    def run(self) -> None:
        """Main worker loop: poll for tasks and execute them."""
        logger.info(f"Worker {self.worker_id} starting...")

        while not _shutdown_requested:
            try:
                # Poll for pending tasks
                tasks = self.db.poll_pending_tasks(limit=10)

                if not tasks:
                    # No tasks available, sleep and retry
                    time.sleep(self.poll_interval_sec)
                    continue

                # Try to claim and execute each task
                for task in tasks:
                    if _shutdown_requested:
                        break

                    task_id = task["task_id"]

                    # Try to claim the task atomically
                    if not self.db.claim_task(task_id, self.worker_id):
                        # Another worker claimed it first
                        logger.debug(
                            f"Task {task_id} already claimed by another worker"
                        )
                        continue

                    # We successfully claimed it, execute it
                    self._execute_task(task)

            except Exception:
                logger.exception("Worker loop error, will retry")
                time.sleep(self.poll_interval_sec)

        logger.info(f"Worker {self.worker_id} shutting down")


def main() -> None:
    """Entry point for the worker process."""
    db_path = os.environ.get("DATABASE_PATH", "agency_os.db")
    poll_interval = float(os.environ.get("WORKER_POLL_INTERVAL", "5.0"))

    logger.info(f"Starting task worker: db={db_path}, poll_interval={poll_interval}s")

    db = Database(db_path)
    metering = MeteringCollector()  # Multi-tenant collector

    worker = TaskWorker(db, metering, poll_interval_sec=poll_interval)

    try:
        worker.run()
    finally:
        db.close()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    main()
