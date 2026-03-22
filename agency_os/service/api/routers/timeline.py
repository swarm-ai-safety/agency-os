"""Timeline and Replay API router — the time-lapse company feature.

Provides endpoints to retrieve the visual timeline of agent activity
within an organization and build replay manifests for the "watch AI
agents build something in real time" experience.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agency_os.service.api.middleware.auth import require_active_billing
from agency_os.service.api.routers.organizations import verify_org_ownership
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant
from agency_os.timeline.collector import TimelineCollector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orgs/{org_id}/timeline", tags=["timeline"])

_timeline_collector: TimelineCollector | None = None
_timeline_db: Database | None = None


def set_timeline_deps(collector: TimelineCollector, db: Database | None) -> None:
    global _timeline_collector, _timeline_db
    _timeline_collector = collector
    _timeline_db = db


def _get_collector() -> TimelineCollector:
    if _timeline_collector is None:
        raise HTTPException(
            status_code=503, detail="Timeline collector not initialized"
        )
    return _timeline_collector


def _build_replay_manifest(
    *,
    org_id: str,
    events: list[dict[str, Any]],
    speed: float,
) -> dict[str, Any]:
    if not events:
        return {
            "org_id": org_id,
            "events": [],
            "agents": [],
            "duration_seconds": 0,
            "speed": speed,
        }

    start_ts = float(events[0]["timestamp"])
    end_ts = float(events[-1]["timestamp"])

    agents: dict[str, dict[str, Any]] = {}
    frames: list[dict[str, Any]] = []
    for raw_event in events:
        event = dict(raw_event)
        agent_id = event.get("agent_id")
        if agent_id and agent_id not in agents:
            agents[agent_id] = {
                "agent_id": agent_id,
                "name": event.get("agent_name"),
                "division": event.get("agent_division"),
                "color": event.get("agent_color"),
            }

        event_ts = float(event["timestamp"])
        event["relative_time"] = event_ts - start_ts
        event["replay_time"] = (event_ts - start_ts) / speed
        frames.append(event)

    return {
        "org_id": org_id,
        "events": frames,
        "agents": list(agents.values()),
        "duration_seconds": end_ts - start_ts,
        "replay_duration_seconds": (end_ts - start_ts) / speed,
        "speed": speed,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
    }


@router.get("")
async def get_timeline(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
    since: float | None = Query(None, description="Unix timestamp lower bound"),
    until: float | None = Query(None, description="Unix timestamp upper bound"),
    event_type: list[str] | None = Query(None, description="Filter by event types"),
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """Get the timeline of events for an organization.

    Returns a chronological list of agent activities, task assignments,
    bids, governance triggers, and artifacts — everything needed to
    render the time-lapse view.
    """
    # Prefer database for persisted events, fall back to in-memory
    db = _timeline_db
    if db is not None:
        events = db.get_timeline_events(
            org_id=org_id,
            tenant_id=tenant.tenant_id,
            since=since,
            until=until,
            event_types=event_type,
            agent_id=agent_id,
            limit=limit,
        )
    else:
        collector = _get_collector()
        events = collector.get_events(
            org_id=org_id,
            tenant_id=tenant.tenant_id,
            since=since,
            until=until,
            event_types=event_type,
            agent_id=agent_id,
            limit=limit,
        )

    return {
        "org_id": org_id,
        "count": len(events),
        "events": events,
    }


@router.get("/replay")
async def get_replay(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
    speed: float = Query(1.0, ge=0.1, le=10.0, description="Playback speed multiplier"),
) -> dict[str, Any]:
    """Get a replay manifest for the organization run.

    Returns all events with relative timestamps for movie-like playback,
    along with agent metadata and duration information. Clients use the
    ``replay_time`` field on each event to schedule rendering.
    """
    db = _timeline_db
    if db is not None:
        events = db.get_timeline_events(
            org_id=org_id,
            tenant_id=tenant.tenant_id,
        )
        return _build_replay_manifest(org_id=org_id, events=events, speed=speed)

    collector = _get_collector()
    return collector.get_replay(org_id=org_id, tenant_id=tenant.tenant_id, speed=speed)


@router.get("/summary")
async def get_summary(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Get summary statistics for an organization's timeline.

    Returns total events, unique agents, event type breakdown,
    and duration — useful for dashboard cards and overview screens.
    """
    collector = _get_collector()
    return collector.get_summary(org_id=org_id, tenant_id=tenant.tenant_id)
