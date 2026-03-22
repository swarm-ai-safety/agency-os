"""Tests for BYOK (Bring Your Own Key) tenant provider key functionality."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from agency_os.gateway.providers.base import (
    CompletionResult,
    TokenUsage,
)
from agency_os.gateway.providers.registry import ProviderRegistry
from agency_os.tenancy.provider_keys import (
    TenantProviderKeyStore,
    _key_fingerprint,
)
from agency_os.tenancy.secrets import SecretStore

# ------------------------------------------------------------------
# Unit tests: TenantProviderKeyStore
# ------------------------------------------------------------------


class TestTenantProviderKeyStore:
    @pytest.fixture()
    def store(self, monkeypatch):
        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "test-master-key-byok")
        from agency_os.service.api import app as app_module

        app_module.create_app()
        db = app_module.db
        secret_store = SecretStore(master_key="test-master-key-byok")
        return TenantProviderKeyStore(db, secret_store), db

    def test_set_and_get_key_roundtrip(self, store):
        key_store, _ = store
        fingerprint = key_store.set_key("tenant-1", "openai", "sk-test-123")
        assert fingerprint == _key_fingerprint("sk-test-123")

        decrypted = key_store.get_key("tenant-1", "openai")
        assert decrypted == "sk-test-123"

    def test_get_key_returns_none_when_not_set(self, store):
        key_store, _ = store
        assert key_store.get_key("tenant-1", "openai") is None

    def test_overwrite_key(self, store):
        key_store, _ = store
        key_store.set_key("tenant-1", "openai", "sk-old")
        key_store.set_key("tenant-1", "openai", "sk-new")
        assert key_store.get_key("tenant-1", "openai") == "sk-new"

    def test_delete_key(self, store):
        key_store, _ = store
        key_store.set_key("tenant-1", "anthropic", "sk-ant-123")
        assert key_store.delete_key("tenant-1", "anthropic") is True
        assert key_store.get_key("tenant-1", "anthropic") is None

    def test_delete_nonexistent_key_returns_false(self, store):
        key_store, _ = store
        assert key_store.delete_key("tenant-1", "openai") is False

    def test_list_providers(self, store):
        key_store, _ = store
        key_store.set_key("tenant-1", "openai", "sk-oa")
        key_store.set_key("tenant-1", "anthropic", "sk-ant")

        providers = key_store.list_providers("tenant-1")
        names = [p["provider"] for p in providers]
        assert "anthropic" in names
        assert "openai" in names
        for p in providers:
            assert "key_fingerprint" in p
            assert "created_at" in p
            assert "updated_at" in p

    def test_has_key(self, store):
        key_store, _ = store
        assert key_store.has_key("tenant-1", "openai") is False
        key_store.set_key("tenant-1", "openai", "sk-test")
        assert key_store.has_key("tenant-1", "openai") is True

    def test_tenant_isolation(self, store):
        """Tenant A cannot see tenant B's keys."""
        key_store, _ = store
        key_store.set_key("tenant-a", "openai", "sk-a-secret")
        key_store.set_key("tenant-b", "openai", "sk-b-secret")

        assert key_store.get_key("tenant-a", "openai") == "sk-a-secret"
        assert key_store.get_key("tenant-b", "openai") == "sk-b-secret"
        assert key_store.list_providers("tenant-a") != key_store.list_providers(
            "tenant-b"
        )

    def test_unsupported_provider_raises(self, store):
        key_store, _ = store
        with pytest.raises(ValueError, match="Unsupported provider"):
            key_store.set_key("tenant-1", "fake_provider", "sk-test")

    def test_empty_key_raises(self, store):
        key_store, _ = store
        with pytest.raises(ValueError, match="api_key must not be empty"):
            key_store.set_key("tenant-1", "openai", "   ")

    def test_provider_name_normalized(self, store):
        key_store, _ = store
        key_store.set_key("tenant-1", "  OpenAI  ", "sk-test")
        assert key_store.get_key("tenant-1", "openai") == "sk-test"


