"""Unit tests for the time-lapse company timeline feature."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from agency_os.timeline.collector import TimelineCollector
from agency_os.timeline.models import TimelineEvent, TimelineEventType

# ---------------------------------------------------------------------------
# TimelineEvent model tests
# ---------------------------------------------------------------------------


class TestTimelineEvent:
    def test_create_event(self):
        ev = TimelineEvent(
            org_id="org-1",
            tenant_id="t-1",
            event_type=TimelineEventType.TASK_COMPLETED,
            title="Agent completed task",
            agent_id="dev-001",
            agent_name="Senior Developer",
        )
        assert ev.org_id == "org-1"
        assert ev.event_type == TimelineEventType.TASK_COMPLETED
        assert ev.agent_id == "dev-001"
        assert isinstance(ev.timestamp, float)

    def test_to_dict(self):
        ev = TimelineEvent(
            org_id="org-1",
            tenant_id="t-1",
            event_type=TimelineEventType.ORG_STARTED,
            title="Org started",
            detail="6 agents",
            metadata={"package": "saas-dev-studio"},
        )
        d = ev.to_dict()
        assert d["event_type"] == "org.started"
        assert d["metadata"]["package"] == "saas-dev-studio"
        assert d["detail"] == "6 agents"
        # tenant_id must never leak to API responses
        assert "tenant_id" not in d

    def test_to_db_row(self):
        ev = TimelineEvent(
            org_id="org-1",
            tenant_id="t-1",
            event_type=TimelineEventType.TASK_BID_PLACED,
            title="Agent bid $10",
            metadata={"bid_amount": 10.0},
        )
        row = ev.to_db_row()
        assert row["event_type"] == "task.bid_placed"
        assert '"bid_amount"' in row["metadata_json"]
        assert row["org_id"] == "org-1"

    def test_from_db_row(self):
        row = {
            "org_id": "org-1",
            "tenant_id": "t-1",
            "agent_id": "dev-001",
            "agent_name": "Dev",
            "agent_division": "engineering",
            "agent_color": "green",
            "event_type": "task.completed",
            "title": "Dev completed task",
            "detail": None,
            "artifact_type": "code",
            "artifact_ref": "main.py",
            "budget_snapshot": 90.0,
            "reputation_snapshot": 1.1,
            "metadata_json": '{"task_id": "t-1"}',
            "timestamp": 1000.0,
        }
        ev = TimelineEvent.from_db_row(row)
        assert ev.event_type == TimelineEventType.TASK_COMPLETED
        assert ev.artifact_type == "code"
        assert ev.metadata == {"task_id": "t-1"}

    def test_from_db_row_no_metadata(self):
        row = {
            "org_id": "org-1",
            "tenant_id": "t-1",
            "event_type": "org.started",
            "title": "Started",
            "timestamp": 1000.0,
        }
        ev = TimelineEvent.from_db_row(row)
        assert ev.metadata == {}


# ---------------------------------------------------------------------------
# TimelineCollector tests
# ---------------------------------------------------------------------------


class TestTimelineCollector:
    def test_record_and_get_events(self):
        collector = TimelineCollector()
        ev = TimelineEvent(
            org_id="org-1",
            tenant_id="t-1",
            event_type=TimelineEventType.ORG_STARTED,
            title="Started",
        )
        collector.record(ev)

        events = collector.get_events("org-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "org.started"

    def test_get_events_filters_by_org(self):
        collector = TimelineCollector()
        for org in ["org-1", "org-2"]:
            collector.record(
                TimelineEvent(
                    org_id=org,
                    tenant_id="t-1",
                    event_type=TimelineEventType.ORG_STARTED,
                    title=f"Started {org}",
                )
            )
        assert len(collector.get_events("org-1")) == 1
        assert len(collector.get_events("org-2")) == 1

    def test_get_events_filters_by_time(self):
        collector = TimelineCollector()
        now = time.time()
        for i in range(3):
            collector.record(
                TimelineEvent(
                    org_id="org-1",
                    tenant_id="t-1",
                    event_type=TimelineEventType.TASK_SUBMITTED,
                    title=f"Task {i}",
                    timestamp=now + i * 10,
                )
            )
        events = collector.get_events("org-1", since=now + 5)
        assert len(events) == 2

    def test_get_events_filters_by_agent(self):
        collector = TimelineCollector()
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done",
                agent_id="dev-001",
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done",
                agent_id="pm-001",
            )
        )
        events = collector.get_events("org-1", agent_id="dev-001")
        assert len(events) == 1
        assert events[0]["agent_id"] == "dev-001"

    def test_get_events_filters_by_event_type(self):
        collector = TimelineCollector()
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done",
            )
        )
        events = collector.get_events("org-1", event_types=["task.completed"])
        assert len(events) == 1

    def test_get_events_respects_limit(self):
        collector = TimelineCollector()
        for i in range(10):
            collector.record(
                TimelineEvent(
                    org_id="org-1",
                    tenant_id="t-1",
                    event_type=TimelineEventType.TASK_SUBMITTED,
                    title=f"Task {i}",
                )
            )
        events = collector.get_events("org-1", limit=3)
        assert len(events) == 3

    def test_get_events_tenant_isolation(self):
        """Events from other tenants must not be returned."""
        collector = TimelineCollector()
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started t-1",
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-2",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started t-2",
            )
        )
        # Without tenant_id, both are returned (backwards compat)
        assert len(collector.get_events("org-1")) == 2
        # With tenant_id, only matching tenant is returned
        assert len(collector.get_events("org-1", tenant_id="t-1")) == 1
        assert len(collector.get_events("org-1", tenant_id="t-2")) == 1

    def test_get_replay_tenant_isolation(self):
        collector = TimelineCollector()
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-other",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Other tenant",
            )
        )
        replay = collector.get_replay("org-1", tenant_id="t-1")
        assert len(replay["events"]) == 1

    def test_get_summary_tenant_isolation(self):
        collector = TimelineCollector()
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-other",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Other tenant",
            )
        )
        summary = collector.get_summary("org-1", tenant_id="t-1")
        assert summary["total_events"] == 1

    def test_get_replay_empty(self):
        collector = TimelineCollector()
        replay = collector.get_replay("org-nonexistent")
        assert replay["events"] == []
        assert replay["duration_seconds"] == 0

    def test_get_replay_builds_manifest(self):
        collector = TimelineCollector()
        now = time.time()

        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
                timestamp=now,
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done",
                agent_id="dev-001",
                agent_name="Dev",
                agent_division="engineering",
                agent_color="green",
                timestamp=now + 30,
            )
        )

        replay = collector.get_replay("org-1", speed=2.0)
        assert replay["org_id"] == "org-1"
        assert len(replay["events"]) == 2
        assert len(replay["agents"]) == 1
        assert replay["agents"][0]["agent_id"] == "dev-001"
        assert replay["duration_seconds"] == pytest.approx(30.0)
        assert replay["replay_duration_seconds"] == pytest.approx(15.0)
        assert replay["speed"] == 2.0

        # Check relative_time and replay_time
        assert replay["events"][0]["relative_time"] == 0
        assert replay["events"][1]["relative_time"] == pytest.approx(30.0)
        assert replay["events"][1]["replay_time"] == pytest.approx(15.0)

    def test_get_summary(self):
        collector = TimelineCollector()
        now = time.time()

        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
                timestamp=now,
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done",
                agent_id="dev-001",
                timestamp=now + 60,
            )
        )
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.TASK_COMPLETED,
                title="Done 2",
                agent_id="pm-001",
                timestamp=now + 90,
            )
        )

        summary = collector.get_summary("org-1")
        assert summary["total_events"] == 3
        assert summary["unique_agents"] == 2
        assert summary["event_types"]["task.completed"] == 2
        assert summary["event_types"]["org.started"] == 1
        assert summary["duration_seconds"] == pytest.approx(90.0)

    def test_get_summary_empty(self):
        collector = TimelineCollector()
        summary = collector.get_summary("org-nonexistent")
        assert summary["total_events"] == 0

    def test_convenience_org_started(self):
        collector = TimelineCollector()
        collector.org_started("org-1", "t-1", "saas-dev-studio", 6)

        events = collector.get_events("org-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "org.started"
        assert "saas-dev-studio" in events[0]["title"]

    def test_convenience_task_submitted(self):
        collector = TimelineCollector()
        collector.task_submitted("org-1", "t-1", "task-1", "Build landing page")

        events = collector.get_events("org-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "task.submitted"

    def test_buffer_limit(self):
        """Buffer should not exceed MAX_BUFFER_SIZE."""
        collector = TimelineCollector()
        for i in range(10_001):
            collector.record(
                TimelineEvent(
                    org_id="org-1",
                    tenant_id="t-1",
                    event_type=TimelineEventType.TASK_SUBMITTED,
                    title=f"Task {i}",
                )
            )
        assert len(collector._buffer) == 10_000

    def test_persist_called_with_db(self):
        mock_db = MagicMock()
        collector = TimelineCollector(db=mock_db)

        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
            )
        )

        mock_db.save_timeline_event.assert_called_once()
        row = mock_db.save_timeline_event.call_args[0][0]
        assert row["event_type"] == "org.started"

    def test_persist_failure_does_not_crash(self):
        mock_db = MagicMock()
        mock_db.save_timeline_event.side_effect = RuntimeError("db error")

        collector = TimelineCollector(db=mock_db)
        # Should not raise
        collector.record(
            TimelineEvent(
                org_id="org-1",
                tenant_id="t-1",
                event_type=TimelineEventType.ORG_STARTED,
                title="Started",
            )
        )
        # Event still buffered in memory
        assert len(collector.get_events("org-1")) == 1


# ---------------------------------------------------------------------------
# TimelineEventType enum tests
# ---------------------------------------------------------------------------


class TestTimelineEventType:
    def test_all_types_have_string_values(self):
        for member in TimelineEventType:
            assert isinstance(member.value, str)
            assert "." in member.value  # All follow "category.action" pattern

    def test_metadata_size_cap_in_db_row(self):
        """Oversized metadata should be dropped in to_db_row to prevent abuse."""
        large_metadata = {"data": "x" * 20_000}
        ev = TimelineEvent(
            org_id="org-1",
            tenant_id="t-1",
            event_type=TimelineEventType.ORG_STARTED,
            title="Started",
            metadata=large_metadata,
        )
        row = ev.to_db_row()
        assert row["metadata_json"] is None  # Dropped because too large

    def test_task_types_exist(self):
        assert TimelineEventType.TASK_SUBMITTED.value == "task.submitted"
        assert TimelineEventType.TASK_BID_PLACED.value == "task.bid_placed"
        assert TimelineEventType.TASK_ASSIGNED.value == "task.assigned"
        assert TimelineEventType.TASK_COMPLETED.value == "task.completed"
        assert TimelineEventType.TASK_FAILED.value == "task.failed"
