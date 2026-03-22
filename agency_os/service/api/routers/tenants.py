"""Tenant signup and lifecycle API router."""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from agency_os.service.api.middleware.auth import (
    get_current_tenant,
    require_action_approval,
)
from agency_os.service.api.middleware.passwords import hash_password, verify_password
from agency_os.service.api.middleware.session_tokens import (
    create_persistent_session_token,
    hash_persistent_session_token,
)
from agency_os.service.email import (
    send_password_reset_email,
    send_welcome_email,
    verify_unsubscribe_token,
)
from agency_os.tenancy.tenant import Tenant, TenantRegistry

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

_tenant_registry: TenantRegistry | None = None
_db: Any | None = None
_rotation_lock = threading.Lock()

# IP-based rate limit for signup: max 5 per hour (bounded LRU)
_signup_rate: collections.OrderedDict[str, list[float]] = collections.OrderedDict()
_signup_rate_lock = threading.Lock()
_SIGNUP_RATE_WINDOW = 3600
_SIGNUP_RATE_MAX = 5
_SIGNUP_RATE_MAX_IPS = 10_000

# IP-based rate limit for login: max 10 per 15 minutes (bounded LRU)
_login_rate: collections.OrderedDict[str, list[float]] = collections.OrderedDict()
_login_rate_lock = threading.Lock()
_LOGIN_RATE_WINDOW = 900
_LOGIN_RATE_MAX = 10
FREE_SIGNUP_BUDGET_USD = 2.0
_PASSWORD_RESET_TTL = 3600  # 1 hour
_PASSWORD_RESET_RATE_WINDOW = 900  # 15 minutes
_PASSWORD_RESET_RATE_MAX = 5
_reset_rate: collections.OrderedDict[str, list[float]] = collections.OrderedDict()
_reset_rate_lock = threading.Lock()

logger = logging.getLogger(__name__)
PERSISTENT_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
FREE_TIER_ALLOWED_MODELS = [
    "groq-llama-3.1-8b",
]


def reset_signup_rate_limiter() -> None:
    """Clear in-memory signup rate state.

    Useful for test isolation when multiple app instances are created
    in the same Python process.
    """
    with _signup_rate_lock:
        _signup_rate.clear()


def reset_login_rate_limiter() -> None:
    """Clear in-memory login rate state (test isolation)."""
    with _login_rate_lock:
        _login_rate.clear()


def set_tenant_registry(registry: TenantRegistry) -> None:
    global _tenant_registry
    _tenant_registry = registry


def set_database(db: Any) -> None:
    global _db
    _db = db


def _get_registry() -> TenantRegistry:
    if _tenant_registry is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    return _tenant_registry


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=256)


class CreateTenantResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str
    session_token: str
    session_expires_in: int


class TenantLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class TenantSessionResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    session_token: str
    session_expires_in: int


class TenantOnboardingResponse(BaseModel):
    account_created: bool
    has_organization: bool
    has_first_task: bool
    billing_configured: bool
    has_first_api_call: bool
    completed_steps: int
    total_steps: int
    is_complete: bool
    next_step: str
    organizations_count: int
    tasks_count: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class EmergencyFreezeRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=8, max_length=500)


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, preferring X-Forwarded-For when behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry is the original client; subsequent entries are proxies.
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    return request.client.host if request.client else "unknown"


def _check_signup_rate(client_ip: str) -> None:
    with _signup_rate_lock:
        now = time.time()
        # LRU eviction
        while len(_signup_rate) > _SIGNUP_RATE_MAX_IPS:
            _signup_rate.popitem(last=False)
        hits = _signup_rate.get(client_ip, [])
        hits = [t for t in hits if now - t < _SIGNUP_RATE_WINDOW]
        if len(hits) >= _SIGNUP_RATE_MAX:
            raise HTTPException(
                status_code=429, detail="Too many signups, try again later"
            )
        hits.append(now)
        _signup_rate[client_ip] = hits
        _signup_rate.move_to_end(client_ip)


def _check_reset_rate(client_ip: str) -> None:
    with _reset_rate_lock:
        now = time.time()
        while len(_reset_rate) > _SIGNUP_RATE_MAX_IPS:
            _reset_rate.popitem(last=False)
        hits = _reset_rate.get(client_ip, [])
        hits = [t for t in hits if now - t < _PASSWORD_RESET_RATE_WINDOW]
        if len(hits) >= _PASSWORD_RESET_RATE_MAX:
            raise HTTPException(
                status_code=429, detail="Too many reset requests, try again later"
            )
        hits.append(now)
        _reset_rate[client_ip] = hits
        _reset_rate.move_to_end(client_ip)


