"""Live governance controls API router."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from agency_os.packages.schema import CircuitBreakerConfig
from agency_os.service.api.middleware.auth import get_current_tenant
from agency_os.service.api.routers.organizations import _get_org, verify_org_ownership
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant

router = APIRouter(prefix="/api/v1/orgs/{org_id}/governance", tags=["governance"])

_VALID_PRESETS = frozenset({"conservative", "balanced", "aggressive"})
_VALID_ROLLOUT_STRATEGIES = frozenset({"immediate", "canary"})
_POLICY_ACTION_VERSIONED = "governance.policy.versioned"
_POLICY_ACTION_PROMOTED = "governance.policy.promoted"
_POLICY_ACTION_ROLLED_BACK = "governance.policy.rolled_back"
_POLICY_ACTIONS = frozenset(
    {
        _POLICY_ACTION_VERSIONED,
        _POLICY_ACTION_PROMOTED,
        _POLICY_ACTION_ROLLED_BACK,
    }
)
_db: Database | None = None


def set_database(db: Database | None) -> None:
    global _db
    _db = db


class GovernanceOverridesUpdate(BaseModel):
    audit_frequency: Optional[float] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    tax_rate: Optional[float] = None

    @field_validator("audit_frequency")
    @classmethod
    def check_audit_frequency(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("audit_frequency must be between 0.0 and 1.0")
        return v

    @field_validator("tax_rate")
    @classmethod
    def check_tax_rate(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 0.5):
            raise ValueError("tax_rate must be between 0.0 and 0.5")
        return v


class GovernanceUpdate(BaseModel):
    preset: str | None = None
    overrides: GovernanceOverridesUpdate = GovernanceOverridesUpdate()
    rollout_strategy: str = "immediate"
    canary_percent: int | None = None

    @field_validator("preset")
    @classmethod
    def check_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_PRESETS:
            raise ValueError(
                f"Invalid preset: {v!r}. Must be one of {sorted(_VALID_PRESETS)}"
            )
        return v

    @field_validator("rollout_strategy")
    @classmethod
    def check_rollout_strategy(cls, v: str) -> str:
        if v not in _VALID_ROLLOUT_STRATEGIES:
            raise ValueError(
                f"Invalid rollout_strategy: {v!r}. Must be one of {sorted(_VALID_ROLLOUT_STRATEGIES)}"
            )
        return v

    @field_validator("canary_percent")
    @classmethod
    def check_canary_percent(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 100):
            raise ValueError("canary_percent must be between 1 and 100")
        return v


class GovernanceRollbackRequest(BaseModel):
    target_version: int | None = None


def _policy_resource_id(org_id: str, version: int) -> str:
    return f"{org_id}:v{version}"


def _load_policy_history(tenant_id: str, org_id: str) -> list[dict[str, Any]]:
    if _db is None:
        return []
    logs = _db.get_audit_log(tenant_id=tenant_id, limit=1000)
    history: list[dict[str, Any]] = []
    for log in reversed(logs):
        if log.get("action") not in _POLICY_ACTIONS:
            continue
        detail_raw = log.get("detail")
        if not detail_raw:
            continue
        try:
            detail = json.loads(detail_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if detail.get("org_id") != org_id:
            continue
        history.append(detail)
    return history


def _latest_policy_detail(tenant_id: str, org_id: str) -> dict[str, Any] | None:
    history = _load_policy_history(tenant_id=tenant_id, org_id=org_id)
    return history[-1] if history else None


def _record_policy_event(
    *,
    tenant_id: str,
    org_id: str,
    version: int,
    action: str,
    detail: dict[str, Any],
) -> None:
    if _db is None:
        return
    _db.save_audit_event(
        actor=f"tenant:{tenant_id}",
        action=action,
        resource="governance_policy",
        resource_id=_policy_resource_id(org_id, version),
        detail=json.dumps(detail),
        tenant_id=tenant_id,
    )


def _log_matches_org(log: dict[str, Any], org_id: str) -> bool:
    resource_id = log.get("resource_id")
    if resource_id == org_id:
        return True
    if isinstance(resource_id, str) and resource_id.startswith(f"{org_id}:"):
        return True

    detail_raw = log.get("detail")
    if not detail_raw:
        return False
    try:
        detail = json.loads(detail_raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(detail, dict):
        return False
    return detail.get("org_id") == org_id


def _summarize_detail(detail: Any) -> str | None:
    if isinstance(detail, dict):
        for key in ("reason", "message", "status"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ", ".join(str(k) for k in detail.keys())[:120] or None
    if isinstance(detail, str):
        value = detail.strip()
        return value[:120] if value else None
    return None


@router.get("")
async def get_governance(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get current governance configuration."""
    org = _get_org(tenant.tenant_id, org_id)
    gov = org.package.governance
    latest_policy = _latest_policy_detail(tenant_id=tenant.tenant_id, org_id=org_id)
    response = {
        "preset": gov.preset,
        "overrides": gov.overrides.model_dump(exclude_none=True),
        "policy_version": latest_policy.get("version", 0) if latest_policy else 0,
        "rollout": latest_policy.get("rollout", {"status": "active"})
        if latest_policy
        else {"status": "active"},
    }
    if latest_policy:
        response["previous_policy_version"] = latest_policy.get("previous_version")
    return response