# ------------------------------------------------------------------
# Unit tests: ProviderRegistry.create_with_key
# ------------------------------------------------------------------


class TestProviderRegistryCreateWithKey:
    def test_create_openai_provider_with_key(self):
        registry = ProviderRegistry()
        provider = registry.create_with_key("openai", "sk-test-key")
        assert provider is not None
        assert provider._api_key == "sk-test-key"

    def test_create_anthropic_provider_with_key(self):
        registry = ProviderRegistry()
        provider = registry.create_with_key("anthropic", "sk-ant-test")
        assert provider is not None
        assert provider._api_key == "sk-ant-test"

    def test_create_unknown_provider_returns_none(self):
        registry = ProviderRegistry()
        assert registry.create_with_key("unknown_provider", "key") is None

    def test_created_provider_is_not_cached(self):
        registry = ProviderRegistry()
        p1 = registry.create_with_key("openai", "sk-key-1")
        p2 = registry.create_with_key("openai", "sk-key-2")
        assert p1 is not p2
        assert p1._api_key != p2._api_key
        # Shared cache should be empty
        assert len(registry._providers) == 0


# ------------------------------------------------------------------
# API integration tests: BYOK CRUD endpoints
# ------------------------------------------------------------------


class TestBYOKEndpoints:
    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "test-byok-secret")
        from agency_os.service.api import app as app_module

        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="BYOK Test Tenant")
        tenant.metadata["stripe_customer_id"] = "cus_byok_test"
        tenant.metadata["billing_status"] = "active"
        app_module.tenant_registry.save_metadata(tenant)
        return TestClient(app), tenant, api_key

    def test_put_provider_key(self, client):
        test_client, tenant, api_key = client
        resp = test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-byok-test-123"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stored"
        assert data["provider"] == "openai"
        assert data["key_fingerprint"] == _key_fingerprint("sk-byok-test-123")

    def test_list_provider_keys(self, client):
        test_client, tenant, api_key = client
        # Store a key first
        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-byok-test-456"},
            headers={"X-API-Key": api_key},
        )

        resp = test_client.get(
            "/api/v1/gateway/provider-keys",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        keys = resp.json()["data"]
        assert len(keys) == 1
        assert keys[0]["provider"] == "openai"
        assert "key_fingerprint" in keys[0]

    def test_delete_provider_key(self, client):
        test_client, tenant, api_key = client
        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-byok-delete-me"},
            headers={"X-API-Key": api_key},
        )

        resp = test_client.delete(
            "/api/v1/gateway/provider-keys/openai",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        list_resp = test_client.get(
            "/api/v1/gateway/provider-keys",
            headers={"X-API-Key": api_key},
        )
        assert len(list_resp.json()["data"]) == 0

    def test_delete_nonexistent_key_returns_404(self, client):
        test_client, tenant, api_key = client
        resp = test_client.delete(
            "/api/v1/gateway/provider-keys/openai",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 404

    def test_put_unsupported_provider_returns_400(self, client):
        test_client, tenant, api_key = client
        resp = test_client.put(
            "/api/v1/gateway/provider-keys/fake_provider",
            json={"api_key": "sk-test"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 400

    def test_put_empty_key_returns_422(self, client):
        test_client, tenant, api_key = client
        resp = test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": ""},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_audit_log_on_set_key(self, client):
        test_client, tenant, api_key = client
        from agency_os.service.api import app as app_module

        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-audit-test"},
            headers={"X-API-Key": api_key},
        )

        audit_logs = app_module.db.get_audit_log(limit=10)
        byok_logs = [
            log for log in audit_logs if log.get("action") == "byok.provider_key.set"
        ]
        assert len(byok_logs) >= 1
        detail = json.loads(byok_logs[0]["detail"])
        assert detail["provider"] == "openai"
        assert detail["key_fingerprint"] == _key_fingerprint("sk-audit-test")

    def test_audit_log_on_delete_key(self, client):
        test_client, tenant, api_key = client
        from agency_os.service.api import app as app_module

        test_client.put(
            "/api/v1/gateway/provider-keys/anthropic",
            json={"api_key": "sk-delete-audit"},
            headers={"X-API-Key": api_key},
        )
        test_client.delete(
            "/api/v1/gateway/provider-keys/anthropic",
            headers={"X-API-Key": api_key},
        )

        audit_logs = app_module.db.get_audit_log(limit=10)
        delete_logs = [
            log
            for log in audit_logs
            if log.get("action") == "byok.provider_key.deleted"
        ]
        assert len(delete_logs) >= 1


# ------------------------------------------------------------------
# Integration test: BYOK routing + zero-markup billing
# ------------------------------------------------------------------


class TestBYOKRoutingFlow:
    @pytest.fixture()
    def setup(self, monkeypatch):
        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "test-byok-routing")
        from agency_os.service.api import app as app_module
        from agency_os.service.api.routers import gateway

        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="BYOK Routing Test")
        tenant.metadata["stripe_customer_id"] = "cus_byok_route"
        tenant.metadata["billing_status"] = "active"
        tenant.metadata["budget_limit_usd"] = 100.0
        tenant.metadata["total_spent_usd"] = 0.0
        app_module.tenant_registry.save_metadata(tenant)

        # Mock provider
        mock_provider = AsyncMock()
        mock_provider.chat_completion = AsyncMock(
            return_value=CompletionResult(
                content="BYOK response",
                model="gpt-4o",
                finish_reason="stop",
                usage=TokenUsage(
                    prompt_tokens=10, completion_tokens=5, total_tokens=15
                ),
            )
        )

        mock_registry = MagicMock(spec=ProviderRegistry)
        mock_registry.get.return_value = mock_provider
        mock_registry.create_with_key.return_value = mock_provider
        gateway.set_provider_registry(mock_registry)

        return TestClient(app), tenant, api_key, mock_registry, app_module

    def test_byok_request_uses_tenant_key(self, setup):
        """When tenant has a BYOK key, create_with_key is called instead of get."""
        test_client, tenant, api_key, mock_registry, app_module = setup

        # Store a BYOK key for this tenant
        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-tenant-own-key"},
            headers={"X-API-Key": api_key},
        )

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        # Verify create_with_key was called (BYOK path)
        mock_registry.create_with_key.assert_called()
        call_args = mock_registry.create_with_key.call_args
        assert call_args[0][0] == "openai"  # provider name
        assert call_args[0][1] == "sk-tenant-own-key"  # tenant's key

    def test_byok_zero_budget_impact(self, setup):
        """BYOK requests should not increase total_spent_usd."""
        test_client, tenant, api_key, mock_registry, app_module = setup

        # Store a BYOK key
        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-tenant-free"},
            headers={"X-API-Key": api_key},
        )

        initial_spent = float(tenant.metadata.get("total_spent_usd", 0.0))

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200

        # Budget should not have increased
        final_spent = float(tenant.metadata.get("total_spent_usd", 0.0))
        assert final_spent == initial_spent

    def test_byok_zero_cost_in_gateway_log(self, setup):
        """BYOK requests should log zero costs."""
        test_client, tenant, api_key, mock_registry, app_module = setup

        test_client.put(
            "/api/v1/gateway/provider-keys/openai",
            json={"api_key": "sk-zero-cost"},
            headers={"X-API-Key": api_key},
        )

        test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )

        # Check gateway request log
        requests = app_module.db.get_gateway_requests(tenant.tenant_id, limit=1)
        assert len(requests) >= 1
        req = requests[0]
        assert float(req["provider_cost"]) == 0.0
        assert float(req["customer_cost"]) == 0.0
        assert float(req["margin"]) == 0.0

    def test_non_byok_request_has_normal_cost(self, setup):
        """Without BYOK key, normal cost tracking applies."""
        test_client, tenant, api_key, mock_registry, app_module = setup

        # No BYOK key stored — should use platform provider
        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200

        # create_with_key should NOT have been called (no tenant key)
        mock_registry.create_with_key.assert_not_called()
        # get should have been called (platform key path)
        mock_registry.get.assert_called()
