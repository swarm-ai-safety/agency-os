"""Tests for tenancy/isolation.py — per-tenant organization isolation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agency_os.tenancy.isolation import OrgIsolator


def _make_org(org_id: str = "org-test") -> MagicMock:
    """Create a mock Organization with the required attributes."""
    org = MagicMock()
    org.org_id = org_id
    return org


@pytest.fixture
def isolator():
    return OrgIsolator()


class TestCreateOrg:
    def test_create_single_org(self, isolator):
        org = _make_org("org-1")
        isolator.create_org("tenant-a", org)
        assert isolator.get_org("tenant-a", "org-1") is org

    def test_create_multiple_orgs_same_tenant(self, isolator):
        org1 = _make_org("org-1")
        org2 = _make_org("org-2")
        isolator.create_org("tenant-a", org1)
        isolator.create_org("tenant-a", org2)
        assert len(isolator.list_orgs("tenant-a")) == 2


class TestGetOrg:
    def test_get_existing_org(self, isolator):
        org = _make_org("org-1")
        isolator.create_org("tenant-a", org)
        assert isolator.get_org("tenant-a", "org-1") is org

    def test_get_nonexistent_org_returns_none(self, isolator):
        assert isolator.get_org("tenant-a", "no-org") is None

    def test_get_nonexistent_tenant_returns_none(self, isolator):
        assert isolator.get_org("no-tenant", "org-1") is None


class TestTenantIsolation:
    def test_tenant_cannot_access_other_tenant_org(self, isolator):
        org = _make_org("org-1")
        isolator.create_org("tenant-a", org)
        assert isolator.get_org("tenant-b", "org-1") is None

    def test_same_org_id_different_tenants(self, isolator):
        org_a = _make_org("shared-id")
        org_b = _make_org("shared-id")
        isolator.create_org("tenant-a", org_a)
        isolator.create_org("tenant-b", org_b)
        assert isolator.get_org("tenant-a", "shared-id") is org_a
        assert isolator.get_org("tenant-b", "shared-id") is org_b

    def test_list_orgs_only_returns_own_tenant(self, isolator):
        isolator.create_org("tenant-a", _make_org("org-a"))
        isolator.create_org("tenant-b", _make_org("org-b"))
        orgs_a = isolator.list_orgs("tenant-a")
        assert len(orgs_a) == 1
        assert orgs_a[0].org_id == "org-a"


class TestListOrgs:
    def test_list_empty_tenant(self, isolator):
        assert isolator.list_orgs("no-tenant") == []

    def test_list_preserves_all_orgs(self, isolator):
        for i in range(5):
            isolator.create_org("t1", _make_org(f"org-{i}"))
        assert len(isolator.list_orgs("t1")) == 5


class TestRemoveOrg:
    def test_remove_existing_org(self, isolator):
        org = _make_org("org-1")
        isolator.create_org("tenant-a", org)
        assert isolator.remove_org("tenant-a", "org-1") is True
        assert isolator.get_org("tenant-a", "org-1") is None

    def test_remove_calls_stop(self, isolator):
        org = _make_org("org-1")
        isolator.create_org("tenant-a", org)
        isolator.remove_org("tenant-a", "org-1")
        org.stop.assert_called_once()

    def test_remove_nonexistent_returns_false(self, isolator):
        assert isolator.remove_org("tenant-a", "missing") is False

    def test_remove_does_not_affect_other_tenant(self, isolator):
        org_a = _make_org("org-1")
        org_b = _make_org("org-1")
        isolator.create_org("tenant-a", org_a)
        isolator.create_org("tenant-b", org_b)
        isolator.remove_org("tenant-a", "org-1")
        assert isolator.get_org("tenant-b", "org-1") is org_b
