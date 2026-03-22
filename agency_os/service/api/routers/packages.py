"""Package browsing API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from agency_os.packages.loader import (
    list_builtin_packages,
    load_package_from_name,
)
from agency_os.service.api.middleware.auth import get_current_tenant
from agency_os.tenancy.tenant import Tenant

router = APIRouter(prefix="/api/v1/packages", tags=["packages"])


@router.get("")
async def list_packages(
    tenant: Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List all available built-in packages."""
    result = []
    for name in list_builtin_packages():
        try:
            spec = load_package_from_name(name)
            result.append(
                {
                    "package_name": name,
                    "name": spec.metadata.name,
                    "display_name": spec.metadata.display_name,
                    "tier": spec.metadata.tier.value,
                    "agent_count": len(spec.agents),
                    "icon": spec.metadata.icon,
                    "tagline": spec.metadata.tagline,
                    "use_cases": spec.metadata.use_cases,
                    "category": spec.metadata.category,
                }
            )
        except Exception:
            result.append({"name": name, "error": "failed to load"})
    return result


@router.get("/{name}")
async def get_package(
    name: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get details of a specific package."""
    try:
        spec = load_package_from_name(name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Package not found: {name}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "package_name": name,
        "name": spec.metadata.name,
        "display_name": spec.metadata.display_name,
        "tier": spec.metadata.tier.value,
        "agents": [
            {
                "ref": a.ref,
                "count": a.count,
                "bid_strategy": a.economic.bid_strategy.value,
            }
            for a in spec.agents
        ],
        "governance": {"preset": spec.governance.preset},
        "workflows": [{"name": w.name, "pipeline": w.pipeline} for w in spec.workflows],
        "deployment": {
            "llm_provider": spec.deployment.llm_provider,
            "model": spec.deployment.model,
            "budget_limit_usd": spec.deployment.budget_limit_usd,
        },
    }
