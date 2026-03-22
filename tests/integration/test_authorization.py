"""Authorization and tenant isolation integration tests.

Tests cross-tenant authorization bypasses to prevent vulnerabilities like:
- agency-os-cxs: Dashboard authorization bypass
- ZERA-138: Cross-tenant metering disclosure
- ZERA-166: Cross-tenant wallet access

Each test validates that Tenant A cannot access Tenant B's resources.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def two_tenant_clients():
    """Fixture providing two authenticated clients for different tenants."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    tenant_registry = app_module.tenant_registry

    # Register Tenant A
    tenant_a, api_key_a = tenant_registry.register(name="Tenant A Corp")
    tenant_a.metadata["stripe_customer_id"] = "cus_tenant_a"
    tenant_a.metadata["billing_status"] = "active"
    tenant_registry.save_metadata(tenant_a)

    # Register Tenant B
    tenant_b, api_key_b = tenant_registry.register(name="Tenant B Corp")
    tenant_b.metadata["stripe_customer_id"] = "cus_tenant_b"
    tenant_b.metadata["billing_status"] = "active"
    tenant_registry.save_metadata(tenant_b)

    # Create clients
    client_a = TestClient(app)
    client_a.headers["X-API-Key"] = api_key_a

    client_b = TestClient(app)
    client_b.headers["X-API-Key"] = api_key_b

    yield {
        "client_a": client_a,
        "client_b": client_b,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
    }

    os.unlink(db_path)


@pytest.fixture
def unauthed_client():
    """Fixture providing an unauthenticated client."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    yield TestClient(app)

    os.unlink(db_path)


class TestOrganizationListAuthorization:
    """Test that organization listing is scoped to the authenticated tenant."""

    def test_tenant_can_only_see_own_orgs(self, two_tenant_clients):
        """Tenant A should only see their own organizations, not Tenant B's."""
        client_a = two_tenant_clients["client_a"]
        client_b = two_tenant_clients["client_b"]

        # Tenant A creates an organization
        resp_a = client_a.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_a.status_code == 200
        org_a = resp_a.json()

        # Tenant B creates an organization
        resp_b = client_b.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_b.status_code == 200
        org_b = resp_b.json()

        # Tenant A lists organizations - should only see their own
        list_resp_a = client_a.get("/api/v1/orgs")
        assert list_resp_a.status_code == 200
        orgs_a = list_resp_a.json()
        assert len(orgs_a) == 1
        assert orgs_a[0]["org_id"] == org_a["org_id"]

        # Tenant B lists organizations - should only see their own
        list_resp_b = client_b.get("/api/v1/orgs")
        assert list_resp_b.status_code == 200
        orgs_b = list_resp_b.json()
        assert len(orgs_b) == 1
        assert orgs_b[0]["org_id"] == org_b["org_id"]

        # Verify no cross-tenant visibility
        org_a_ids = {org["org_id"] for org in orgs_a}
        org_b_ids = {org["org_id"] for org in orgs_b}
        assert org_a_ids.isdisjoint(org_b_ids), (
            "Tenant A should not see Tenant B's orgs"
        )


class TestOrganizationDetailAuthorization:
    """Test that org detail endpoints enforce ownership."""

    def test_tenant_cannot_access_other_tenant_org(self, two_tenant_clients):
        """Tenant A cannot access Tenant B's organization via GET /api/v1/orgs/{id}."""
        client_a = two_tenant_clients["client_a"]
        client_b = two_tenant_clients["client_b"]

        # Tenant B creates an organization
        resp_b = client_b.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_b.status_code == 200
        org_b = resp_b.json()
        org_b_id = org_b["org_id"]

        # Tenant A tries to access Tenant B's organization
        access_resp = client_a.get(f"/api/v1/orgs/{org_b_id}")

        # Should return 403 Forbidden (not 404 to avoid org ID enumeration)
        assert access_resp.status_code == 403
        error = access_resp.json()
        assert "detail" in error
        assert (
            "not found" in error["detail"].lower()
            or "forbidden" in error["detail"].lower()
        )

    def test_tenant_can_access_own_org(self, two_tenant_clients):
        """Tenant can access their own organization."""
        client_a = two_tenant_clients["client_a"]

        # Tenant A creates an organization
        resp_a = client_a.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_a.status_code == 200
        org_a = resp_a.json()
        org_a_id = org_a["org_id"]

        # Tenant A accesses their own organization
        access_resp = client_a.get(f"/api/v1/orgs/{org_a_id}")
        assert access_resp.status_code == 200
        org_data = access_resp.json()
        assert org_data["org_id"] == org_a_id


