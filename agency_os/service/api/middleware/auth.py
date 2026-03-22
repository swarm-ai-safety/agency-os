"""API key / JWT authentication middleware."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Optional, cast

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from agency_os.service.api.middleware.rate_limit import RateLimiter
from agency_os.service.api.middleware.session_tokens import (
    hash_persistent_session_token,
    verify_tenant_session_token,
)
from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant, TenantRegistry

# Free tier hard limits — intentionally tight to drive conversion.
FREE_DEMO_MAX_RUNS = 1
FREE_TIER_AGENT_LIMIT = 1

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Module-level singletons (set by app startup)
_tenant_registry: Optional[TenantRegistry] = None
_rate_limiter: Optional[RateLimiter] = None
_db: Database | None = None
_APPROVAL_HEADER = "X-Manager-Approval"
_APPROVAL_REASON_HEADER = "X-Approval-Reason"


def set_tenant_registry(registry: TenantRegistry) -> None:
    global _tenant_registry
    _tenant_registry = registry


def set_rate_limiter(limiter: RateLimiter) -> None:
    global _rate_limiter
    _rate_limiter = limiter


def set_database(db: Database | None) -> None:
    global _db
    _db = db


def _audit_auth_failure(
    request: Request,
    *,
    reason: str,
    api_key: str | None = None,
    tenant_id: str | None = None,
) -> None:
    if _db is None:
        return
    key_fingerprint = None
    if api_key:
        key_fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:12]
    detail = json.dumps(
        {
            "reason": reason,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "unknown",
            "api_key_fingerprint": key_fingerprint,
        }
    )
    _db.save_audit_event(
        actor="system:auth",
        action="auth.failed",
        resource="api_key",
        resource_id=key_fingerprint,
        detail=detail,
        tenant_id=tenant_id,
    )


def _is_approved(request: Request) -> bool:
    value = request.headers.get(_APPROVAL_HEADER, "").strip().lower()
    return value in {"1", "true", "yes", "approved"}


def _approval_reason(request: Request) -> str:
    return cast(str, request.headers.get(_APPROVAL_REASON_HEADER, "").strip())


def _ensure_tenant_row(tenant: Tenant) -> None:
    """Backfill tenant row when auth succeeds but DB row is missing.

    This keeps FK-constrained writes (e.g. webhooks) robust under test/process
    startup permutations where in-memory tenant state can exist before schema rows.
    """
    if _db is None:
        return
    if _db.get_tenant(tenant.tenant_id) is not None:
        return
    api_key_hash = tenant.api_key
    if not getattr(tenant, "_from_db", False):
        api_key_hash = hashlib.sha256(api_key_hash.encode()).hexdigest()
    _db.save_tenant(
        {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "api_key_hash": api_key_hash,
            "active": tenant.active,
            "metadata": tenant.metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def require_action_approval(action: str):
    """Dependency factory enforcing explicit manager approval headers."""

    async def _require(
        request: Request,
        tenant: Tenant = Security(get_current_tenant),
    ) -> Tenant:
        if _is_approved(request) and len(_approval_reason(request)) >= 8:
            return tenant

        if _db is not None:
            _db.save_audit_event(
                actor=f"tenant:{tenant.tenant_id}",
                action="approval.denied",
                resource="high_impact_action",
                resource_id=action,
                detail=json.dumps(
                    {
                        "path": request.url.path,
                        "method": request.method,
                        "reason": "missing_or_invalid_approval_headers",
                        "required_headers": [
                            _APPROVAL_HEADER,
                            _APPROVAL_REASON_HEADER,
                        ],
                    }
                ),
                tenant_id=tenant.tenant_id,
            )

        raise HTTPException(
            status_code=403,
            detail=(
                "Explicit manager approval required for high-impact action. "
                f"Provide {_APPROVAL_HEADER}: true and a non-empty "
                f"{_APPROVAL_REASON_HEADER}."
            ),
        )

    return _require


async def get_current_tenant(
    request: Request,
    api_key: str = Security(api_key_header),
) -> Tenant:
    """Validate API key or session bearer token and return the tenant."""
    if _tenant_registry is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        payload = verify_tenant_session_token(token)
        tenant_id = ""
        if payload is not None:
            tenant_id = str(payload.get("sub", "")).strip()
        elif _db is not None:
            session = _db.get_active_tenant_session(
                hash_persistent_session_token(token), time.time()
            )
            if session is not None:
                tenant_id = str(session.get("tenant_id", "")).strip()

        if not tenant_id:
            _audit_auth_failure(request, reason="invalid_bearer_token")
            raise HTTPException(status_code=401, detail="Invalid bearer token")

        tenant = _tenant_registry.get(tenant_id)
        if tenant is None:
            _audit_auth_failure(
                request,
                reason="unknown_bearer_tenant",
                tenant_id=tenant_id,
            )
            raise HTTPException(status_code=401, detail="Invalid bearer token")
    else:
        if not api_key:
            _audit_auth_failure(request, reason="missing_api_key")
            raise HTTPException(status_code=401, detail="Missing API key")

        tenant = _tenant_registry.get_by_api_key(api_key)
        if tenant is None:
            _audit_auth_failure(request, reason="invalid_api_key", api_key=api_key)
            raise HTTPException(status_code=401, detail="Invalid API key")

    if not tenant.active:
        _audit_auth_failure(
            request,
            reason="tenant_deactivated",
            tenant_id=tenant.tenant_id,
            api_key=api_key,
        )
        raise HTTPException(status_code=403, detail="Tenant is deactivated")

    _ensure_tenant_row(tenant)

    # Apply rate limiting after authentication (only valid tenants are tracked)
    if _rate_limiter is not None:
        tier = tenant.metadata.get("tier", "free")
        rate_limit_info = _rate_limiter.check(tenant.tenant_id, tier=tier)
        # Store rate limit info in request state for middleware to add headers
        request.state.rate_limit_info = rate_limit_info

    return tenant


def _check_free_tier_quota(tenant: Tenant) -> None:
    """Enforce one-shot free demo quota. Raises 402 if already consumed."""
    runs_used = int(tenant.metadata.get("free_demo_runs_used", 0))
    if runs_used >= FREE_DEMO_MAX_RUNS:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Free demo already used ({FREE_DEMO_MAX_RUNS} example workflow run). "
                "Upgrade to Pro for continued usage: POST /api/v1/billing/checkout."
            ),
        )


async def require_active_billing(
    tenant: Tenant = Security(get_current_tenant),
) -> Tenant:
    """Require active Stripe billing or remaining free demo eligibility.

    Use this dependency on any endpoint that consumes LLM tokens.
    Free tier tenants (no billing_status or tier=free) are allowed through
    until they consume their one-shot free demo run.
    """
    if tenant.metadata.get("emergency_freeze") is True:
        raise HTTPException(
            status_code=423,
            detail=(
                "Tenant is in emergency freeze mode; token-consuming operations "
                "are temporarily disabled."
            ),
        )

    billing_status = tenant.metadata.get("billing_status")
    tier = tenant.metadata.get("tier", "free")

    # Paid tenants with active billing pass through
    if billing_status == "active":
        return tenant

    # Free tier bypass — enforce quota
    if tier == "free" and billing_status is None:
        _check_free_tier_quota(tenant)
        return tenant

    # Has a Stripe customer but no active subscription
    if not tenant.metadata.get("stripe_customer_id"):
        raise HTTPException(
            status_code=402,
            detail="Payment required. Set up billing at POST /api/v1/billing/setup-customer and complete checkout.",
        )
    if billing_status == "past_due":
        raise HTTPException(
            status_code=402,
            detail="Payment past due. Please update your payment method.",
        )
    raise HTTPException(
        status_code=402,
        detail="Active subscription required. Complete checkout at POST /api/v1/billing/checkout.",
    )


def record_free_tier_usage(tenant: Tenant, tokens: int) -> None:
    """Track free-tier demo consumption.

    Call this after each gateway/task call for free tier tenants.
    Does nothing for paid tenants.
    """
    _ = tokens
    if tenant.metadata.get("billing_status") == "active":
        return
    if tenant.metadata.get("tier", "free") != "free":
        return

    tenant.metadata["free_demo_runs_used"] = (
        int(tenant.metadata.get("free_demo_runs_used", 0)) + 1
    )
    tenant.metadata["free_demo_completed"] = (
        int(tenant.metadata.get("free_demo_runs_used", 0)) >= FREE_DEMO_MAX_RUNS
    )
