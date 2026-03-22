"""Tests for free tier enforcement in auth middleware."""

import pytest

from agency_os.service.api.middleware.auth import (
    FREE_DEMO_MAX_RUNS,
    FREE_TIER_AGENT_LIMIT,
    _check_free_tier_quota,
    record_free_tier_usage,
)
from agency_os.tenancy.tenant import Tenant


def _make_tenant(**metadata_overrides) -> Tenant:
    return Tenant(
        tenant_id="tenant-test",
        name="Test Corp",
        api_key="ak-test",
        metadata=metadata_overrides,
    )


class TestFreeTierConstants:
    def test_demo_limit_is_one_run(self):
        assert FREE_DEMO_MAX_RUNS == 1

    def test_agent_limit_is_1(self):
        assert FREE_TIER_AGENT_LIMIT == 1


class TestFreeTierQuota:
    def test_new_tenant_passes(self):
        """Brand-new tenant with no usage should pass quota check."""
        tenant = _make_tenant()
        # Should not raise
        _check_free_tier_quota(tenant)

    def test_zero_demo_runs_passes(self):
        tenant = _make_tenant(free_demo_runs_used=0)
        _check_free_tier_quota(tenant)

    def test_at_limit_raises_402(self):
        tenant = _make_tenant(free_demo_runs_used=FREE_DEMO_MAX_RUNS)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_free_tier_quota(tenant)
        assert exc_info.value.status_code == 402
        assert "Free demo already used" in exc_info.value.detail

    def test_over_limit_raises_402(self):
        tenant = _make_tenant(free_demo_runs_used=FREE_DEMO_MAX_RUNS + 1)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_free_tier_quota(tenant)
        assert exc_info.value.status_code == 402


class TestRecordFreeTierUsage:
    def test_increments_demo_runs(self):
        tenant = _make_tenant()
        record_free_tier_usage(tenant, 500)
        assert tenant.metadata["free_demo_runs_used"] == 1
        assert tenant.metadata["free_demo_completed"] is True

        record_free_tier_usage(tenant, 300)
        assert tenant.metadata["free_demo_runs_used"] == 2
        assert tenant.metadata["free_demo_completed"] is True

    def test_skips_paid_tenants(self):
        tenant = _make_tenant(billing_status="active")
        record_free_tier_usage(tenant, 500)
        assert "free_demo_runs_used" not in tenant.metadata

    def test_skips_non_free_tier(self):
        tenant = _make_tenant(tier="professional")
        record_free_tier_usage(tenant, 500)
        assert "free_demo_runs_used" not in tenant.metadata


class TestRequireActiveBillingIntegration:
    """Test the full require_active_billing dependency via TestClient."""

    @pytest.fixture
    def app_and_registry(self):
        from agency_os.service.api import app as app_module

        app = app_module.create_app()
        return app, app_module.tenant_registry

    def test_free_tier_tenant_can_access(self, app_and_registry):
        from starlette.testclient import TestClient

        app, registry = app_and_registry
        tenant, api_key = registry.register(name="Free User")
        # No billing_status, no stripe_customer_id — pure free tier
        client = TestClient(app)
        client.headers["X-API-Key"] = api_key

        # Should be able to hit org creation (no longer 402)
        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 200

    def test_free_tier_tenant_after_demo_is_blocked(self, app_and_registry):
        from starlette.testclient import TestClient

        app, registry = app_and_registry
        tenant, api_key = registry.register(name="Demo Complete User")
        tenant.metadata["free_demo_runs_used"] = 1
        tenant.metadata["free_demo_completed"] = True
        registry.save_metadata(tenant)

        client = TestClient(app)
        client.headers["X-API-Key"] = api_key

        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 402

    def test_past_due_tenant_blocked(self, app_and_registry):
        from starlette.testclient import TestClient

        app, registry = app_and_registry
        tenant, api_key = registry.register(name="Past Due Corp")
        tenant.metadata["stripe_customer_id"] = "cus_test"
        tenant.metadata["billing_status"] = "past_due"
        registry.save_metadata(tenant)

        client = TestClient(app)
        client.headers["X-API-Key"] = api_key

        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 402

    def test_no_subscription_tenant_blocked(self, app_and_registry):
        from starlette.testclient import TestClient

        app, registry = app_and_registry
        tenant, api_key = registry.register(name="Setup Incomplete")
        tenant.metadata["stripe_customer_id"] = "cus_test"
        tenant.metadata["billing_status"] = "incomplete"
        registry.save_metadata(tenant)

        client = TestClient(app)
        client.headers["X-API-Key"] = api_key

        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 402
