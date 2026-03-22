"""Integration tests for OIDC bridge sessions and bearer auth."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch):
    created_paths: list[Path] = []

    def _create_client_with_tenant(
        email: str, bridge_secret: str
    ) -> tuple[TestClient, str]:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        created_paths.append(Path(db_path))

        monkeypatch.setenv("DATABASE_PATH", db_path)
        monkeypatch.setenv("AGENCY_OS_OIDC_BRIDGE_SECRET", bridge_secret)

        from agency_os.service.api import app as app_module

        app = app_module.create_app()
        tenant_registry = app_module.tenant_registry
        assert tenant_registry is not None

        tenant, _ = tenant_registry.register(
            name="OIDC Tenant",
            metadata={"email": email, "tier": "free"},
        )

        client = TestClient(app)
        return client, tenant.tenant_id

    yield _create_client_with_tenant

    for path in created_paths:
        path.unlink(missing_ok=True)


def test_oidc_bridge_can_issue_session_and_bearer_access(client_factory) -> None:
    client, tenant_id = client_factory(
        email="owner@example.com",
        bridge_secret="bridge-test-secret",
    )

    session_resp = client.post(
        "/api/v1/auth/oidc/session",
        headers={"X-OIDC-Bridge-Secret": "bridge-test-secret"},
        json={
            "email": "owner@example.com",
            "subject": "oidc-sub-123",
            "issuer": "https://issuer.example.com",
        },
    )
    assert session_resp.status_code == 200
    payload = session_resp.json()
    assert payload["tenant_id"] == tenant_id
    assert payload["session_token"]

    me_resp = client.get(
        "/api/v1/tenants/me",
        headers={"Authorization": f"Bearer {payload['session_token']}"},
    )
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["tenant_id"] == tenant_id


def test_oidc_bridge_requires_secret(client_factory) -> None:
    client, _ = client_factory(
        email="owner2@example.com",
        bridge_secret="bridge-test-secret-2",
    )

    session_resp = client.post(
        "/api/v1/auth/oidc/session",
        json={
            "email": "owner2@example.com",
            "subject": "oidc-sub-234",
            "issuer": "https://issuer.example.com",
        },
    )
    assert session_resp.status_code == 401


def test_oidc_bridge_rejects_unknown_email(client_factory) -> None:
    client, _ = client_factory(
        email="known@example.com",
        bridge_secret="bridge-test-secret-3",
    )

    session_resp = client.post(
        "/api/v1/auth/oidc/session",
        headers={"X-OIDC-Bridge-Secret": "bridge-test-secret-3"},
        json={
            "email": "unknown@example.com",
            "subject": "oidc-sub-345",
            "issuer": "https://issuer.example.com",
        },
    )
    assert session_resp.status_code == 403


def test_invalid_bearer_token_is_rejected(client_factory) -> None:
    client, _ = client_factory(
        email="owner3@example.com",
        bridge_secret="bridge-test-secret-4",
    )

    response = client.get(
        "/api/v1/tenants/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
