"""Process-level isolation per tenant organization."""

from __future__ import annotations

import logging
from typing import Optional

from agency_os.orchestration.organization import Organization

logger = logging.getLogger(__name__)


class OrgIsolator:
    """
    Manages isolated organization instances per tenant.

    Each tenant's orgs run in their own namespace. Prevents cross-tenant
    data leakage and resource interference.
    """

    def __init__(self) -> None:
        self._orgs: dict[
            str, dict[str, Organization]
        ] = {}  # tenant_id -> {org_id -> org}

    def create_org(self, tenant_id: str, org: Organization) -> None:
        """Register an organization for a tenant."""
        if tenant_id not in self._orgs:
            self._orgs[tenant_id] = {}
        self._orgs[tenant_id][org.org_id] = org
        logger.info(f"Registered org {org.org_id} for tenant {tenant_id}")

    def get_org(self, tenant_id: str, org_id: str) -> Optional[Organization]:
        """Get an org, enforcing tenant isolation."""
        return self._orgs.get(tenant_id, {}).get(org_id)

    def list_orgs(self, tenant_id: str) -> list[Organization]:
        """List all orgs for a tenant."""
        return list(self._orgs.get(tenant_id, {}).values())

    def remove_org(self, tenant_id: str, org_id: str) -> bool:
        """Remove an org (after stopping)."""
        tenant_orgs = self._orgs.get(tenant_id, {})
        if org_id in tenant_orgs:
            org = tenant_orgs.pop(org_id)
            org.stop()
            return True
        return False
