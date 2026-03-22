"""Metering query endpoints for operational visibility."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agency_os.service.api.middleware.auth import get_current_tenant
from agency_os.service.api.routers.organizations import verify_org_ownership
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant

router = APIRouter(tags=["metering"])

_db: Database | None = None


def set_database(db: Database | None) -> None:
    global _db
    _db = db


def _require_db() -> Database:
    if _db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return _db


def _query_metering(
    *,
    tenant: Tenant,
    start_time: float | None,
    end_time: float | None,
    agent_id: str | None,
    org_id: str | None,
    task_id: str | None,
    event_type: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    db = _require_db()
    events, total = db.query_metering_events(
        tenant_id=tenant.tenant_id,
        start_time=start_time,
        end_time=end_time,
        agent_id=agent_id,
        org_id=org_id,
        task_id=task_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return {"items": events, "total": total, "limit": limit, "offset": offset}


@router.get("/api/v1/orgs/{org_id}/metering")
async def get_org_metering(
    org_id: str = Depends(verify_org_ownership),
    start_time: float | None = Query(default=None, alias="startTime"),
    end_time: float | None = Query(default=None, alias="endTime"),
    agent_id: str | None = Query(default=None, alias="agentId"),
    task_id: str | None = Query(default=None, alias="taskId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Query metering events scoped to an organization owned by the tenant."""
    return _query_metering(
        tenant=tenant,
        start_time=start_time,
        end_time=end_time,
        agent_id=agent_id,
        org_id=org_id,
        task_id=task_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/api/v1/orgs/{org_id}/agents/{agent_id}/metering")
async def get_agent_metering(
    agent_id: str,
    org_id: str = Depends(verify_org_ownership),
    start_time: float | None = Query(default=None, alias="startTime"),
    end_time: float | None = Query(default=None, alias="endTime"),
    task_id: str | None = Query(default=None, alias="taskId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Query metering events scoped to a single agent within a verified org."""
    return _query_metering(
        tenant=tenant,
        start_time=start_time,
        end_time=end_time,
        agent_id=agent_id,
        org_id=org_id,
        task_id=task_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/api/v1/tasks/{task_id}/metering")
async def get_task_metering(
    task_id: str,
    start_time: float | None = Query(default=None, alias="startTime"),
    end_time: float | None = Query(default=None, alias="endTime"),
    agent_id: str | None = Query(default=None, alias="agentId"),
    org_id: str | None = Query(default=None, alias="orgId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Query metering events attributed to a task for the current tenant."""
    db = _require_db()
    task = db.get_task(task_id, tenant_id=tenant.tenant_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _query_metering(
        tenant=tenant,
        start_time=start_time,
        end_time=end_time,
        agent_id=agent_id,
        org_id=org_id,
        task_id=task_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
