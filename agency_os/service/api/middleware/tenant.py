"""Tenant context middleware — extracts tenant from request."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from agency_os.tenancy.tenant import Tenant

# Context variable for current tenant (thread-safe)
current_tenant_var: ContextVar[Optional[Tenant]] = ContextVar(
    "current_tenant", default=None
)


def get_tenant_context() -> Optional[Tenant]:
    """Get the current tenant from context."""
    return current_tenant_var.get()


def set_tenant_context(tenant: Tenant) -> None:
    """Set the current tenant in context."""
    current_tenant_var.set(tenant)
