"""Task submission and tracking API router.

Tasks are assigned synchronously (bid auction) but executed
asynchronously in a background thread. Clients poll GET /tasks/{id}
for results.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from agency_os.governance.classifier import select_governance_preset
from agency_os.governance.task_sanitizer import sanitize_task_description
from agency_os.governance.trust import compute_trust_score
from agency_os.metering.collector import MeteringCollector
from agency_os.service.api.middleware.auth import require_active_billing
from agency_os.service.api.routers.organizations import _get_org, verify_org_ownership
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orgs/{org_id}/tasks", tags=["tasks"])

_metering: MeteringCollector | None = None
_task_db: Database | None = None
_webhook_dispatcher: Any | None = None
_autonomy_gate_status_getter: Any | None = None
# NOTE: ThreadPoolExecutor removed - tasks are now consumed by dedicated worker process


def set_metering(collector: MeteringCollector, db: Database | None) -> None:
    global _metering, _task_db
    _metering = collector
    _task_db = db


def set_webhook_dispatcher(dispatcher: Any) -> None:
    """Set the global webhook dispatcher (called from app.py)."""
    global _webhook_dispatcher
    _webhook_dispatcher = dispatcher


def set_autonomy_gate_status_getter(getter: Any | None) -> None:
    """Set optional callable returning current autonomy gate status."""
    global _autonomy_gate_status_getter
    _autonomy_gate_status_getter = getter


_MAX_METADATA_TOTAL_BYTES = 64 * 1024  # 64 KB total cap on metadata
_HIGH_IMPACT_PATTERN = re.compile(
    r"\b("
    r"deploy(ment)?\s+to\s+prod(uction)?|"
    r"prod(uction)?\s+deploy|"
    r"delete\s+data|"
    r"drop\s+table|"
    r"privilege\s+change|"
    r"grant\s+admin|"
    r"revoke\s+access|"
    r"spend\s+\$?\d+|"
    r"external\s+spend"
    r")\b",
    flags=re.IGNORECASE,
)

# NOTE: _execute_in_background function has been removed.
# Task execution now happens in agency_os.worker.TaskWorker instead of
# ThreadPoolExecutor threads. This allows horizontal scaling and proper
# multi-tenant task consumption.


def _enforce_credit_balance(tenant: Tenant) -> None:
    """Soft enforcement: reject task if credits depleted and no subscription.

    Returns 402 if the tenant has a Stripe customer but zero/negative balance
    and no active subscription. Logs a warning if balance is low.
    """
    customer_id = tenant.metadata.get("stripe_customer_id")
    if not customer_id:
        return  # No billing set up — skip enforcement

    # Skip if tenant has an active subscription (subscription handles payment)
    if tenant.metadata.get("billing_status") == "active" and tenant.metadata.get(
        "stripe_subscription_id"
    ):
        return

    try:
        from agency_os.billing_private.checkout import (
            _get_billing,
            get_cached_credit_balance,
        )

        billing = _get_billing()
        summary = get_cached_credit_balance(billing, customer_id)

        # Extract balance from Stripe response
        balances = summary.get("balances", [])
        total_available = 0
        for balance in balances:
            available = balance.get("available_balance", {})
            monetary = available.get("monetary", {})
            total_available += monetary.get("value", 0)

        if total_available <= 0:
            raise HTTPException(
                status_code=402,
                detail="Insufficient credit balance. Purchase credits or subscribe to continue.",
            )

        # Low balance warning
        included = tenant.metadata.get("included_credits_usd", 0)
        if included and total_available < int(included) * 0.1:
            logger.warning(
                "Tenant %s credit balance low: %d (included: %s)",
                tenant.tenant_id,
                total_available,
                included,
            )
    except HTTPException:
        raise
    except Exception:
        # Don't block tasks if balance check fails — soft enforcement
        logger.warning(
            "Credit balance check failed for tenant %s, allowing task",
            tenant.tenant_id,
        )


class SubmitTaskRequest(BaseModel):
    description: str = Field(min_length=1, max_length=10_000)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)
    execute: bool = False

    @model_validator(mode="after")
    def _check_metadata_size(self) -> "SubmitTaskRequest":
        total = sum(len(k) + len(v) for k, v in self.metadata.items())
        if total > _MAX_METADATA_TOTAL_BYTES:
            raise ValueError(
                f"metadata total size {total} bytes exceeds limit of {_MAX_METADATA_TOTAL_BYTES}"
            )
        return self


@router.post("")
async def submit_task(
    req: SubmitTaskRequest,
    request: Request,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Submit a task to an organization.

    Tasks are assigned via bid auction immediately. If execute=true,
    the winning agent runs the task in the background. Poll
    GET /tasks/{task_id} for results.
    """
    # Soft credit enforcement: reject if credits depleted and no active subscription
    _enforce_credit_balance(tenant)

    high_impact = bool(_HIGH_IMPACT_PATTERN.search(req.description))
    if high_impact:
        approval = request.headers.get("X-Manager-Approval", "").strip().lower()
        reason = request.headers.get("X-Approval-Reason", "").strip()
        if approval not in {"1", "true", "yes", "approved"} or len(reason) < 8:
            if _task_db is not None:
                _task_db.save_audit_event(
                    actor=f"tenant:{tenant.tenant_id}",
                    action="approval.denied",
                    resource="task.high_impact",
                    resource_id=org_id,
                    detail=json.dumps(
                        {
                            "reason": "missing_or_invalid_approval_headers",
                            "required_headers": [
                                "X-Manager-Approval",
                                "X-Approval-Reason",
                            ],
                        }
                    ),
                    tenant_id=tenant.tenant_id,
                )
            raise HTTPException(
                status_code=403,
                detail=(
                    "High-impact task requires explicit manager approval. "
                    "Set X-Manager-Approval: true and X-Approval-Reason."
                ),
            )

    # Sanitize the task description against prompt injection
    sanitization = sanitize_task_description(req.description)
    if sanitization.flagged:
        logger.warning(
            "Prompt injection patterns detected in task description from tenant %s: %s",
            tenant.tenant_id,
            sanitization.flags,
        )
        if _task_db is not None:
            _task_db.save_audit_event(
                actor=f"tenant:{tenant.tenant_id}",
                action="task.prompt_injection_detected",
                resource="task",
                resource_id=org_id,
                detail=json.dumps({"flags": sanitization.flags}),
                tenant_id=tenant.tenant_id,
            )
    safe_description = sanitization.sanitized

    org = _get_org(tenant.tenant_id, org_id)
    result = org.submit_task(safe_description, req.metadata)

    # Auto-select governance preset based on task type + agent trust
    agent_id = result.get("assigned_to")
    trust = None
    if _metering is not None and agent_id:
        trust = compute_trust_score(_metering, agent_id, tenant.tenant_id)
    governance = select_governance_preset(safe_description, trust=trust)
    autonomy_gate = (
        _autonomy_gate_status_getter()
        if callable(_autonomy_gate_status_getter)
        else {"degraded": False}
    )
    if autonomy_gate.get("degraded"):
        governance = replace(governance, preset="conservative")
        # Enforce conservative on the actual org config, not just metadata
        org.package.governance.preset = "conservative"
        autonomy_reason = autonomy_gate.get("reason")
        if isinstance(autonomy_reason, str) and autonomy_reason:
            governance = replace(
                governance,
                reason=f"{governance.reason}; autonomy gate: {autonomy_reason}",
            )

    result["governance"] = {
        "preset": governance.preset,
        "task_type": governance.task_type.value,
        "trust_tier": governance.trust_tier,
        "reason": governance.reason,
    }

    # All tasks are queued with status='assigned' for worker consumption.
    # The 'execute' parameter is deprecated but kept for API compatibility.
    status = "assigned"

    # Persist task to database - worker will pick it up
    db = _task_db
    if db is not None:
        db.save_task(
            {
                "task_id": result["task_id"],
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "description": safe_description,
                "assigned_to": agent_id,
                "status": status,
                "governance_preset": governance.preset,
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="task.submitted",
            resource="task",
            resource_id=result["task_id"],
            detail=json.dumps(
                {
                    "org_id": org_id,
                    "assigned_to": agent_id,
                    "governance_preset": governance.preset,
                }
            ),
            tenant_id=tenant.tenant_id,
        )
    else:
        logger.warning(
            "No database configured - task will not be persisted or executed"
        )

    result["status"] = status
    result["note"] = "Task queued for execution by worker"
    return result


@router.get("/failures")
async def get_run_failures(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
    since: str | None = Query(
        default=None, description="ISO8601 start datetime (inclusive)"
    ),
    until: str | None = Query(
        default=None, description="ISO8601 end datetime (inclusive)"
    ),
    agent_id: str | None = Query(
        default=None, description="Filter by assigned agent ID"
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Get run failure metrics for an organization.

    Returns failure count, rate, common error causes, and recent failed tasks.
    Filterable by agent and time range. Links failed tasks via task_id for
    investigation using GET /tasks/{task_id}.
    """
    _get_org(tenant.tenant_id, org_id)  # verify access
    db = _task_db
    if db is not None:
        return db.get_run_failure_metrics(
            tenant_id=tenant.tenant_id,
            org_id=org_id,
            since=since,
            until=until,
            agent_id=agent_id,
            limit=limit,
        )
    return {
        "total_tasks": 0,
        "failure_count": 0,
        "failure_rate": 0.0,
        "recent_failures": [],
        "common_causes": [],
    }


@router.get("")
async def list_tasks(
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
) -> list[dict[str, Any]]:
    """List all tasks for an organization."""
    _get_org(tenant.tenant_id, org_id)  # verify access
    db = _task_db
    if db is not None:
        return db.list_tasks(org_id, tenant_id=tenant.tenant_id)
    return []


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Get a specific task by ID."""
    _get_org(tenant.tenant_id, org_id)  # verify access
    db = _task_db
    if db is not None:
        task = db.get_task(task_id, tenant_id=tenant.tenant_id)
        if task and task.get("org_id") == org_id:
            return task
    raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")


@router.get("/{task_id}/trajectory")
async def get_task_trajectory(
    task_id: str,
    org_id: str = Depends(verify_org_ownership),
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Return the ATIF trajectory for a completed task."""
    _get_org(tenant.tenant_id, org_id)  # verify access
    db = _task_db
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Verify task exists and belongs to this org
    task = db.get_task(task_id, tenant_id=tenant.tenant_id)
    if not task or task.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    trajectory = db.get_trajectory(task_id, tenant_id=tenant.tenant_id)
    if trajectory is None:
        raise HTTPException(
            status_code=404,
            detail=f"No trajectory recorded for task: {task_id}",
        )
    return trajectory
