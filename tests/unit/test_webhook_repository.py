"""Unit tests for WebhookRepository."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from sqlalchemy import insert, select

from agency_os import models
from agency_os.service.webhook_repository import WebhookRepository
from agency_os.service.webhooks import WebhookDispatcher
from agency_os.storage import Database
from agency_os.tenancy.secrets import SecretStore


@pytest.fixture()
def db_conn():
    """Create a temp SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)

    # Create test tenants
    db.save_tenant(
        {
            "tenant_id": "tenant-1",
            "name": "Test Corp 1",
            "api_key_hash": "hash1",
            "active": True,
            "metadata": "{}",
            "created_at": "2026-01-01T00:00:00Z",
        }
    )
    db.save_tenant(
        {
            "tenant_id": "tenant-2",
            "name": "Test Corp 2",
            "api_key_hash": "hash2",
            "active": True,
            "metadata": "{}",
            "created_at": "2026-01-01T00:00:00Z",
        }
    )

    yield db
    db.close()
    os.unlink(db_path)


def _fetchone(db: Database, stmt):
    with db._engine.connect() as conn:
        return conn.execute(stmt).fetchone()


def _execute(db: Database, stmt):
    with db._engine.begin() as conn:
        conn.execute(stmt)
        return None


@pytest.fixture()
def secret_store():
    """Create a secret store with a test key."""
    return SecretStore(master_key="test-master-key-32-bytes-long!!")


@pytest.fixture()
def dispatcher():
    """Create a webhook dispatcher in test mode."""
    return WebhookDispatcher(live_mode=False)


@pytest.fixture()
def repository(db_conn, dispatcher, secret_store):
    """Create a webhook repository."""
    return WebhookRepository(db_conn, dispatcher, secret_store)


class TestCreate:
    def test_create_webhook(self, repository):
        result = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed", "budget.alert"],
        )

        assert result["id"]
        assert result["url"] == "https://example.com/webhook"
        assert result["events"] == ["task.completed", "budget.alert"]
        assert result["secret"]  # Secret returned on creation
        assert len(result["secret"]) > 20  # Should be a secure token
        assert result["created_at"]

    def test_create_stores_encrypted_secret(self, repository, db_conn):
        result = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        # Check database
        row = _fetchone(
            db_conn,
            select(models.webhooks.c.secret_encrypted).where(
                models.webhooks.c.id == result["id"]
            ),
        )

        assert row.secret_encrypted != result["secret"]  # Should be encrypted
        assert row.secret_encrypted.startswith("gAAAAA")  # Fernet token format

    def test_create_syncs_to_dispatcher(self, repository, dispatcher):
        repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        # Check dispatcher has subscription
        subs = dispatcher._subscriptions.get("tenant-1", [])
        assert len(subs) == 1
        assert subs[0].url == "https://example.com/webhook"
        assert subs[0].events == ["task.completed"]

    def test_create_with_custom_secret(self, repository):
        result = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
            secret="my-custom-secret",
        )

        assert result["secret"] == "my-custom-secret"


class TestList:
    def test_list_empty(self, repository):
        result = repository.list("tenant-1")
        assert result == []

    def test_list_webhooks(self, repository):
        # Create two webhooks
        repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook1",
            events=["task.completed"],
        )
        repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook2",
            events=["budget.alert"],
        )

        result = repository.list("tenant-1")
        assert len(result) == 2

        # Check secrets are NOT returned
        for item in result:
            assert "secret" not in item
            assert "secret_encrypted" not in item

    def test_list_filters_by_tenant(self, repository):
        repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook1",
            events=["task.completed"],
        )
        repository.create(
            tenant_id="tenant-2",
            url="https://example.com/webhook2",
            events=["task.completed"],
        )

        result = repository.list("tenant-1")
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/webhook1"


