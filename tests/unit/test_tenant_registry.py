"""Unit tests for TenantRegistry."""

import os
import tempfile

import pytest

from agency_os.storage import Database
from agency_os.tenancy.tenant import TenantRegistry


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    db.close()
    os.remove(path)


def test_register_creates_tenant_with_api_key(temp_db):
    """Test that register() creates a tenant and returns plaintext key."""
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    assert tenant.name == "test-tenant"
    assert tenant.active is True
    assert api_key.startswith("ak-")
    assert tenant.api_key != api_key  # Should be hashed in memory


def test_get_by_api_key_works_immediately_after_register(temp_db):
    """Test that API key lookup works right after registration."""
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    found = registry.get_by_api_key(api_key)
    assert found is not None
    assert found.tenant_id == tenant.tenant_id


def test_get_by_api_key_after_restart(temp_db):
    """Regression test for ZERA-118: API keys must work after restart."""
    # Register tenant
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    # Simulate restart by creating new registry from same DB
    registry2 = TenantRegistry(temp_db)
    found = registry2.get_by_api_key(api_key)

    assert found is not None
    assert found.tenant_id == tenant.tenant_id
    assert found.name == "test-tenant"


def test_save_metadata_preserves_api_key_hash(temp_db):
    """Regression test for ZERA-118: save_metadata must not double-hash."""
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    # Update metadata and persist
    tenant.metadata["foo"] = "bar"
    registry.save_metadata(tenant)

    # Key should still work in-memory
    found = registry.get_by_api_key(api_key)
    assert found is not None
    assert found.metadata["foo"] == "bar"

    # Key should still work after restart
    registry2 = TenantRegistry(temp_db)
    found2 = registry2.get_by_api_key(api_key)
    assert found2 is not None
    assert found2.metadata["foo"] == "bar"


def test_multiple_metadata_updates_preserve_api_key(temp_db):
    """Test that multiple metadata updates don't corrupt the API key hash."""
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    # Multiple metadata updates
    for i in range(5):
        tenant.metadata[f"key{i}"] = f"value{i}"
        registry.save_metadata(tenant)

    # Key should still work after multiple persists
    found = registry.get_by_api_key(api_key)
    assert found is not None
    assert found.metadata["key4"] == "value4"

    # And after restart
    registry2 = TenantRegistry(temp_db)
    found2 = registry2.get_by_api_key(api_key)
    assert found2 is not None
    assert len(found2.metadata) == 5


def test_deactivate_removes_from_key_index(temp_db):
    """Test that deactivating a tenant removes it from key index."""
    registry = TenantRegistry(temp_db)
    tenant, api_key = registry.register("test-tenant")

    # Deactivate
    result = registry.deactivate(tenant.tenant_id)
    assert result is True

    # Should not be found by API key
    found = registry.get_by_api_key(api_key)
    assert found is None

    # Should still exist in tenant list (but inactive)
    tenant_obj = registry.get(tenant.tenant_id)
    assert tenant_obj is not None
    assert tenant_obj.active is False


def test_invalid_api_key_returns_none(temp_db):
    """Test that invalid API keys return None."""
    registry = TenantRegistry(temp_db)
    registry.register("test-tenant")

    found = registry.get_by_api_key("ak-invalid-key")
    assert found is None