def _check_login_rate(client_ip: str) -> None:
    with _login_rate_lock:
        now = time.time()
        while len(_login_rate) > _SIGNUP_RATE_MAX_IPS:
            _login_rate.popitem(last=False)
        hits = _login_rate.get(client_ip, [])
        hits = [t for t in hits if now - t < _LOGIN_RATE_WINDOW]
        if len(hits) >= _LOGIN_RATE_MAX:
            raise HTTPException(
                status_code=429, detail="Too many login attempts, try again later"
            )
        hits.append(now)
        _login_rate[client_ip] = hits
        _login_rate.move_to_end(client_ip)


def _issue_persistent_session(tenant: Tenant) -> tuple[str, int]:
    if _db is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    token = create_persistent_session_token()
    token_hash = hash_persistent_session_token(token)
    now = time.time()
    _db.create_tenant_session(
        session_id=f"tsn-{uuid.uuid4().hex}",
        tenant_id=tenant.tenant_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + PERSISTENT_SESSION_TTL_SECONDS,
    )
    return token, PERSISTENT_SESSION_TTL_SECONDS


def _find_tenant_for_identifier(
    identifier: str, registry: TenantRegistry
) -> Tenant | None:
    ident = identifier.strip()
    if not ident:
        return None
    if "@" in ident:
        return registry.find_by_metadata("email", ident.lower())
    return registry.get(ident)


@router.post("", response_model=CreateTenantResponse)
async def create_tenant(req: CreateTenantRequest, request: Request) -> dict[str, Any]:
    """Create a new tenant and return their API key.

    This is the public signup endpoint — no auth required.
    The plaintext API key is returned exactly once in this response.
    """
    client_ip = _get_client_ip(request)
    _check_signup_rate(client_ip)
    registry = _get_registry()
    if req.email and registry.email_exists(req.email):
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists. Try logging in.",
        )
    metadata: dict[str, Any] = {
        "tier": "free",
        "budget_limit_usd": FREE_SIGNUP_BUDGET_USD,
        "allowed_models": list(FREE_TIER_ALLOWED_MODELS),
    }
    metadata["password_hash"] = hash_password(req.password)
    metadata["signed_up_at"] = time.time()
    if req.email:
        metadata["email"] = req.email.lower()

    tenant, plaintext_key = registry.register(name=req.name, metadata=metadata)
    # Store masked key prefix for settings display (e.g. "ak-Abc1...").
    tenant.metadata["key_prefix"] = plaintext_key[:8]
    registry.save_metadata(tenant)
    session_token, session_expires_in = _issue_persistent_session(tenant)
    if _db is not None:
        _db.save_audit_event(
            actor="system:signup",
            action="tenant.registered",
            resource="tenant",
            resource_id=tenant.tenant_id,
            detail=json.dumps({"email_provided": bool(req.email)}),
            tenant_id=tenant.tenant_id,
        )
    # Send welcome email (non-blocking — failure is logged, not raised)
    if req.email:
        send_welcome_email(req.email.lower(), req.name)

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "api_key": plaintext_key,
        "session_token": session_token,
        "session_expires_in": session_expires_in,
    }


@router.post("/login", response_model=TenantSessionResponse)
async def login(body: TenantLoginRequest, request: Request) -> dict[str, Any]:
    client_ip = _get_client_ip(request)
    _check_login_rate(client_ip)
    registry = _get_registry()
    tenant = _find_tenant_for_identifier(body.identifier, registry)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    password_hash = str(tenant.metadata.get("password_hash", "")).strip()
    if not password_hash or not verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not tenant.active:
        raise HTTPException(status_code=403, detail="Tenant is deactivated")

    session_token, session_expires_in = _issue_persistent_session(tenant)
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "session_token": session_token,
        "session_expires_in": session_expires_in,
    }


@router.post("/request-password-reset")
async def request_password_reset(
    body: PasswordResetRequest, request: Request
) -> dict[str, str]:
    """Generate a password reset token for the given email.

    Always returns success to avoid email enumeration. The reset token
    is logged server-side; wire up email delivery to send it to users.
    """
    client_ip = _get_client_ip(request)
    _check_reset_rate(client_ip)
    registry = _get_registry()
    # Generic success message regardless of whether email exists
    generic = {"message": "If that email is registered, a reset link has been sent."}

    tenant = registry.find_by_metadata("email", body.email.lower())
    if tenant is None:
        return generic

    # Generate token, store hash + expiry in metadata
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    tenant.metadata["password_reset_token_hash"] = token_hash
    tenant.metadata["password_reset_expires"] = time.time() + _PASSWORD_RESET_TTL
    registry.save_metadata(tenant)

    # Build reset URL from request origin
    origin = request.headers.get("origin", "").strip()
    if not origin:
        forwarded_proto = (
            request.headers.get("x-forwarded-proto", "https").split(",")[0].strip()
        )
        forwarded_host = (
            request.headers.get("x-forwarded-host", "").split(",")[0].strip()
        )
        host = forwarded_host or request.headers.get("host", "zero-human-labs.com")
        origin = f"{forwarded_proto}://{host}"
    reset_url = f"{origin}/reset-password?token={token}"

    # Send email (falls back to logging if RESEND_API_KEY not set)
    send_password_reset_email(body.email.lower(), reset_url)

    logger.info(
        "Password reset requested for tenant %s",
        tenant.tenant_id,
    )

    if _db is not None:
        _db.save_audit_event(
            actor="system:password_reset",
            action="tenant.password_reset_requested",
            resource="tenant",
            resource_id=tenant.tenant_id,
            detail=json.dumps({"email": body.email.lower()}),
            tenant_id=tenant.tenant_id,
        )

    return generic


