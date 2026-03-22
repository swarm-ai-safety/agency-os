"""OIDC bridge endpoints for dashboard session issuance."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from agency_os.service.api.middleware.session_tokens import create_tenant_session_token
from agency_os.tenancy.tenant import TenantRegistry

router = APIRouter(prefix="/api/v1/auth/oidc", tags=["auth"])

_tenant_registry: TenantRegistry | None = None


class OidcSessionRequest(BaseModel):
    email: EmailStr
    subject: str = Field(min_length=1, max_length=512)
    issuer: str = Field(min_length=1, max_length=512)


class OidcSessionResponse(BaseModel):
    session_token: str
    tenant_id: str
    tenant_name: str
    expires_in: int


def set_tenant_registry(registry: TenantRegistry) -> None:
    global _tenant_registry
    _tenant_registry = registry


def _require_bridge_secret(secret: str | None) -> None:
    configured = os.environ.get("AGENCY_OS_OIDC_BRIDGE_SECRET", "").strip()
    if not configured:
        raise HTTPException(status_code=500, detail="OIDC bridge not configured")
    if not secret or not hmac.compare_digest(secret.strip(), configured):
        raise HTTPException(status_code=401, detail="Unauthorized OIDC bridge caller")


@router.post("/session", response_model=OidcSessionResponse)
async def create_oidc_session(
    body: OidcSessionRequest,
    x_oidc_bridge_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    """Exchange verified OIDC identity for a short-lived tenant session token.

    The caller must be trusted server-side frontend middleware that has already
    completed OIDC code exchange and userinfo lookup.
    """
    _require_bridge_secret(x_oidc_bridge_secret)

    if _tenant_registry is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    tenant = _tenant_registry.find_by_metadata("email", body.email)
    if tenant is None:
        raise HTTPException(
            status_code=403,
            detail="No tenant found for this OIDC identity. Sign up first.",
        )
    if not tenant.active:
        raise HTTPException(status_code=403, detail="Tenant is deactivated")

    token = create_tenant_session_token(tenant.tenant_id)
    return {
        "session_token": token,
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "expires_in": 8 * 60 * 60,
    }
