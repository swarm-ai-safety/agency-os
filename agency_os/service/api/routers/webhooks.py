"""Webhook notification API router."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from agency_os.service.api.middleware.auth import get_current_tenant
from agency_os.service.webhook_repository import WebhookRepository
from agency_os.service.webhooks import (
    BUDGET_ALERT,
    CIRCUIT_BREAKER_TRIPPED,
    ORG_STARTED,
    ORG_STOPPED,
    TASK_ASSIGNED,
    TASK_COMPLETED,
)
from agency_os.tenancy.tenant import Tenant

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Webhook repository singleton (set by app.py)
_repository: WebhookRepository | None = None
# Legacy: direct dispatcher (fallback when repository not available)
_legacy_dispatcher: Any | None = None
# In-memory health tracker (set by app.py)
_health_tracker: Any | None = None
_MAX_WEBHOOKS_PER_TENANT = 10
_MAX_DELIVERY_QUERY_LIMIT = 200

_ALLOWED_EVENT_TYPES = frozenset(
    {
        TASK_ASSIGNED,
        TASK_COMPLETED,
        BUDGET_ALERT,
        CIRCUIT_BREAKER_TRIPPED,
        ORG_STARTED,
        ORG_STOPPED,
    }
)


def set_webhook_repository(repository: WebhookRepository) -> None:
    """Set the global webhook repository (called from app.py)."""
    global _repository, _legacy_dispatcher
    _repository = repository
    # Ensure modes are mutually exclusive across repeated app bootstrap calls.
    _legacy_dispatcher = None


def set_webhook_dispatcher(dispatcher: Any) -> None:
    """Legacy: set webhook dispatcher directly (deprecated, kept for backward compat)."""
    global _legacy_dispatcher, _repository
    _legacy_dispatcher = dispatcher
    # Prevent stale repository usage when running without SecretStore.
    _repository = None


def set_webhook_health_tracker(tracker: Any) -> None:
    """Set the global webhook health tracker (called from app.py)."""
    global _health_tracker
    _health_tracker = tracker


def _validate_webhook_url(url: str) -> str:
    """Validate webhook URL format: HTTPS only, must have a hostname.

    DNS resolution and private-IP blocking are enforced at delivery time
    (see ``WebhookDispatcher._send_once``) so that registration does not
    require network access.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Webhook URL must have a hostname")
    # Block obvious localhost/loopback hostnames without DNS lookup
    _blocked = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    if parsed.hostname in _blocked:
        raise ValueError("Webhook URL must not resolve to a private/internal address")
    return url


class WebhookRegistration(BaseModel):
    url: str
    events: list[str] = ["task.completed", "budget.alert", "circuit_breaker.tripped"]

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        return _validate_webhook_url(v)

    @field_validator("events")
    @classmethod
    def check_events(cls, v: list[str]) -> list[str]:
        invalid = set(v) - _ALLOWED_EVENT_TYPES
        if invalid:
            raise ValueError(
                f"Invalid event types: {invalid}. Allowed: {sorted(_ALLOWED_EVENT_TYPES)}"
            )
        return v