@router.post("/reset-password")
async def reset_password(
    body: PasswordResetConfirm, request: Request
) -> dict[str, str]:
    """Reset password using a valid reset token."""
    client_ip = _get_client_ip(request)
    _check_reset_rate(client_ip)
    registry = _get_registry()

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()

    # Find tenant with matching reset token
    target: Tenant | None = None
    for tenant in registry._tenants.values():
        stored_hash = tenant.metadata.get("password_reset_token_hash")
        expires = tenant.metadata.get("password_reset_expires", 0)
        if (
            stored_hash
            and hmac.compare_digest(stored_hash, token_hash)
            and time.time() < expires
        ):
            target = tenant
            break

    if target is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Update password, clear reset token
    target.metadata["password_hash"] = hash_password(body.new_password)
    target.metadata.pop("password_reset_token_hash", None)
    target.metadata.pop("password_reset_expires", None)
    registry.save_metadata(target)

    if _db is not None:
        _db.save_audit_event(
            actor="system:password_reset",
            action="tenant.password_reset_completed",
            resource="tenant",
            resource_id=target.tenant_id,
            detail="{}",
            tenant_id=target.tenant_id,
        )

    return {"message": "Password has been reset. You can now log in."}


@router.get("/me")
async def get_current_tenant_info(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Get current tenant info (excludes API key and internal IDs)."""
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "active": tenant.active,
        "billing_status": tenant.metadata.get("billing_status"),
        "tier": tenant.metadata.get("tier", "free"),
        "budget_limit_usd": tenant.metadata.get("budget_limit_usd", 0.0),
        "total_spent_usd": tenant.metadata.get("total_spent_usd", 0.0),
        "stripe_customer_id": tenant.metadata.get("stripe_customer_id"),
        "key_prefix": tenant.metadata.get("key_prefix"),
        "email": tenant.metadata.get("email"),
    }


@router.get("/me/onboarding", response_model=TenantOnboardingResponse)
async def get_tenant_onboarding_status(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Compute onboarding progress from live tenant/org/task/gateway state."""
    if _db is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    orgs = _db.list_orgs(tenant.tenant_id)
    organizations_count = len(orgs)
    has_organization = organizations_count > 0

    tasks_count = 0
    for org in orgs:
        org_id = str(org.get("org_id", "")).strip()
        if not org_id:
            continue
        tasks_count += len(_db.list_tasks(org_id, tenant.tenant_id))
    has_first_task = tasks_count > 0

    billing_configured = bool(tenant.metadata.get("stripe_customer_id"))
    gateway_stats = _db.get_gateway_stats(tenant.tenant_id)
    total_requests = int(gateway_stats.get("total_requests", 0) or 0)
    has_first_api_call = total_requests > 0

    completed_steps = (
        1 + int(has_organization) + int(has_first_task) + int(billing_configured)
    )
    total_steps = 4
    is_complete = has_organization and has_first_task and billing_configured

    if not has_organization:
        next_step = "create_organization"
    elif not has_first_task:
        next_step = "run_first_task"
    elif not billing_configured:
        next_step = "configure_billing"
    elif not has_first_api_call:
        next_step = "make_first_api_call"
    else:
        next_step = "complete"

    return {
        "account_created": True,
        "has_organization": has_organization,
        "has_first_task": has_first_task,
        "billing_configured": billing_configured,
        "has_first_api_call": has_first_api_call,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "is_complete": is_complete,
        "next_step": next_step,
        "organizations_count": organizations_count,
        "tasks_count": tasks_count,
    }


@router.post("/me/rotate-key")
async def rotate_api_key(
    tenant: Tenant = Depends(require_action_approval("tenant.rotate_api_key")),
) -> dict[str, str]:
    """Generate a new API key for the current tenant.

    The old key is immediately invalidated. The new plaintext key
    is returned exactly once in this response.
    """
    import secrets

    registry = _get_registry()

    with _rotation_lock:
        # tenant.api_key is always a hash now (from register or DB load)
        old_hash = tenant.api_key
        if old_hash not in registry._by_key_hash:
            raise HTTPException(
                status_code=409, detail="Key already rotated by another request"
            )
        registry._by_key_hash.pop(old_hash, None)

        # Generate new key, store only hash
        new_key = f"ak-{secrets.token_urlsafe(32)}"
        new_hash = registry._hash_key(new_key)
        tenant.api_key = new_hash
        tenant._from_db = True  # type: ignore[attr-defined]
        tenant.metadata["key_prefix"] = new_key[:8]
        registry._by_key_hash[new_hash] = tenant
        registry.save_metadata(tenant)
        if _db is not None:
            _db.save_audit_event(
                actor=f"tenant:{tenant.tenant_id}",
                action="tenant.api_key_rotated",
                resource="tenant",
                resource_id=tenant.tenant_id,
                detail=json.dumps(
                    {
                        "old_key_fingerprint": old_hash[:12],
                        "new_key_fingerprint": new_hash[:12],
                    }
                ),
                tenant_id=tenant.tenant_id,
            )

    return {
        "api_key": new_key,
        "message": "Key rotated. Old key is no longer valid.",
    }


@router.post("/me/emergency-freeze")
async def set_emergency_freeze(
    req: EmergencyFreezeRequest,
    tenant: Tenant = Depends(require_action_approval("tenant.set_emergency_freeze")),
) -> dict[str, Any]:
    """Enable/disable tenant emergency freeze switch for token operations."""
    tenant.metadata["emergency_freeze"] = req.enabled
    tenant.metadata["emergency_freeze_reason"] = req.reason
    if _tenant_registry is not None:
        _tenant_registry.save_metadata(tenant)
    if _db is not None:
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="tenant.emergency_freeze.updated",
            resource="tenant",
            resource_id=tenant.tenant_id,
            detail=json.dumps({"enabled": req.enabled, "reason": req.reason}),
            tenant_id=tenant.tenant_id,
        )
    return {
        "tenant_id": tenant.tenant_id,
        "emergency_freeze": req.enabled,
        "reason": req.reason,
    }


