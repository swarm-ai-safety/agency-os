"""Agent status, wallets, reputation, and effectiveness API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agency_os.governance.trust import compute_trust_score
from agency_os.metering.collector import MeteringCollector
from agency_os.service.api.middleware.auth import get_current_tenant
from agency_os.service.api.routers.organizations import _get_org, verify_org_ownership
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant

router = APIRouter(prefix="/api/v1/orgs/{org_id}/agents", tags=["agents"])

_metering: MeteringCollector | None = None
_db: Database | None = None


def set_agent_deps(collector: MeteringCollector, db: Database | None) -> None:
    global _metering, _db
    _metering = collector
    _db = db


@router.get("")
async def list_agents(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List all agents with wallets and reputation."""
    org = _get_org(tenant.tenant_id, org_id)
    agents = []
    for a in org.agents:
        info = a.status_dict()
        if _metering is not None:
            trust = compute_trust_score(_metering, a.agent_id, tenant.tenant_id)
            info["trust_score"] = trust.score
            info["trust_tier"] = trust.tier
        agents.append(info)
    return agents


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get a specific agent's status with trust data."""
    org = _get_org(tenant.tenant_id, org_id)
    agent = org.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    info = agent.status_dict()
    if _metering is not None:
        trust = compute_trust_score(_metering, agent_id, tenant.tenant_id)
        info["trust_score"] = trust.score
        info["trust_tier"] = trust.tier
        info["effectiveness_trend"] = _compute_trend(agent_id, tenant.tenant_id)
    return info


@router.get("/{agent_id}/effectiveness")
async def get_agent_effectiveness(
    agent_id: str,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get agent effectiveness data: trust history, success rates, percentiles."""
    org = _get_org(tenant.tenant_id, org_id)
    agent = org.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    result: dict[str, Any] = {"agent_id": agent_id}

    # Trust score history from DB
    db = _db
    if db is not None:
        history = db.get_trust_score_history(agent_id, limit=100)
        result["trust_history"] = [
            {
                "score": h["score"],
                "tier": h["tier"],
                "total_tasks": h["total_tasks"],
                "successes": h["successes"],
                "failures": h["failures"],
                "partials": h["partials"],
                "computed_at": h["computed_at"],
            }
            for h in history
        ]
    else:
        result["trust_history"] = []

    # Current trust score
    if _metering is not None:
        trust = compute_trust_score(_metering, agent_id, tenant.tenant_id)
        result["current_trust"] = {
            "score": trust.score,
            "tier": trust.tier,
            "total_tasks": trust.total_tasks,
            "successes": trust.successes,
            "failures": trust.failures,
            "partials": trust.partials,
        }
        # Percentiles (p5/p50/p95 on duration)
        result["duration_percentiles"] = _metering.get_agent_percentiles(
            agent_id, tenant.tenant_id
        )

        # Success rate by task type from outcomes
        outcomes = _metering.get_agent_outcomes(agent_id, tenant.tenant_id)
        total = len(outcomes)
        successes = sum(1 for e in outcomes if e.metadata.get("outcome") == "success")
        result["success_rate"] = {
            "total_tasks": total,
            "successes": successes,
            "rate": successes / total if total > 0 else 0.0,
        }
    else:
        result["current_trust"] = None
        result["duration_percentiles"] = {}
        result["success_rate"] = {"total_tasks": 0, "successes": 0, "rate": 0.0}

    result["effectiveness_trend"] = _compute_trend(agent_id, tenant.tenant_id)

    return result


@router.get("/{agent_id}/history")
async def get_agent_history(
    agent_id: str,
    org_id: str = Depends(verify_org_ownership),
    limit: int = Query(50, ge=1, le=100),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get recent task outcomes and wallet history for an agent."""
    org = _get_org(tenant.tenant_id, org_id)
    agent = org.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    result: dict[str, Any] = {"agent_id": agent_id}

    # Recent task outcomes from metering
    if _metering is not None:
        outcomes = _metering.get_agent_outcomes(agent_id, tenant.tenant_id, limit=limit)
        result["task_outcomes"] = [
            {
                "outcome": e.metadata.get("outcome"),
                "task_id": e.metadata.get("task_id", ""),
                "duration_sec": e.metadata.get("duration_sec"),
                "timestamp": e.timestamp,
            }
            for e in outcomes
        ]
    else:
        result["task_outcomes"] = []

    # Wallet snapshots from DB
    db = _db
    if db is not None:
        result["wallet_snapshots"] = db.get_agent_wallet_snapshots(
            agent_id, limit=limit
        )
    else:
        result["wallet_snapshots"] = []

    return result


def _compute_trend(agent_id: str, tenant_id: str) -> str:
    """Compute effectiveness trend: improving, stable, or declining."""
    if _metering is None:
        return "stable"
    outcomes = _metering.get_agent_outcomes(agent_id, tenant_id, limit=20)
    if len(outcomes) < 6:
        return "stable"
    # Compare first half vs second half success rates
    mid = len(outcomes) // 2
    # outcomes are most-recent-first, so recent = outcomes[:mid], older = outcomes[mid:]
    recent = outcomes[:mid]
    older = outcomes[mid:]
    recent_rate = sum(
        1 for e in recent if e.metadata.get("outcome") == "success"
    ) / len(recent)
    older_rate = sum(1 for e in older if e.metadata.get("outcome") == "success") / len(
        older
    )
    diff = recent_rate - older_rate
    if diff > 0.1:
        return "improving"
    if diff < -0.1:
        return "declining"
    return "stable"