class TestGet:
    def test_get_webhook(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        result = repository.get(created["id"], "tenant-1")
        assert result["id"] == created["id"]
        assert result["url"] == "https://example.com/webhook"
        assert "secret" not in result  # Not returned

    def test_get_nonexistent(self, repository):
        result = repository.get("fake-id", "tenant-1")
        assert result is None

    def test_get_wrong_tenant(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        result = repository.get(created["id"], "tenant-2")
        assert result is None


class TestDelete:
    def test_delete_webhook(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        success = repository.delete(created["id"], "tenant-1")
        assert success is True

        # Verify deleted
        result = repository.get(created["id"], "tenant-1")
        assert result is None

    def test_delete_syncs_to_dispatcher(self, repository, dispatcher):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        repository.delete(created["id"], "tenant-1")

        # Check dispatcher no longer has subscription
        subs = dispatcher._subscriptions.get("tenant-1", [])
        assert len(subs) == 0

    def test_delete_nonexistent(self, repository):
        success = repository.delete("fake-id", "tenant-1")
        assert success is False

    def test_delete_wrong_tenant(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        success = repository.delete(created["id"], "tenant-2")
        assert success is False


class TestRotateSecret:
    def test_rotate_secret(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )
        original_secret = created["secret"]

        result = repository.rotate_secret(created["id"], "tenant-1")
        assert result["id"] == created["id"]
        assert result["secret"] != original_secret  # New secret
        assert len(result["secret"]) > 20
        assert result["rotated_at"]

    def test_rotate_updates_database(self, repository, db_conn, secret_store):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        rotated = repository.rotate_secret(created["id"], "tenant-1")

        # Check database
        row = _fetchone(
            db_conn,
            select(
                models.webhooks.c.secret_encrypted, models.webhooks.c.rotated_at
            ).where(models.webhooks.c.id == created["id"]),
        )

        # Decrypt and verify it matches the returned secret
        decrypted = secret_store._decrypt(row.secret_encrypted, "tenant-1")
        assert decrypted == rotated["secret"]
        assert row.rotated_at is not None

    def test_rotate_syncs_to_dispatcher(self, repository, dispatcher):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        rotated = repository.rotate_secret(created["id"], "tenant-1")

        # Check dispatcher has updated secret
        subs = dispatcher._subscriptions.get("tenant-1", [])
        assert len(subs) == 1
        assert subs[0].secret == rotated["secret"]

    def test_rotate_nonexistent(self, repository):
        result = repository.rotate_secret("fake-id", "tenant-1")
        assert result is None

    def test_rotate_wrong_tenant(self, repository):
        created = repository.create(
            tenant_id="tenant-1",
            url="https://example.com/webhook",
            events=["task.completed"],
        )

        result = repository.rotate_secret(created["id"], "tenant-2")
        assert result is None


class TestLoadAll:
    def test_load_all_empty(self, repository, dispatcher):
        repository.load_all()
        assert len(dispatcher._subscriptions) == 0

    def test_load_all_webhooks(self, repository, db_conn, dispatcher):
        # Insert webhooks directly into database
        secret_store = SecretStore(master_key="test-master-key-32-bytes-long!!")

        _execute(
            db_conn,
            insert(models.webhooks).values(
                id="wh-1",
                tenant_id="tenant-1",
                url="https://example.com/webhook1",
                events=json.dumps(["task.completed"]),
                secret_encrypted=secret_store._encrypt("secret-1", "tenant-1"),
                created_at="2026-01-01T00:00:00Z",
                rotated_at=None,
            ),
        )
        _execute(
            db_conn,
            insert(models.webhooks).values(
                id="wh-2",
                tenant_id="tenant-2",
                url="https://example.com/webhook2",
                events=json.dumps(["budget.alert"]),
                secret_encrypted=secret_store._encrypt("secret-2", "tenant-2"),
                created_at="2026-01-01T00:00:00Z",
                rotated_at=None,
            ),
        )

        # Load into dispatcher
        repository.load_all()

        # Check dispatcher
        assert len(dispatcher._subscriptions) == 2
        assert len(dispatcher._subscriptions["tenant-1"]) == 1
        assert (
            dispatcher._subscriptions["tenant-1"][0].url
            == "https://example.com/webhook1"
        )
        assert dispatcher._subscriptions["tenant-1"][0].secret == "secret-1"

        assert len(dispatcher._subscriptions["tenant-2"]) == 1
        assert (
            dispatcher._subscriptions["tenant-2"][0].url
            == "https://example.com/webhook2"
        )
        assert dispatcher._subscriptions["tenant-2"][0].secret == "secret-2"
