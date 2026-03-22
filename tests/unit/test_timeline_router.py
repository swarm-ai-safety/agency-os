from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agency_os.service.api.routers import timeline
from agency_os.tenancy.tenant import Tenant


@pytest.fixture
def tenant() -> Tenant:
    return Tenant(tenant_id="tenant-1", name="Tenant 1", api_key="ak-test")


@pytest.fixture(autouse=True)
def reset_timeline_deps():
    timeline._timeline_collector = None
    timeline._timeline_db = None
    yield
    timeline._timeline_collector = None
    timeline._timeline_db = None


@pytest.mark.asyncio
async def test_get_timeline_uses_db_without_in_memory_org_lookup(tenant: Tenant):
    db = MagicMock()
    db.get_timeline_events.return_value = [
        {"org_id": "org-1", "event_type": "org.started", "timestamp": 1000.0}
    ]
    timeline.set_timeline_deps(collector=MagicMock(), db=db)

    payload = await timeline.get_timeline(
        org_id="org-1",
        tenant=tenant,
        since=None,
        until=None,
        event_type=None,
        agent_id=None,
        limit=500,
    )

    assert payload["org_id"] == "org-1"
    assert payload["count"] == 1
    assert payload["events"][0]["event_type"] == "org.started"
    db.get_timeline_events.assert_called_once_with(
        org_id="org-1",
        tenant_id="tenant-1",
        since=None,
        until=None,
        event_types=None,
        agent_id=None,
        limit=500,
    )


@pytest.mark.asyncio
async def test_get_replay_uses_persisted_events_when_db_available(tenant: Tenant):
    db = MagicMock()
    db.get_timeline_events.return_value = [
        {
            "org_id": "org-1",
            "tenant_id": "tenant-1",
            "agent_id": "a-1",
            "agent_name": "Agent 1",
            "agent_division": "engineering",
            "agent_color": "blue",
            "event_type": "org.started",
            "title": "Org started",
            "timestamp": 100.0,
        },
        {
            "org_id": "org-1",
            "tenant_id": "tenant-1",
            "agent_id": "a-1",
            "agent_name": "Agent 1",
            "agent_division": "engineering",
            "agent_color": "blue",
            "event_type": "task.completed",
            "title": "Task done",
            "timestamp": 104.0,
        },
    ]

    collector = MagicMock()
    timeline.set_timeline_deps(collector=collector, db=db)

    replay = await timeline.get_replay(org_id="org-1", tenant=tenant, speed=2.0)

    db.get_timeline_events.assert_called_once_with(
        org_id="org-1",
        tenant_id="tenant-1",
    )
    collector.get_replay.assert_not_called()
    assert replay["org_id"] == "org-1"
    assert replay["duration_seconds"] == 4.0
    assert replay["replay_duration_seconds"] == 2.0
    assert replay["events"][1]["relative_time"] == 4.0
    assert replay["events"][1]["replay_time"] == 2.0
    assert replay["agents"] == [
        {
            "agent_id": "a-1",
            "name": "Agent 1",
            "division": "engineering",
            "color": "blue",
        }
    ]