@router.get("/me/organizations")
async def list_tenant_organizations(
    tenant: Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List all organizations owned by the authenticated tenant.

    Returns organizations from the database (all orgs ever created by this tenant),
    not just currently running orgs.
    """
    if _db is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    orgs = _db.list_orgs(tenant.tenant_id)

    # Transform to match required response format
    return [
        {
            "org_id": org["org_id"],
            "name": org["package_name"],  # Use package_name as name
            "status": org["status"],
            "agent_count": 0,  # Not persisted in DB, would need in-memory lookup
            "created_at": org["created_at"],
        }
        for org in orgs
    ]


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_confirm(tenant_id: str, token: str) -> HTMLResponse:
    """Show confirmation page — does NOT perform opt-out (defeats link prefetchers)."""
    if not verify_unsubscribe_token(tenant_id, token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    registry = _get_registry()
    tenant = registry.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    import html as html_mod

    safe_tid = html_mod.escape(tenant_id)
    safe_token = html_mod.escape(token)
    return HTMLResponse(f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Unsubscribe</title></head>
<body style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 60px auto; text-align: center;">
  <h2>Unsubscribe from emails?</h2>
  <p style="color: #666;">Click the button below to confirm.</p>
  <form method="POST" action="/api/v1/tenants/unsubscribe">
    <input type="hidden" name="tenant_id" value="{safe_tid}">
    <input type="hidden" name="token" value="{safe_token}">
    <button type="submit" style="padding: 12px 32px; background: #00ff88; color: #000;
      font-weight: 600; border: none; border-radius: 8px; cursor: pointer; font-size: 16px;">
      Confirm Unsubscribe
    </button>
  </form>
</body></html>""")


@router.post("/unsubscribe")
async def unsubscribe(request: Request) -> dict[str, str]:
    """Perform the actual opt-out (POST only — safe from prefetchers)."""
    form = await request.form()
    tenant_id = str(form.get("tenant_id", ""))
    token = str(form.get("token", ""))

    if not tenant_id or not token:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    if not verify_unsubscribe_token(tenant_id, token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    registry = _get_registry()
    tenant = registry.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")

    tenant.metadata["email_opt_out"] = True
    registry.save_metadata(tenant)

    if _db is not None:
        _db.save_audit_event(
            actor=f"tenant:{tenant_id}",
            action="tenant.email_opt_out",
            resource="tenant",
            resource_id=tenant_id,
            detail=json.dumps({"source": "unsubscribe_link"}),
            tenant_id=tenant_id,
        )

    return {"message": "You have been unsubscribed from marketing emails."}
