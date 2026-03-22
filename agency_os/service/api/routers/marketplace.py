"""FastAPI router for the SWARM marketplace — agent-to-agent service commerce.

Exposes endpoints for:
- Service discovery (agents find SWARM services by capability/category)
- Service requests (agents purchase and invoke SWARM services)
- ACP marketplace registration and management
- Escrow status and settlement
- Marketplace analytics

Security:
- All mutating endpoints require tenant authentication (C1)
- POST /request requires active billing (C1)
- Escrow lookup restricted to transaction participants (H3)
- Input params sanitized before handler dispatch (C2)
- Error messages sanitized to prevent internal leakage (M5)
- Audit logging on all financial operations (L3)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Security
from pydantic import BaseModel, Field, field_validator

from agency_os.marketplace.acp import ACPClient
from agency_os.marketplace.catalog import ServiceCatalog, ServiceCategory
from agency_os.marketplace.router import ACPRequestRouter, ServiceRequest
from agency_os.service.api.middleware.auth import (
    get_current_tenant,
    require_active_billing,
)
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])

# Module-level singletons — wired in app.py
_catalog: ServiceCatalog | None = None
_acp_client: ACPClient | None = None
_request_router: ACPRequestRouter | None = None
_db: Database | None = None


def set_catalog(catalog: ServiceCatalog) -> None:
    global _catalog
    _catalog = catalog


def set_acp_client(client: ACPClient) -> None:
    global _acp_client
    _acp_client = client


def set_request_router(rr: ACPRequestRouter) -> None:
    global _request_router
    _request_router = rr


def set_database(db: Database) -> None:
    global _db
    _db = db


def _require_catalog() -> ServiceCatalog:
    if _catalog is None:
        raise HTTPException(503, "Marketplace not initialized")
    return _catalog


def _require_acp() -> ACPClient:
    if _acp_client is None:
        raise HTTPException(503, "ACP client not initialized")
    return _acp_client


def _require_router() -> ACPRequestRouter:
    if _request_router is None:
        raise HTTPException(503, "Request router not initialized")
    return _request_router


def _audit(
    tenant_id: str, action: str, resource: str, resource_id: str, detail: str
) -> None:
    """Record an audit event for marketplace operations (L3)."""
    if _db is not None:
        try:
            _db.save_audit_event(
                actor=f"tenant:{tenant_id}",
                action=action,
                resource=resource,
                resource_id=resource_id,
                detail=detail,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning("Failed to write audit event: %s", e)


def _sanitize_error(error: str | None) -> str | None:
    """Strip internal details from error messages before returning to callers (M5)."""
    if error is None:
        return None
    # Remove Python tracebacks, internal module paths, and exception class names
    sanitized = error
    for prefix in ("Traceback ", "File ", "  ", "swarm.", "agency_os."):
        if sanitized.startswith(prefix):
            return "Service execution failed"
    if "Error" in sanitized and ":" in sanitized:
        # e.g. "RuntimeError: something" → "something"
        parts = sanitized.split(":", 1)
        if parts[0].endswith("Error") or parts[0].endswith("Exception"):
            sanitized = parts[1].strip()
    # Truncate overly long messages
    if len(sanitized) > 256:
        sanitized = sanitized[:253] + "..."
    return sanitized


# -- Request / Response models --


class ServiceRequestBody(BaseModel):
    client_agent_id: str = Field(
        ..., description="ID of the requesting agent", min_length=1, max_length=128
    )
    service_id: str = Field(
        ..., description="SWARM service to invoke", min_length=1, max_length=64
    )
    input_params: dict[str, Any] = Field(default_factory=dict)
    max_price_usd: Optional[float] = Field(
        None, description="Maximum price the client is willing to pay", ge=0, le=10000
    )

    @field_validator("input_params")
    @classmethod
    def validate_input_params_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Reject oversized input payloads (C2)."""
        import json

        serialized = json.dumps(v, default=str)
        if len(serialized) > 65536:  # 64KB limit
            raise ValueError("input_params exceeds maximum size of 64KB")
        return v


