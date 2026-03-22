"""Organization API router — launch/stop orgs."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agency_os.orchestration.organization import Organization
from agency_os.packages.loader import load_package_from_name  # used by SSE stream
from agency_os.service.api.middleware.auth import (
    get_current_tenant,
    require_action_approval,
    require_active_billing,
)
from agency_os.tenancy.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])

# In-memory org store (injected by app)
_org_store: dict[str, dict[str, Organization]] = {}  # tenant_id -> {org_id -> org}
_db: Any | None = None
_timeline_collector: Any | None = None


def set_org_store(store: dict) -> None:
    global _org_store
    _org_store = store


def set_database(db: Any) -> None:
    global _db
    _db = db


def set_timeline_collector(collector: Any) -> None:
    global _timeline_collector
    _timeline_collector = collector


def rehydrate_orgs_from_db() -> int:
    """Rebuild _org_store from persisted organizations on startup.

    Returns the number of orgs successfully rehydrated.
    """
    if _db is None:
        return 0

    from agency_os.orchestration.organization import Organization

    count = 0

    for tenant_row in _db.list_tenants():
        tenant_id = tenant_row["tenant_id"]
        for org_row in _db.list_orgs(tenant_id):
            if org_row.get("status") != "running":
                continue
            org_id = org_row["org_id"]
            package_name = org_row["package_name"]
            try:
                org = Organization.from_builtin(package_name, org_id=org_id)
                org.start()
                if tenant_id not in _org_store:
                    _org_store[tenant_id] = {}
                _org_store[tenant_id][org_id] = org
                count += 1
            except Exception:
                logger.warning(
                    "Failed to rehydrate org %s (package=%s) for tenant %s",
                    org_id,
                    package_name,
                    tenant_id,
                    exc_info=True,
                )
    logger.info("Rehydrated %d organizations from database", count)
    return count


def verify_org_ownership(
    org_id: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> str:
    """Verify that the org_id belongs to the authenticated tenant.

    Returns the org_id if valid, raises 403 Forbidden for both non-existent orgs
    and orgs owned by other tenants (prevents org ID enumeration).
    """
    if _db is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    org = _db.get_org(org_id, tenant_id=tenant.tenant_id)

    # Return 403 for both non-existent and cross-tenant orgs
    # This prevents org ID enumeration attacks
    if org is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    return org_id


def _persist_org(
    org: Organization,
    tenant: Tenant,
    package_name: str,
) -> None:
    """Store org in memory and database, emit timeline events."""
    if tenant.tenant_id not in _org_store:
        _org_store[tenant.tenant_id] = {}
    _org_store[tenant.tenant_id][org.org_id] = org

    if _db is not None:
        _db.save_org(
            {
                "org_id": org.org_id,
                "tenant_id": tenant.tenant_id,
                "package_name": package_name,
                "status": org.status.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="org.created",
            resource="organization",
            resource_id=org.org_id,
            detail=json.dumps({"package_name": package_name}),
            tenant_id=tenant.tenant_id,
        )

    if _timeline_collector is not None:
        _timeline_collector.org_started(
            org_id=org.org_id,
            tenant_id=tenant.tenant_id,
            package_name=package_name,
            agent_count=len(org.agents),
        )
        for agent in org.agents:
            _timeline_collector.agent_joined(
                org_id=org.org_id,
                tenant_id=tenant.tenant_id,
                agent=agent,
            )


class CreateOrgRequest(BaseModel):
    package_name: str


class OrgResponse(BaseModel):
    org_id: str
    status: str
    package: str
    agent_count: int


@router.post("", response_model=OrgResponse)
async def create_org(
    req: CreateOrgRequest,
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Launch an organization from a built-in package."""
    try:
        org = Organization.from_builtin(req.package_name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Package not found: {req.package_name}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    org.start()
    _persist_org(org, tenant, req.package_name)

    return {
        "org_id": org.org_id,
        "status": org.status.value,
        "package": org.package.metadata.name,
        "agent_count": len(org.agents),
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream", response_class=StreamingResponse)
async def create_org_stream(
    req: CreateOrgRequest,
    tenant: Tenant = Depends(require_active_billing),
) -> StreamingResponse:
    """Launch an organization with real-time SSE progress streaming."""

    async def _stream() -> AsyncGenerator[str, None]:
        # Phase 1: Load package
        yield _sse_event(
            "log",
            {"phase": "package", "message": f"Loading package '{req.package_name}'..."},
        )

        try:
            package = load_package_from_name(req.package_name)
        except FileNotFoundError:
            yield _sse_event(
                "error", {"message": f"Package not found: {req.package_name}"}
            )
            return
        except ValueError as exc:
            yield _sse_event("error", {"message": str(exc)})
            return

        yield _sse_event(
            "log",
            {
                "phase": "package",
                "message": f"Loaded '{package.metadata.display_name}' — {len(package.agents)} agent specs, governance: {package.governance.preset}",
            },
        )

        # Phase 2: Create organization
        yield _sse_event(
            "log", {"phase": "organization", "message": "Creating organization..."}
        )
        org = Organization(package=package)

        # Phase 3: Start agents
        yield _sse_event(
            "log",
            {
                "phase": "agents",
                "message": f"Initializing {len(package.agents)} agents...",
            },
        )

        try:
            org.start()
        except Exception:
            logger.exception(
                "Failed to start organization for tenant %s", tenant.tenant_id
            )
            yield _sse_event(
                "error", {"message": "Failed to start organization. Please try again."}
            )
            return

        for agent in org.agents:
            yield _sse_event(
                "log",
                {
                    "phase": "agents",
                    "message": f"Agent ready: {agent.name} (wallet: ${agent.balance:.0f})",
                    "agent_id": agent.agent_id,
                    "agent_name": agent.name,
                },
            )

        # Phase 4: Governance
        yield _sse_event(
            "log",
            {
                "phase": "governance",
                "message": f"Governance profile '{package.governance.preset}' applied",
            },
        )

        # Phase 5: Persist
        yield _sse_event(
            "log", {"phase": "persist", "message": "Persisting organization..."}
        )
        _persist_org(org, tenant, req.package_name)

        # Final result event
        yield _sse_event(
            "result",
            {
                "org_id": org.org_id,
                "status": org.status.value,
                "package": org.package.metadata.name,
                "agent_count": len(org.agents),
                "agents": [
                    {"agent_id": a.agent_id, "name": a.name} for a in org.agents
                ],
            },
        )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("")
async def list_orgs(
    tenant: Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List all organizations for the current tenant."""
    tenant_orgs = _org_store.get(tenant.tenant_id, {})
    return [org.status_dict() for org in tenant_orgs.values()]


@router.get("/{org_id}")
async def get_org(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get organization status."""
    org = _get_org(tenant.tenant_id, org_id)
    return org.status_dict()


@router.delete("/{org_id}")
async def delete_org(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_action_approval("org.delete")),
) -> dict[str, str]:
    """Shutdown an organization."""
    org = _get_org(tenant.tenant_id, org_id)
    org.stop()
    del _org_store[tenant.tenant_id][org_id]

    # Update status in database (scoped to tenant)
    if _db is not None:
        _db.update_org_status(org_id, "stopped", tenant_id=tenant.tenant_id)
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="org.deleted",
            resource="organization",
            resource_id=org_id,
            detail=json.dumps({"status": "stopped"}),
            tenant_id=tenant.tenant_id,
        )

    # Emit timeline stop event
    if _timeline_collector is not None:
        _timeline_collector.org_stopped(
            org_id=org_id,
            tenant_id=tenant.tenant_id,
        )

    return {"status": "stopped", "org_id": org_id}


def _get_org(tenant_id: str, org_id: str) -> Organization:
    org = _org_store.get(tenant_id, {}).get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return org
