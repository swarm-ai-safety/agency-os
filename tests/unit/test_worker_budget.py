"""Worker budget enforcement tests.

Verifies that TaskWorker:
1. Rejects tasks when tenant budget is exhausted (pre-execution check)
2. Updates total_spent_usd on tenant metadata after task execution
3. Flags tenants that exceed budget post-execution
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from agency_os.metering.aggregator import (
    DEFAULT_COST_PER_1K_INPUT,
    DEFAULT_COST_PER_1K_OUTPUT,
    DEFAULT_MARGIN_RATE,
)
from agency_os.storage import Database
from agency_os.worker import TaskWorker


def _make_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return Database(f.name), f.name


def _seed(db, tenant_id, org_id, budget_limit=100.0, total_spent=0.0):
    db.save_tenant(
        {
            "tenant_id": tenant_id,
            "name": "Test Tenant",
            "api_key_hash": "hash",
            "active": True,
            "metadata": json.dumps(
                {
                    "budget_limit_usd": budget_limit,
                    "total_spent_usd": total_spent,
                }
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db.save_org(
        {
            "org_id": org_id,
            "tenant_id": tenant_id,
            "package_name": "devops_team",
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _make_task(task_id, tenant_id, org_id, agent_id="agent-1"):
    return {
        "task_id": task_id,
        "tenant_id": tenant_id,
        "org_id": org_id,
        "assigned_to": agent_id,
        "description": "test task",
        "metadata": {},
    }


class TestWorkerBudgetPreCheck:
    def test_rejects_task_when_budget_exhausted(self):
        db, _ = _make_db()
        tid, oid = "tenant-1", "org-1"
        _seed(db, tid, oid, budget_limit=10.0, total_spent=10.0)

        worker = TaskWorker(db)
        task = _make_task("task-1", tid, oid)

        # Save task first so update_task_status can find it
        db.save_task(
            {
                "task_id": "task-1",
                "tenant_id": tid,
                "org_id": oid,
                "description": "test",
                "assigned_to": "agent-1",
                "status": "assigned",
                "governance_preset": "balanced",
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        worker._execute_task(task)

        # Task should be marked as failed
        result = db.get_task("task-1", tenant_id=tid)
        assert result["status"] == "failed"
        assert "budget exceeded" in result["result"]["error"].lower()

        # Budget rejection event should be logged
        events = db.get_metering_events(tid)
        rejected = [e for e in events if e["event_type"] == "budget.task_rejected"]
        assert len(rejected) == 1

    def test_allows_task_when_budget_has_room(self):
        db, _ = _make_db()
        tid, oid = "tenant-1", "org-1"
        _seed(db, tid, oid, budget_limit=100.0, total_spent=5.0)

        allowed, spent, limit = TaskWorker(db)._check_tenant_budget(tid)
        assert allowed is True
        assert spent == 5.0
        assert limit == 100.0

    def test_rejects_when_spent_exceeds_limit(self):
        db, _ = _make_db()
        tid, oid = "tenant-1", "org-1"
        _seed(db, tid, oid, budget_limit=10.0, total_spent=15.0)

        allowed, spent, limit = TaskWorker(db)._check_tenant_budget(tid)
        assert allowed is False


class TestWorkerSpendTracking:
    def test_calc_task_customer_cost(self):
        cost = TaskWorker._calc_task_customer_cost(1000, 500)
        expected_provider = (1000 / 1000) * DEFAULT_COST_PER_1K_INPUT + (
            500 / 1000
        ) * DEFAULT_COST_PER_1K_OUTPUT
        expected = expected_provider * (1 + DEFAULT_MARGIN_RATE)
        assert abs(cost - expected) < 1e-9

    def test_calc_task_customer_cost_zero_tokens(self):
        assert TaskWorker._calc_task_customer_cost(0, 0) == 0.0

    def test_update_tenant_spend_persists(self):
        db, _ = _make_db()
        tid = "tenant-1"
        _seed(db, tid, "org-1", budget_limit=100.0, total_spent=5.0)

        worker = TaskWorker(db)
        new_spent, limit = worker._update_tenant_spend(tid, 3.0)

        assert new_spent == 8.0
        assert limit == 100.0

        # Verify persisted to DB
        tenant_data = db.get_tenant(tid)
        metadata = tenant_data["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        assert metadata["total_spent_usd"] == 8.0

    def test_spend_tracked_after_task_execution(self):
        """End-to-end: task execution updates total_spent_usd."""
        db, _ = _make_db()
        tid, oid = "tenant-1", "org-1"
        _seed(db, tid, oid, budget_limit=100.0, total_spent=0.0)

        db.save_task(
            {
                "task_id": "task-1",
                "tenant_id": tid,
                "org_id": oid,
                "description": "test",
                "assigned_to": "agent-1",
                "status": "assigned",
                "governance_preset": "balanced",
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        worker = TaskWorker(db)

        # Mock the org/agent execution
        mock_agent = MagicMock()
        mock_agent.execute_task.return_value = {
            "success": True,
            "tokens_in": 2000,
            "tokens_out": 1000,
        }
        mock_agent.balance = 100.0
        mock_agent.reputation = 1.0

        mock_org = MagicMock()
        mock_org.get_agent.return_value = mock_agent

        with patch.object(worker, "_get_or_create_org", return_value=mock_org):
            worker._execute_task(_make_task("task-1", tid, oid))

        # Verify spend was updated
        tenant_data = db.get_tenant(tid)
        metadata = tenant_data["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        expected_cost = TaskWorker._calc_task_customer_cost(2000, 1000)
        assert metadata["total_spent_usd"] == expected_cost
        assert expected_cost > 0


class TestWorkerPostExecBudgetFlag:
    def test_flags_tenant_when_spend_exceeds_budget_post_exec(self):
        """When task execution pushes spend over budget, flag it."""
        db, _ = _make_db()
        tid, oid = "tenant-1", "org-1"
        # Budget is $1, already spent $0.99 — task will push over
        _seed(db, tid, oid, budget_limit=1.0, total_spent=0.99)

        db.save_task(
            {
                "task_id": "task-1",
                "tenant_id": tid,
                "org_id": oid,
                "description": "test",
                "assigned_to": "agent-1",
                "status": "assigned",
                "governance_preset": "balanced",
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        worker = TaskWorker(db)

        mock_agent = MagicMock()
        mock_agent.execute_task.return_value = {
            "success": True,
            "tokens_in": 5000,
            "tokens_out": 2000,
        }
        mock_agent.balance = 100.0
        mock_agent.reputation = 1.0

        mock_org = MagicMock()
        mock_org.get_agent.return_value = mock_agent

        with patch.object(worker, "_get_or_create_org", return_value=mock_org):
            worker._execute_task(_make_task("task-1", tid, oid))

        # Verify budget exceeded event was logged
        events = db.get_metering_events(tid)
        exceeded = [e for e in events if e["event_type"] == "budget.exceeded_post_task"]
        assert len(exceeded) == 1
        meta = exceeded[0]["metadata"]
        assert meta["task_id"] == "task-1"
        assert meta["total_spent_usd"] > 1.0