class ACPRegisterBody(BaseModel):
    agent_id: str = Field(
        ..., description="Worker agent ID", min_length=1, max_length=128
    )
    service_ids: list[str] = Field(
        ..., description="Service IDs this agent provides", min_length=1, max_length=20
    )


# -- Endpoints --


@router.get("/services")
async def list_services(
    category: Optional[str] = None,
    capability: Optional[str] = None,
    tag: Optional[str] = None,
    max_price_usd: Optional[float] = None,
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """Discover SWARM services available for purchase.

    Requires authentication. Autonomous agents call this endpoint to find
    services they can hire.
    """
    catalog = _require_catalog()
    # L2: Handle invalid category gracefully instead of unhandled ValueError
    cat_enum = None
    if category:
        try:
            cat_enum = ServiceCategory(category)
        except ValueError:
            raise HTTPException(400, f"Invalid category: {category}") from None
    services = catalog.list_services(
        category=cat_enum,
        capability=capability,
        tag=tag,
    )
    if max_price_usd is not None:
        services = [s for s in services if s.pricing.base_price_usd <= max_price_usd]
    return {
        "services": [
            {
                "service_id": s.service_id,
                "name": s.name,
                "description": s.description,
                "category": s.category.value,
                "capabilities": s.capabilities,
                "pricing": {
                    "model": s.pricing.model.value,
                    "base_usd": s.pricing.base_price_usd,
                    "per_unit_usd": s.pricing.per_unit_usd,
                    "unit": s.pricing.unit_name,
                    "currency": s.pricing.currency,
                },
                "sla": {
                    "max_latency_seconds": s.sla.max_latency_seconds,
                },
                "tags": s.tags,
                "version": s.version,
            }
            for s in services
        ],
        "total": len(services),
    }


@router.get("/services/{service_id}")
async def get_service(
    service_id: str,
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """Get detailed info about a specific SWARM service."""
    catalog = _require_catalog()
    service = catalog.get(service_id)
    if service is None:
        raise HTTPException(404, "Service not found")
    stats = catalog.get_stats(service_id)
    return {
        "service_id": service.service_id,
        "name": service.name,
        "description": service.description,
        "category": service.category.value,
        "capabilities": service.capabilities,
        "pricing": {
            "model": service.pricing.model.value,
            "base_usd": service.pricing.base_price_usd,
            "per_unit_usd": service.pricing.per_unit_usd,
            "unit": service.pricing.unit_name,
            "currency": service.pricing.currency,
        },
        "sla": {
            "max_latency_seconds": service.sla.max_latency_seconds,
            "availability": service.sla.availability_target,
            "max_concurrent": service.sla.max_concurrent_requests,
        },
        "input_schema": service.input_schema,
        "output_schema": service.output_schema,
        "tags": service.tags,
        "version": service.version,
        "enabled": service.enabled,
        "stats": stats,
    }


@router.post("/request")
async def request_service(
    body: ServiceRequestBody,
    tenant: Tenant = Security(require_active_billing),
) -> dict[str, Any]:
    """Submit a service request — an agent purchasing a SWARM service.

    Requires active billing (C1). The request flows through:
    1. Input validation and sanitization
    2. Price validation
    3. Worker agent selection
    4. ACP escrow creation
    5. SWARM module execution (with timeout)
    6. Auto-evaluation
    7. Payment settlement

    Returns the service result, cost, and optional safety certification.
    """
    rr = _require_router()

    request = ServiceRequest(
        request_id=f"req-{uuid.uuid4().hex[:12]}",
        client_agent_id=body.client_agent_id,
        service_id=body.service_id,
        input_params=body.input_params,
        max_price_usd=body.max_price_usd,
    )

    # L3: Audit the service request
    _audit(
        tenant_id=tenant.tenant_id,
        action="marketplace.request",
        resource="service",
        resource_id=body.service_id,
        detail=f"client={body.client_agent_id}",
    )

    response = rr.handle_request(request)

    if response.status == "rejected":
        raise HTTPException(400, _sanitize_error(response.error) or "Request rejected")

    result: dict[str, Any] = {
        "request_id": response.request_id,
        "service_id": response.service_id,
        "status": response.status,
        "result": response.result,
        "cost_usd": response.cost_usd,
        "escrow_id": response.escrow_id,
        "latency_seconds": round(response.latency_seconds, 2),
    }
    if response.certification:
        result["certification"] = response.certification
    if response.error:
        result["error"] = _sanitize_error(response.error)
    return result


@router.get("/discover")
async def discover_acp(
    capability: Optional[str] = None,
    category: Optional[str] = None,
    max_price_usd: Optional[float] = None,
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """ACP-compatible discovery endpoint.

    Returns service manifests in ACP format for autonomous agent consumption.
    """
    acp = _require_acp()
    results = acp.discover(
        capability=capability,
        category=category,
        max_price_usd=max_price_usd,
    )
    return {"agents": results, "total": len(results)}


@router.post("/register")
async def register_provider(
    body: ACPRegisterBody,
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """Register a SWARM worker agent as an ACP service provider.

    Requires authentication (C1).
    """
    catalog = _require_catalog()
    acp = _require_acp()

    manifests = []
    for sid in body.service_ids:
        service = catalog.get(sid)
        if service is None:
            raise HTTPException(404, "Service not found")
        manifest = service.to_acp_manifest()
        manifests.append(manifest)

    combined_manifest: dict[str, Any] = {
        "agent_id": body.agent_id,
        "capabilities": [],
        "services": [],
    }
    for m in manifests:
        combined_manifest["capabilities"].extend(m.get("capabilities", []))
        combined_manifest["services"].append(m)

    reg = acp.register_service(body.agent_id, combined_manifest)

    # L3: Audit provider registration
    _audit(
        tenant_id=tenant.tenant_id,
        action="marketplace.register",
        resource="provider",
        resource_id=body.agent_id,
        detail=f"services={body.service_ids}",
    )

    return {
        "agent_id": reg.agent_id,
        "registered_at": reg.registered_at,
        "active": reg.active,
        "services": body.service_ids,
    }


@router.get("/escrow/{escrow_id}")
async def get_escrow(
    escrow_id: str,
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """Check escrow status for a service transaction.

    Only the client or provider agent's tenant can view escrow details (H3).
    """
    acp = _require_acp()
    escrow = acp.get_escrow(escrow_id)
    if escrow is None:
        raise HTTPException(404, "Escrow not found")

    # H3: Authorization — only participants can view escrow details.
    # The tenant_id is embedded in the client_agent_id prefix by convention,
    # but we also check provider side. For system-level access, tenant metadata
    # can include "marketplace_admin": true.
    is_admin = tenant.metadata.get("marketplace_admin") is True
    tenant_prefix = tenant.tenant_id
    is_participant = escrow.client_agent_id.startswith(
        tenant_prefix
    ) or escrow.provider_agent_id.startswith(tenant_prefix)
    if not is_participant and not is_admin:
        raise HTTPException(403, "Not authorized to view this escrow")

    return {
        "escrow_id": escrow.escrow_id,
        "client_agent_id": escrow.client_agent_id,
        "provider_agent_id": escrow.provider_agent_id,
        "service_id": escrow.service_id,
        "amount_usd": escrow.amount_usd,
        "state": escrow.state.value,
        "evaluation_score": escrow.evaluation_score,
        "tx_hash": escrow.tx_hash,
        "created_at": escrow.created_at,
        "settled_at": escrow.settled_at,
    }


@router.get("/stats")
async def marketplace_stats(
    tenant: Tenant = Security(get_current_tenant),
) -> dict[str, Any]:
    """Get marketplace-wide statistics. Requires authentication."""
    catalog = _require_catalog()
    acp = _require_acp()
    rr = _require_router()

    return {
        "catalog": {
            "total_services": len(catalog.list_services(enabled_only=False)),
            "enabled_services": len(catalog.list_services()),
        },
        "acp": acp.platform_stats(),
        "requests": rr.request_log_summary(),
    }
