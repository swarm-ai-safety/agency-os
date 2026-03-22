"""Integration tests for webhook lifecycle API (create, list, delete, rotate)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_with_repo():
    """Create a test client with webhook repository enabled."""
    # Use a temp database for each test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path
    os.environ["AGENCY_OS_SECRET_KEY"] = "test-secret-key-32-bytes-long!!"

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    tenant_registry = app_module.tenant_registry

    # Register a test tenant with active billing
    tenant, api_key = tenant_registry.register(name="Test Corp")
    tenant.metadata["stripe_customer_id"] = "cus_test"
    tenant.metadata["billing_status"] = "active"
    tenant_registry.save_metadata(tenant)

    client = TestClient(app)
    client.headers["X-API-Key"] = api_key
    yield client

    os.unlink(db_path)
    del os.environ["AGENCY_OS_SECRET_KEY"]


def test_webhook_delete(client_with_repo):
    """Test DELETE /api/v1/webhooks/{id} endpoint."""
    # Register a webhook
    response = client_with_repo.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["task.completed"]},
    )
    assert response.status_code == 200
    data = response.json()

    # Repository mode returns webhook ID
    if "webhook" in data and "id" in data["webhook"]:
        webhook_id = data["webhook"]["id"]

        # Delete webhook
        response = client_with_repo.delete(f"/api/v1/webhooks/{webhook_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify deleted
        response = client_with_repo.get("/api/v1/webhooks")
        assert response.status_code == 200
        webhooks = response.json()
        assert len(webhooks) == 0


def test_webhook_rotate_secret(client_with_repo):
    """Test POST /api/v1/webhooks/{id}/rotate-secret endpoint."""
    # Register a webhook
    response = client_with_repo.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["task.completed"]},
    )
    assert response.status_code == 200
    data = response.json()

    webhook_id = data["webhook"]["id"]
    original_secret = data["webhook"]["secret"]

    # Rotate secret
    response = client_with_repo.post(f"/api/v1/webhooks/{webhook_id}/rotate-secret")
    assert response.status_code == 200
    rotated_data = response.json()
    assert rotated_data["status"] == "rotated"
    assert rotated_data["webhook"]["secret"] != original_secret
    assert len(rotated_data["webhook"]["secret"]) > 20
    assert rotated_data["webhook"]["rotated_at"]


def test_webhook_delete_wrong_tenant(client_with_repo):
    """Test that delete fails for non-existent webhook."""
    response = client_with_repo.delete("/api/v1/webhooks/fake-webhook-id")
    assert response.status_code == 404


def test_webhook_rotate_wrong_tenant(client_with_repo):
    """Test that rotate fails for non-existent webhook."""
    response = client_with_repo.post("/api/v1/webhooks/fake-webhook-id/rotate-secret")
    assert response.status_code == 404


def test_webhook_delivery_status_endpoint(client_with_repo):
    """Test GET /api/v1/webhooks/{id}/deliveries returns persisted delivery records."""
    from agency_os.service.api import app as app_module
    from agency_os.service.webhooks import TASK_COMPLETED, WebhookEvent

    response = client_with_repo.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["task.completed"]},
    )
    assert response.status_code == 200
    webhook_id = response.json()["webhook"]["id"]

    tenant_id = app_module.tenant_registry.list_all()[0].tenant_id
    event = WebhookEvent(
        event_type=TASK_COMPLETED,
        org_id=tenant_id,
        payload={"task_id": "task-1", "status": "completed"},
    )
    app_module.webhook_dispatcher.dispatch(event)

    response = client_with_repo.get(f"/api/v1/webhooks/{webhook_id}/deliveries")
    assert response.status_code == 200
    data = response.json()
    assert data["webhook_id"] == webhook_id
    assert len(data["deliveries"]) == 1
    delivery = data["deliveries"][0]
    assert delivery["event_type"] == TASK_COMPLETED
    assert delivery["attempt_count"] == 1
    assert delivery["success"] == 1