@router.post("")
async def register_webhook(
    req: WebhookRegistration,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Register a webhook URL for event notifications.

    Returns the webhook registration with a signing secret. Store this secret
    securely - it's used to verify webhook signatures via HMAC-SHA256.
    """
    # Prefer repository (with persistence), fall back to legacy dispatcher
    if _repository is not None:
        # Check subscription count limit
        existing = _repository.list(tenant.tenant_id)
        if len(existing) >= _MAX_WEBHOOKS_PER_TENANT:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum of {_MAX_WEBHOOKS_PER_TENANT} webhooks per tenant",
            )

        # Create webhook with encrypted secret
        webhook = _repository.create(
            tenant_id=tenant.tenant_id,
            url=req.url,
            events=req.events,
        )

        return {
            "status": "registered",
            "webhook": {
                "id": webhook["id"],
                "url": webhook["url"],
                "events": webhook["events"],
                "secret": webhook["secret"],
                "created_at": webhook["created_at"],
            },
            "info": "Store the secret securely. Use it to verify X-AgencyOS-Signature headers. See docs/api-reference.md#verifying-webhook-signatures for examples.",
        }
    elif _legacy_dispatcher is not None:
        # Legacy path: in-memory dispatcher without persistence
        import secrets as secrets_module

        org_id = tenant.tenant_id
        existing_subs = _legacy_dispatcher._subscriptions.get(org_id, [])
        if len(existing_subs) >= _MAX_WEBHOOKS_PER_TENANT:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum of {_MAX_WEBHOOKS_PER_TENANT} webhooks per tenant",
            )

        secret = secrets_module.token_urlsafe(32)
        _legacy_dispatcher.subscribe(
            org_id=org_id, url=req.url, events=req.events, secret=secret
        )

        return {
            "status": "registered",
            "webhook": {"url": req.url, "events": req.events, "secret": secret},
            "info": "Store the secret securely. Use it to verify X-AgencyOS-Signature headers. See docs/api-reference.md#verifying-webhook-signatures for examples.",
        }
    else:
        raise HTTPException(
            status_code=500, detail="Webhook dispatcher not initialized"
        )


@router.get("")
async def list_webhooks(
    tenant: Tenant = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List registered webhooks.

    Note: Secrets are not returned for security reasons.
    """
    if _repository is not None:
        return _repository.list(tenant.tenant_id)
    elif _legacy_dispatcher is not None:
        # Legacy path: in-memory dispatcher
        org_id = tenant.tenant_id
        subs = _legacy_dispatcher._subscriptions.get(org_id, [])
        return [{"url": sub.url, "events": sub.events} for sub in subs]
    else:
        raise HTTPException(
            status_code=500, detail="Webhook dispatcher not initialized"
        )


@router.get("/health")
async def webhook_health(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Webhook delivery health dashboard for the current tenant.

    Returns in-memory latency percentiles (P50/P95), delivery success rate,
    failed delivery counts, and retry queue depth.
    """
    result: dict[str, Any] = {}

    # In-memory sliding-window metrics (latency + real-time success rate)
    if _health_tracker is not None:
        result["realtime"] = _health_tracker.stats()

    # Database-backed aggregate metrics (tenant-scoped)
    if _repository is not None:
        result["persistent"] = _repository.delivery_stats(tenant_id=tenant.tenant_id)

    if not result:
        raise HTTPException(
            status_code=500, detail="Webhook health tracking not initialized"
        )

    return result


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Delete a webhook subscription."""
    if _repository is None:
        raise HTTPException(
            status_code=500, detail="Webhook repository not initialized"
        )

    success = _repository.delete(webhook_id, tenant.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"status": "deleted", "id": webhook_id}


@router.post("/{webhook_id}/rotate-secret")
async def rotate_webhook_secret(
    webhook_id: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Rotate webhook signing secret.

    Returns a new secret. Store it securely - this is the only time it will be returned.
    The old secret is immediately invalidated.
    """
    if _repository is None:
        raise HTTPException(
            status_code=500, detail="Webhook repository not initialized"
        )

    result = _repository.rotate_secret(webhook_id, tenant.tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {
        "status": "rotated",
        "webhook": {
            "id": result["id"],
            "url": result["url"],
            "secret": result["secret"],
            "rotated_at": result["rotated_at"],
        },
        "info": "Store the new secret securely. The old secret is now invalid.",
    }


@router.get("/{webhook_id}/deliveries")
async def list_webhook_deliveries(
    webhook_id: str,
    limit: int = 100,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """List recent delivery status for a webhook."""
    if _repository is None:
        raise HTTPException(
            status_code=500, detail="Webhook repository not initialized"
        )
    if limit < 1 or limit > _MAX_DELIVERY_QUERY_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be between 1 and {_MAX_DELIVERY_QUERY_LIMIT}",
        )
    webhook = _repository.get(webhook_id, tenant.tenant_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    deliveries = _repository.list_deliveries(
        tenant_id=tenant.tenant_id, webhook_id=webhook_id, limit=limit
    )
    return {
        "webhook_id": webhook_id,
        "deliveries": deliveries,
    }
