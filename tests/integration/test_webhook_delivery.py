"""Integration test for webhook delivery infrastructure."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create a test client with a real app instance."""
    # Use a temp database for each test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

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


def test_webhook_dispatcher_initialized():
    """Verify that the webhook dispatcher singleton is initialized on app startup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app_module.create_app()

    # Check that the dispatcher was initialized
    assert app_module.webhook_dispatcher is not None
    assert not app_module.webhook_dispatcher.live_mode  # Test mode by default

    os.unlink(db_path)


def test_webhook_registration_returns_secret(client):
    """Verify that webhook registration returns a signing secret."""
    response = client.post(
        "/api/v1/webhooks",
        json={
            "url": "https://example.com/hook",
            "events": ["task.completed", "budget.alert"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "registered"
    assert "secret" in data["webhook"]
    assert len(data["webhook"]["secret"]) > 20  # URL-safe secret should be long
    assert data["webhook"]["url"] == "https://example.com/hook"
    assert set(data["webhook"]["events"]) == {"task.completed", "budget.alert"}


def test_webhook_list_endpoint(client):
    """Verify that GET /api/v1/webhooks returns registered webhooks without secrets."""
    # Register a webhook
    client.post(
        "/api/v1/webhooks",
        json={
            "url": "https://example.com/webhook1",
            "events": ["task.completed"],
        },
    )

    # List webhooks
    response = client.get("/api/v1/webhooks")

    assert response.status_code == 200
    webhooks = response.json()
    assert len(webhooks) == 1
    assert webhooks[0]["url"] == "https://example.com/webhook1"
    assert "task.completed" in webhooks[0]["events"]
    assert "secret" not in webhooks[0]  # Secrets should not be returned for security


def test_webhook_max_limit_enforced(client):
    """Verify that the 10-webhook-per-tenant limit is enforced."""
    # Register 10 webhooks (should succeed)
    for i in range(10):
        response = client.post(
            "/api/v1/webhooks",
            json={
                "url": f"https://example.com/webhook{i}",
                "events": ["task.completed"],
            },
        )
        assert response.status_code == 200

    # 11th webhook should fail
    response = client.post(
        "/api/v1/webhooks",
        json={
            "url": "https://example.com/webhook11",
            "events": ["task.completed"],
        },
    )
    assert response.status_code == 400
    assert "Maximum" in response.json()["detail"]


def test_webhook_url_validation():
    """Verify that webhook URL validation enforces HTTPS and blocks private IPs."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    tenant_registry = app_module.tenant_registry
    tenant, api_key = tenant_registry.register(name="Test Corp")

    client = TestClient(app)
    client.headers["X-API-Key"] = api_key

    # Test HTTP rejection
    response = client.post(
        "/api/v1/webhooks",
        json={
            "url": "http://example.com/hook",  # HTTP not HTTPS
            "events": ["task.completed"],
        },
    )
    assert response.status_code == 422  # Pydantic validation error

    # Test private IP rejection (localhost)
    response = client.post(
        "/api/v1/webhooks",
        json={
            "url": "https://localhost/hook",
            "events": ["task.completed"],
        },
    )
    assert response.status_code == 422

    os.unlink(db_path)


def test_webhook_dispatcher_wired_and_delivers_events():
    """Integration test: verify dispatcher is wired up and can deliver events.

    This test verifies:
    1. WebhookDispatcher singleton is initialized on app startup
    2. Webhook subscriptions can be registered
    3. Events can be dispatched to registered webhooks
    4. Signatures are generated correctly
    5. Delivery attempts are logged
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module
    from agency_os.service.webhooks import TASK_COMPLETED, WebhookEvent

    app_module.create_app()
    dispatcher = app_module.webhook_dispatcher

    # Verify dispatcher is initialized
    assert dispatcher is not None
    assert not dispatcher.live_mode  # Test mode by default

    # Register a webhook subscription directly (bypasses API auth for simplicity)
    test_org_id = "test-org-123"
    secret = "test-secret-abc"
    dispatcher.subscribe(
        org_id=test_org_id,
        url="https://example.com/task-webhook",
        events=["task.completed", "budget.alert"],
        secret=secret,
    )

    # Manually dispatch an event (simulates what tasks.py does)
    event = WebhookEvent(
        event_type=TASK_COMPLETED,
        org_id=test_org_id,
        payload={
            "task_id": "test-task-123",
            "agent_id": "agent-456",
            "status": "completed",
            "success": True,
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_sec": 2.5,
        },
    )

    # Dispatch the event
    attempts = dispatcher.dispatch(event)

    # Verify delivery attempt was logged
    assert len(attempts) == 1, "Expected 1 delivery attempt"
    delivery = attempts[0]
    assert delivery.url == "https://example.com/task-webhook"
    assert delivery.event_type == TASK_COMPLETED
    assert delivery.org_id == test_org_id
    assert delivery.payload["task_id"] == "test-task-123"
    assert delivery.signature.startswith("sha256=")
    assert delivery.success is True  # Test mode always succeeds

    # Verify signature format
    assert len(delivery.signature.split("=")) == 2
    assert delivery.signature.split("=")[0] == "sha256"
    assert len(delivery.signature.split("=")[1]) == 64  # SHA256 hex digest length

    # Verify the same event is in the delivery log
    assert len(dispatcher._delivery_log) >= 1
    logged_delivery = dispatcher._delivery_log[-1]
    assert logged_delivery.url == delivery.url
    assert logged_delivery.signature == delivery.signature

    os.unlink(db_path)


def test_webhook_signature_verification_example():
    """Example test demonstrating customer-side webhook signature verification.

    This test shows how customers should verify webhook signatures they receive,
    matching the documentation examples in docs/api-reference.md.
    """
    import hashlib
    import hmac

    def verify_webhook_signature(
        payload_bytes: bytes, signature: str, secret: str
    ) -> bool:
        """Verify Agency-OS webhook signature (customer implementation)."""
        expected = (
            "sha256="
            + hmac.new(
                secret.encode("utf-8"),
                msg=payload_bytes,
                digestmod=hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(signature, expected)

    # Test with documented test fixtures
    secret = "test-secret-key-123"
    payload = b'{"event_type":"task.completed","org_id":"org-abc123","timestamp":"2026-03-08T00:00:00Z","payload":{"task_id":"task-1","status":"success"}}'
    expected_signature = (
        "sha256=44604ce4f1b8e7db21223267db9f4a9249bfe61929e1b2b1918cd63d31d7f626"
    )

    # Verify signature
    assert verify_webhook_signature(payload, expected_signature, secret)

    # Verify that wrong signature fails
    wrong_signature = (
        "sha256=0000000000000000000000000000000000000000000000000000000000000000"
    )
    assert not verify_webhook_signature(payload, wrong_signature, secret)

    # Verify that wrong secret fails
    wrong_secret = "wrong-secret"
    assert not verify_webhook_signature(payload, expected_signature, wrong_secret)

    # Test with second documented test fixture
    secret2 = "production-webhook-key-xyz"
    payload2 = b'{"event_type":"budget.alert","org_id":"org-prod-456","timestamp":"2026-03-08T12:00:00Z","payload":{"budget_remaining":100,"threshold":0.1}}'
    expected_signature2 = (
        "sha256=3d18cedc520c8b72f0bc26679d73ee47dd7ff02542fc63dc1bb2dd5e2c9a86b8"
    )

    assert verify_webhook_signature(payload2, expected_signature2, secret2)
