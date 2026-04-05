"""Tests for tenancy/secrets.py — per-tenant encrypted secret storage."""

from __future__ import annotations

import pytest

from agency_os.tenancy.secrets import SecretStore

MASTER_KEY = "test-master-key-for-unit-tests-only"


@pytest.fixture
def store():
    return SecretStore(master_key=MASTER_KEY)


class TestSecretStoreInit:
    def test_init_with_master_key(self):
        store = SecretStore(master_key=MASTER_KEY)
        assert store is not None

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", MASTER_KEY)
        store = SecretStore()
        assert store is not None

    def test_init_no_key_raises(self, monkeypatch):
        monkeypatch.delenv("AGENCY_OS_SECRET_KEY", raising=False)
        with pytest.raises(ValueError, match="No encryption key"):
            SecretStore()


class TestSecretCRUD:
    def test_set_and_get(self, store):
        store.set_secret("tenant-1", "api_key", "sk-secret-123")
        assert store.get_secret("tenant-1", "api_key") == "sk-secret-123"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_secret("tenant-1", "missing") is None

    def test_get_nonexistent_tenant_returns_none(self, store):
        assert store.get_secret("no-such-tenant", "key") is None

    def test_overwrite_secret(self, store):
        store.set_secret("t1", "key", "value1")
        store.set_secret("t1", "key", "value2")
        assert store.get_secret("t1", "key") == "value2"

    def test_delete_secret(self, store):
        store.set_secret("t1", "key", "value")
        assert store.delete_secret("t1", "key") is True
        assert store.get_secret("t1", "key") is None

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete_secret("t1", "missing") is False

    def test_delete_nonexistent_tenant_returns_false(self, store):
        assert store.delete_secret("no-tenant", "key") is False

    def test_list_keys(self, store):
        store.set_secret("t1", "key_a", "val")
        store.set_secret("t1", "key_b", "val")
        keys = store.list_keys("t1")
        assert sorted(keys) == ["key_a", "key_b"]

    def test_list_keys_empty_tenant(self, store):
        assert store.list_keys("no-tenant") == []


class TestTenantIsolation:
    def test_secrets_isolated_between_tenants(self, store):
        store.set_secret("tenant-a", "shared_key", "value-a")
        store.set_secret("tenant-b", "shared_key", "value-b")
        assert store.get_secret("tenant-a", "shared_key") == "value-a"
        assert store.get_secret("tenant-b", "shared_key") == "value-b"

    def test_tenant_cannot_read_other_tenants_secret(self, store):
        store.set_secret("tenant-a", "private", "secret")
        assert store.get_secret("tenant-b", "private") is None

    def test_delete_does_not_affect_other_tenant(self, store):
        store.set_secret("tenant-a", "key", "val-a")
        store.set_secret("tenant-b", "key", "val-b")
        store.delete_secret("tenant-a", "key")
        assert store.get_secret("tenant-b", "key") == "val-b"


class TestEncryptionProperties:
    def test_stored_value_is_encrypted(self, store):
        store.set_secret("t1", "key", "plaintext-secret")
        raw = store._stores["t1"]["key"]
        assert raw != "plaintext-secret"
        assert "plaintext" not in raw

    def test_different_tenants_produce_different_ciphertexts(self, store):
        store.set_secret("tenant-a", "key", "same-value")
        store.set_secret("tenant-b", "key", "same-value")
        cipher_a = store._stores["tenant-a"]["key"]
        cipher_b = store._stores["tenant-b"]["key"]
        assert cipher_a != cipher_b

    def test_derived_keys_differ_per_tenant(self, store):
        key_a = store._derive_fernet_key("tenant-a")
        key_b = store._derive_fernet_key("tenant-b")
        assert key_a != key_b

    def test_derived_key_is_deterministic(self, store):
        k1 = store._derive_fernet_key("tenant-x")
        k2 = store._derive_fernet_key("tenant-x")
        assert k1 == k2

    def test_roundtrip_unicode(self, store):
        store.set_secret("t1", "emoji", "secret-\u2603-\U0001f680")
        assert store.get_secret("t1", "emoji") == "secret-\u2603-\U0001f680"

    def test_roundtrip_empty_string(self, store):
        store.set_secret("t1", "empty", "")
        assert store.get_secret("t1", "empty") == ""