class TestOrganizationAgentsAuthorization:
    """Test that agent endpoints enforce org ownership."""

    def test_tenant_cannot_list_other_tenant_agents(self, two_tenant_clients):
        """Tenant A cannot list Tenant B's agents."""
        client_a = two_tenant_clients["client_a"]
        client_b = two_tenant_clients["client_b"]

        # Tenant B creates an organization
        resp_b = client_b.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_b.status_code == 200
        org_b = resp_b.json()
        org_b_id = org_b["org_id"]

        # Tenant A tries to list Tenant B's agents
        agents_resp = client_a.get(f"/api/v1/orgs/{org_b_id}/agents")

        # Should return 403 Forbidden
        assert agents_resp.status_code == 403

    def test_tenant_cannot_access_other_tenant_agent_details(self, two_tenant_clients):
        """Tenant A cannot access Tenant B's individual agent details."""
        client_a = two_tenant_clients["client_a"]
        client_b = two_tenant_clients["client_b"]

        # Tenant B creates an organization
        resp_b = client_b.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_b.status_code == 200
        org_b = resp_b.json()
        org_b_id = org_b["org_id"]

        # Get an agent ID from Tenant B's org
        agents_resp = client_b.get(f"/api/v1/orgs/{org_b_id}/agents")
        assert agents_resp.status_code == 200
        agents = agents_resp.json()
        assert len(agents) > 0
        agent_id = agents[0]["agent_id"]

        # Tenant A tries to access the agent
        agent_resp = client_a.get(f"/api/v1/orgs/{org_b_id}/agents/{agent_id}")

        # Should return 403 Forbidden
        assert agent_resp.status_code == 403


class TestUnauthenticatedAccess:
    """Test that unauthenticated requests are properly rejected."""

    def test_unauthenticated_org_list(self, unauthed_client):
        """Unauthenticated requests to list orgs return 401."""
        resp = unauthed_client.get("/api/v1/orgs")
        assert resp.status_code == 401

    def test_unauthenticated_org_detail(self, unauthed_client):
        """Unauthenticated requests to org details return 401."""
        resp = unauthed_client.get("/api/v1/orgs/fake-org-id")
        assert resp.status_code == 401

    def test_unauthenticated_org_create(self, unauthed_client):
        """Unauthenticated requests to create orgs return 401."""
        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "agency-basic"}
        )
        assert resp.status_code == 401


class TestInvalidOrgIdHandling:
    """Test proper error handling for invalid org IDs."""

    def test_nonexistent_org_returns_403(self, two_tenant_clients):
        """Accessing a non-existent org ID returns 403 (not 404 to avoid enumeration)."""
        client_a = two_tenant_clients["client_a"]

        # Try to access a non-existent org
        resp = client_a.get("/api/v1/orgs/nonexistent-org-id-12345")

        # Should return 403 Forbidden (not 404)
        assert resp.status_code == 403

    def test_malformed_org_id_returns_403_or_422(self, two_tenant_clients):
        """Malformed org IDs are handled gracefully."""
        client_a = two_tenant_clients["client_a"]

        # Try various malformed IDs
        malformed_ids = [
            " ",  # Blank-ish
            "../../../etc/passwd",  # Path traversal attempt
            "'; DROP TABLE orgs; --",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
        ]

        for bad_id in malformed_ids:
            resp = client_a.get(f"/api/v1/orgs/{bad_id}")
            # Should be rejected with 403, 404, or 422
            assert resp.status_code in [403, 404, 422], (
                f"Bad ID '{bad_id}' got unexpected status {resp.status_code}"
            )


class TestCrossResourceAuthorization:
    """Test authorization across different resource types (agents, tasks, wallets)."""

    def test_tenant_cannot_access_other_tenant_task_history(self, two_tenant_clients):
        """Tenant A cannot access Tenant B's task history."""
        client_a = two_tenant_clients["client_a"]
        client_b = two_tenant_clients["client_b"]

        # Tenant B creates an organization
        resp_b = client_b.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_b.status_code == 200
        org_b = resp_b.json()
        org_b_id = org_b["org_id"]

        # Tenant A tries to access Tenant B's org tasks endpoint
        tasks_resp = client_a.get(f"/api/v1/orgs/{org_b_id}/tasks")

        # Should return 403 Forbidden
        assert tasks_resp.status_code == 403

    def test_tenant_can_access_own_task_history(self, two_tenant_clients):
        """Tenant can access their own task history."""
        client_a = two_tenant_clients["client_a"]

        # Tenant A creates an organization
        resp_a = client_a.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp_a.status_code == 200
        org_a = resp_a.json()
        org_a_id = org_a["org_id"]

        # Tenant A accesses their own tasks
        tasks_resp = client_a.get(f"/api/v1/orgs/{org_a_id}/tasks")

        # Should succeed (even if empty)
        assert tasks_resp.status_code == 200
