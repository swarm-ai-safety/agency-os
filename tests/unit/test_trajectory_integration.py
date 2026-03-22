"""Integration tests for trajectory storage and worker wiring."""

import json
import time

import pytest

from agency_os.observability.trajectory import TrajectoryRecorder
from agency_os.storage import Database


@pytest.fixture
def db(tmp_path):
    """Create a fresh in-memory-like database for testing."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


@pytest.fixture
def sample_trajectory():
    """Build a sample trajectory dict."""
    recorder = TrajectoryRecorder(
        agent_id="agent-test",
        agent_name="Test Agent",
        model_name="claude-sonnet-4-20250514",
        task_id="task-001",
        tenant_id="tenant-t1",
        org_id="org-o1",
    )
    recorder.record_system_step("You are a test agent.")
    recorder.record_user_step("Do the thing.")
    recorder.record_agent_step(
        response_text="Done.",
        tokens_in=100,
        tokens_out=50,
    )
    recorder.set_governance(
        preset="balanced", task_type="stateless", trust_tier="medium"
    )
    return recorder.to_dict()


class TestTrajectoryStorage:
    def _create_task(
        self, db, task_id="task-001", tenant_id="tenant-t1", org_id="org-o1"
    ):
        """Helper to insert prerequisite tenant, org, and task rows."""
        db.save_tenant(
            {
                "tenant_id": tenant_id,
                "name": "Test Tenant",
                "api_key_hash": f"hash-{tenant_id}",
                "active": True,
                "metadata": "{}",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        db.save_org(
            {
                "org_id": org_id,
                "tenant_id": tenant_id,
                "package_name": "test-pkg",
                "status": "active",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        db.save_task(
            {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "org_id": org_id,
                "description": "Test task",
                "assigned_to": "agent-test",
                "status": "assigned",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def test_save_and_get_trajectory(self, db, sample_trajectory):
        self._create_task(db)
        trajectory_json = json.dumps(sample_trajectory)

        db.save_trajectory("task-001", trajectory_json, tenant_id="tenant-t1")

        result = db.get_trajectory("task-001", tenant_id="tenant-t1")
        assert result is not None
        assert result["schema_version"] == "ATIF-v1.6"
        assert result["agent"]["name"] == "Test Agent"
        assert len(result["steps"]) == 3
        assert result["extra"]["governance"]["preset"] == "balanced"

    def test_get_trajectory_returns_none_when_no_trajectory(self, db):
        self._create_task(db)
        result = db.get_trajectory("task-001", tenant_id="tenant-t1")
        assert result is None

    def test_get_trajectory_returns_none_for_missing_task(self, db):
        result = db.get_trajectory("nonexistent", tenant_id="tenant-t1")
        assert result is None

    def test_trajectory_tenant_isolation(self, db, sample_trajectory):
        self._create_task(db, task_id="task-001", tenant_id="tenant-t1")
        db.save_trajectory(
            "task-001", json.dumps(sample_trajectory), tenant_id="tenant-t1"
        )

        # Different tenant should not see the trajectory
        result = db.get_trajectory("task-001", tenant_id="tenant-other")
        assert result is None

    def test_trajectory_roundtrip_preserves_data(self, db, sample_trajectory):
        self._create_task(db)
        trajectory_json = json.dumps(sample_trajectory)

        db.save_trajectory("task-001", trajectory_json, tenant_id="tenant-t1")
        result = db.get_trajectory("task-001", tenant_id="tenant-t1")

        # Verify full round-trip fidelity
        assert result == sample_trajectory

    def test_trajectory_included_in_get_task(self, db, sample_trajectory):
        """Verify trajectory column is present when fetching the full task."""
        self._create_task(db)
        db.save_trajectory(
            "task-001", json.dumps(sample_trajectory), tenant_id="tenant-t1"
        )

        task = db.get_task("task-001", tenant_id="tenant-t1")
        assert task is not None
        # The trajectory column should be a raw JSON string in the task dict
        assert task.get("trajectory") is not None
        parsed = json.loads(task["trajectory"])
        assert parsed["schema_version"] == "ATIF-v1.6"