@router.get("/history")
async def get_governance_history(
    limit: int = Query(default=50, ge=1, le=200),
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get org-scoped audit timeline and circuit-breaker trip history."""
    _get_org(tenant.tenant_id, org_id)

    if _db is None:
        return {"audit_timeline": [], "circuit_breaker_history": [], "stats": {}}

    # Read a broader window so org-level filtering still yields enough rows.
    raw_audit_logs = _db.get_audit_log(
        tenant_id=tenant.tenant_id, limit=max(limit * 10, 500)
    )
    audit_timeline: list[dict[str, Any]] = []
    for log in raw_audit_logs:
        if not _log_matches_org(log, org_id):
            continue

        detail_raw = log.get("detail")
        parsed_detail: dict[str, Any] | str | None = None
        if detail_raw:
            try:
                parsed_detail = json.loads(detail_raw)
            except (json.JSONDecodeError, TypeError):
                parsed_detail = detail_raw

        audit_timeline.append(
            {
                "timestamp": log.get("timestamp"),
                "actor": log.get("actor"),
                "action": log.get("action"),
                "resource": log.get("resource"),
                "resource_id": log.get("resource_id"),
                "detail": parsed_detail,
                "summary": _summarize_detail(parsed_detail),
            }
        )

    audit_timeline.sort(
        key=lambda item: float(item.get("timestamp") or 0), reverse=True
    )
    audit_timeline = audit_timeline[:limit]

    metering_events = _db.get_metering_events(tenant.tenant_id)
    circuit_breaker_history: list[dict[str, Any]] = []
    for event in metering_events:
        if event.get("org_id") != org_id:
            continue
        if event.get("event_type") != "circuit_breaker.tripped":
            continue
        metadata = event.get("metadata")
        payload = metadata if isinstance(metadata, dict) else {}
        circuit_breaker_history.append(
            {
                "timestamp": event.get("timestamp"),
                "event_type": event.get("event_type"),
                "agent_id": payload.get("agent_id"),
                "task_id": payload.get("task_id"),
                "threshold": payload.get("threshold"),
                "consecutive_failures": payload.get("consecutive_failures"),
                "reason": payload.get("reason"),
                "duration_sec": payload.get("duration_sec"),
            }
        )

    circuit_breaker_history.sort(
        key=lambda item: float(item.get("timestamp") or 0), reverse=True
    )
    circuit_breaker_history = circuit_breaker_history[:limit]

    return {
        "audit_timeline": audit_timeline,
        "circuit_breaker_history": circuit_breaker_history,
        "stats": {
            "audit_events": len(audit_timeline),
            "circuit_breaker_trips": len(circuit_breaker_history),
        },
    }


@router.patch("")
async def update_governance(
    update: GovernanceUpdate,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Adjust governance levers on a running org."""
    org = _get_org(tenant.tenant_id, org_id)

    if update.preset:
        org.package.governance.preset = update.preset

    # Apply only explicitly-set override fields (no setattr from user input)
    overrides = update.overrides
    gov_overrides = org.package.governance.overrides
    if overrides.audit_frequency is not None:
        gov_overrides.audit_frequency = overrides.audit_frequency
    if overrides.circuit_breaker is not None:
        gov_overrides.circuit_breaker = overrides.circuit_breaker
    if overrides.tax_rate is not None:
        gov_overrides.tax_rate = overrides.tax_rate

    history = _load_policy_history(tenant_id=tenant.tenant_id, org_id=org_id)
    previous_version = history[-1].get("version") if history else None
    version = (previous_version or 0) + 1
    rollout_status = (
        "canary"
        if update.rollout_strategy == "canary" and (update.canary_percent or 0) < 100
        else "active"
    )
    detail = {
        "org_id": org_id,
        "version": version,
        "previous_version": previous_version,
        "preset": org.package.governance.preset,
        "overrides": org.package.governance.overrides.model_dump(exclude_none=True),
        "rollout": {
            "strategy": update.rollout_strategy,
            "status": rollout_status,
            "canary_percent": update.canary_percent
            if update.rollout_strategy == "canary"
            else None,
        },
    }
    _record_policy_event(
        tenant_id=tenant.tenant_id,
        org_id=org_id,
        version=version,
        action=_POLICY_ACTION_VERSIONED,
        detail=detail,
    )

    return {
        "status": "updated",
        "preset": org.package.governance.preset,
        "overrides": org.package.governance.overrides.model_dump(exclude_none=True),
        "policy_version": version,
        "previous_policy_version": previous_version,
        "rollout": detail["rollout"],
    }


@router.post("/promote")
async def promote_governance_canary(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Promote current canary rollout to active."""
    latest = _latest_policy_detail(tenant_id=tenant.tenant_id, org_id=org_id)
    if latest is None:
        raise HTTPException(status_code=409, detail="No versioned policy exists")
    rollout = latest.get("rollout", {})
    if rollout.get("status") != "canary":
        raise HTTPException(status_code=409, detail="No canary rollout to promote")

    promoted = dict(latest)
    promoted_rollout = dict(rollout)
    promoted_rollout["status"] = "active"
    promoted_rollout["canary_percent"] = 100
    promoted["rollout"] = promoted_rollout
    _record_policy_event(
        tenant_id=tenant.tenant_id,
        org_id=org_id,
        version=int(latest["version"]),
        action=_POLICY_ACTION_PROMOTED,
        detail=promoted,
    )
    return {
        "status": "promoted",
        "policy_version": latest["version"],
        "rollout": promoted_rollout,
    }


@router.post("/rollback")
async def rollback_governance_policy(
    req: GovernanceRollbackRequest | None = None,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Rollback current governance policy to a prior version."""
    org = _get_org(tenant.tenant_id, org_id)
    history = _load_policy_history(tenant_id=tenant.tenant_id, org_id=org_id)
    if not history:
        raise HTTPException(status_code=409, detail="No versioned policy exists")

    latest = history[-1]
    current_version = int(latest["version"])
    target_version = req.target_version if req is not None else None
    if target_version is None:
        target_version = int(latest.get("previous_version") or 0)
    if target_version <= 0:
        raise HTTPException(status_code=409, detail="No prior version available")

    target = next(
        (item for item in history if int(item["version"]) == target_version), None
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"Target version {target_version} does not exist"
        )

    org.package.governance.preset = target["preset"]
    gov_overrides = org.package.governance.overrides
    target_overrides = target.get("overrides", {})
    gov_overrides.audit_frequency = target_overrides.get("audit_frequency")
    cb = target_overrides.get("circuit_breaker")
    gov_overrides.circuit_breaker = (
        CircuitBreakerConfig(**cb) if isinstance(cb, dict) else cb
    )
    gov_overrides.tax_rate = target_overrides.get("tax_rate")

    rollback_version = current_version + 1
    detail = {
        "org_id": org_id,
        "version": rollback_version,
        "previous_version": current_version,
        "rollback_to_version": target_version,
        "preset": org.package.governance.preset,
        "overrides": org.package.governance.overrides.model_dump(exclude_none=True),
        "rollout": {"strategy": "rollback", "status": "active", "canary_percent": None},
    }
    _record_policy_event(
        tenant_id=tenant.tenant_id,
        org_id=org_id,
        version=rollback_version,
        action=_POLICY_ACTION_ROLLED_BACK,
        detail=detail,
    )

    return {
        "status": "rolled_back",
        "policy_version": rollback_version,
        "rollback_to_version": target_version,
        "preset": org.package.governance.preset,
        "overrides": org.package.governance.overrides.model_dump(exclude_none=True),
    }
