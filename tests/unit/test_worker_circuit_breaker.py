"""Worker circuit-breaker observability tests."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from agency_os.storage import Database
from agency_os.worker import TaskWorker


def _seed_tenant_and_org(
    db: Database, tenant_id: str, org_id: str, package_name: str = "devops_team"
) -> None:
    db.save_tenant(
        {
            "tenant_id": tenant_id,
            "name": "Test Tenant",
            "api_key_hash": "hash",
            "active": True,
            "metadata": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db.save_org(
        {
            "org_id": org_id,
            "tenant_id": tenant_id,
            "package_name": package_name,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def test_emits_circuit_breaker_trip_when_failure_streak_hits_threshold():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db = Database(f.name)
        tenant_id = "tenant-test"
        org_id = "org-test"
        agent_id = "agent-test"
        _seed_tenant_and_org(db, tenant_id, org_id)

        base = datetime.now(timezone.utc)
        for idx, status in enumerate(["completed", "failed", "failed"]):
            db.save_task(
                {
                    "task_id": f"task-{idx}",
                    "tenant_id": tenant_id,
                    "org_id": org_id,
                    "description": "x",
                    "assigned_to": agent_id,
                    "status": status,
                    "governance_preset": "conservative",
                    "result": None,
                    "created_at": (base + timedelta(seconds=idx)).isoformat(),
                }
            )

        worker = TaskWorker(db, webhook_dispatcher=MagicMock())
        org = worker._get_or_create_org(org_id, tenant_id)
        threshold = worker._circuit_breaker_threshold(org)
        assert threshold == 2
        worker._maybe_emit_circuit_breaker_trip(
            org=org,
            task_id="task-2",
            tenant_id=tenant_id,
            org_id=org_id,
            agent_id=agent_id,
            duration_sec=1.2,
            reason="boom",
        )

        events = db.get_metering_events(tenant_id)
        trips = [e for e in events if e["event_type"] == "circuit_breaker.tripped"]
        assert len(trips) == 1
        assert trips[0]["metadata"]["consecutive_failures"] == threshold
        assert trips[0]["metadata"]["threshold"] == threshold
        assert worker.webhook_dispatcher.dispatch.call_count == 1
