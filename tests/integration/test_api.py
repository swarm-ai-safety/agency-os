"""API integration tests using FastAPI TestClient."""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Use a temp database for each test run
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


@pytest.fixture
def unauthed_client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    yield TestClient(app)

    os.unlink(db_path)


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_missing_api_key(self, unauthed_client):
        from agency_os.service.api import app as app_module

        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert resp.status_code == 401
        logs = app_module.db.get_audit_log()
        assert any(log["action"] == "auth.failed" for log in logs)

    def test_invalid_api_key(self, unauthed_client):
        from agency_os.service.api import app as app_module

        unauthed_client.headers["X-API-Key"] = "invalid-key"
        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert resp.status_code == 401
        logs = app_module.db.get_audit_log()
        assert any(
            log["action"] == "auth.failed" and log["resource"] == "api_key"
            for log in logs
        )

    def test_deactivated_tenant_logs_auth_failure(self, unauthed_client):
        from agency_os.service.api import app as app_module

        tenant, api_key = app_module.tenant_registry.register(name="Disabled Corp")
        tenant.active = False
        app_module.tenant_registry.save_metadata(tenant)
        unauthed_client.headers["X-API-Key"] = api_key

        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()

        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        matching = [log for log in logs if log["action"] == "auth.failed"]
        assert matching
        detail = json.loads(matching[0]["detail"])
        assert detail["reason"] == "tenant_deactivated"

    def test_bearer_session_token_authenticates(self, unauthed_client):
        from agency_os.service.api import app as app_module
        from agency_os.service.api.middleware.session_tokens import (
            create_tenant_session_token,
        )

        tenant, _ = app_module.tenant_registry.register(name="Session Corp")
        tenant.metadata["stripe_customer_id"] = "cus_session"
        tenant.metadata["billing_status"] = "active"
        app_module.tenant_registry.save_metadata(tenant)

        token = create_tenant_session_token(tenant.tenant_id)
        resp = unauthed_client.post(
            "/api/v1/orgs",
            json={"package_name": "saas_dev_studio"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_invalid_bearer_token_rejected_and_audited(self, unauthed_client):
        from agency_os.service.api import app as app_module

        resp = unauthed_client.post(
            "/api/v1/orgs",
            json={"package_name": "saas_dev_studio"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401
        assert "bearer" in resp.json()["detail"].lower()

        logs = app_module.db.get_audit_log()
        failures = [log for log in logs if log["action"] == "auth.failed"]
        assert failures
        detail = json.loads(failures[0]["detail"])
        assert detail["reason"] == "invalid_bearer_token"


class TestOidcBridge:
    def test_create_oidc_session_token(self, unauthed_client, monkeypatch):
        from agency_os.service.api import app as app_module
        from agency_os.service.api.middleware.session_tokens import (
            verify_tenant_session_token,
        )

        monkeypatch.setenv("AGENCY_OS_OIDC_BRIDGE_SECRET", "test-bridge-secret")
        tenant, _ = app_module.tenant_registry.register(name="OIDC Corp")
        tenant.metadata["email"] = "owner@oidc.example"
        app_module.tenant_registry.save_metadata(tenant)

        resp = unauthed_client.post(
            "/api/v1/auth/oidc/session",
            json={
                "email": "owner@oidc.example",
                "subject": "oidc-sub-123",
                "issuer": "https://issuer.example",
            },
            headers={"X-OIDC-Bridge-Secret": "test-bridge-secret"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["tenant_id"] == tenant.tenant_id
        assert payload["tenant_name"] == "OIDC Corp"
        assert payload["expires_in"] == 8 * 60 * 60
        token_payload = verify_tenant_session_token(payload["session_token"])
        assert token_payload is not None
        assert token_payload["sub"] == tenant.tenant_id

    def test_create_oidc_session_rejects_unknown_tenant(
        self, unauthed_client, monkeypatch
    ):
        monkeypatch.setenv("AGENCY_OS_OIDC_BRIDGE_SECRET", "test-bridge-secret")

        resp = unauthed_client.post(
            "/api/v1/auth/oidc/session",
            json={
                "email": "unknown@example.com",
                "subject": "oidc-sub-123",
                "issuer": "https://issuer.example",
            },
            headers={"X-OIDC-Bridge-Secret": "test-bridge-secret"},
        )
        assert resp.status_code == 403


class TestBillingGate:
    def test_free_tier_tenant_can_create_org(self, unauthed_client):
        """Free tier tenants (no billing setup) can create organizations."""
        from agency_os.service.api import app as app_module

        tenant, api_key = app_module.tenant_registry.register(name="Free Corp")
        unauthed_client.headers["X-API-Key"] = api_key

        # Free tier tenants pass through require_active_billing
        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert resp.status_code == 200

    def test_org_creation_rejected_with_incomplete_billing(self, unauthed_client):
        """Tenants who started billing setup but lack active subscription get 402."""
        from agency_os.service.api import app as app_module

        tenant, api_key = app_module.tenant_registry.register(name="Unpaid Corp")
        tenant.metadata["stripe_customer_id"] = "cus_test"
        tenant.metadata["billing_status"] = "incomplete"
        app_module.tenant_registry.save_metadata(tenant)
        unauthed_client.headers["X-API-Key"] = api_key

        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert resp.status_code == 402


class TestPackages:
    def test_list_packages(self, client):
        resp = client.get("/api/v1/packages")
        assert resp.status_code == 200
        packages = resp.json()
        assert len(packages) >= 1
        names = [p["name"] for p in packages]
        assert "saas-dev-studio" in names

    def test_get_package(self, client):
        resp = client.get("/api/v1/packages/saas_dev_studio")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "saas-dev-studio"
        assert len(data["agents"]) == 6

    def test_get_missing_package(self, client):
        resp = client.get("/api/v1/packages/nonexistent")
        assert resp.status_code == 404


class TestOrgLifecycle:
    def test_create_org(self, client):
        from agency_os.service.api import app as app_module

        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["agent_count"] == 6

        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(
            log["action"] == "org.created" and log["resource_id"] == data["org_id"]
            for log in logs
        )

    def test_create_org_accepts_hyphenated_package_name(self, client):
        resp = client.post("/api/v1/orgs", json={"package_name": "saas-dev-studio"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["package"] == "saas-dev-studio"

    def test_create_org_missing_package_returns_404(self, client):
        resp = client.post("/api/v1/orgs", json={"package_name": "does-not-exist"})
        assert resp.status_code == 404
        assert "package not found" in resp.json()["detail"].lower()

    def test_create_org_invalid_package_name_returns_400(self, client):
        resp = client.post("/api/v1/orgs", json={"package_name": "../bad"})
        assert resp.status_code == 400
        assert "invalid name" in resp.json()["detail"].lower()

    def test_list_orgs(self, client):
        client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        resp = client.get("/api/v1/orgs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_org(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}")
        assert resp.status_code == 200
        assert resp.json()["org_id"] == org_id

    def test_delete_org(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.delete(
            f"/api/v1/orgs/{org_id}",
            headers={
                "X-API-Key": client.headers["X-API-Key"],
                "X-Manager-Approval": "true",
                "X-Approval-Reason": "Approved destructive org shutdown.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(
            log["action"] == "org.deleted" and log["resource_id"] == org_id
            for log in logs
        )

    def test_delete_org_requires_approval(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.delete(f"/api/v1/orgs/{org_id}")
        assert resp.status_code == 403
        assert "approval" in resp.json()["detail"].lower()

    def test_get_missing_org(self, client):
        resp = client.get("/api/v1/orgs/nonexistent")
        # Non-existent orgs return 403 to avoid org-id enumeration.
        assert resp.status_code == 403


class TestTasks:
    def test_submit_task(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Build user authentication"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assigned"
        assert data["assigned_to"] is not None

        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(
            log["action"] == "task.submitted" and log["resource_id"] == data["task_id"]
            for log in logs
        )

    def test_list_tasks(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Build auth"},
        )
        resp = client.get(f"/api/v1/orgs/{org_id}/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_high_impact_task_requires_approval(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        denied = client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Deploy to production now"},
        )
        assert denied.status_code == 403
        assert "approval" in denied.json()["detail"].lower()
        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(
            log["action"] == "approval.denied"
            and log["resource"] == "task.high_impact"
            and log["resource_id"] == org_id
            for log in logs
        )

        approved = client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Deploy to production now"},
            headers={
                "X-API-Key": client.headers["X-API-Key"],
                "X-Manager-Approval": "true",
                "X-Approval-Reason": "Approved production deployment.",
            },
        )
        assert approved.status_code == 200

    def test_get_task(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        task_resp = client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Build auth"},
        )
        task_id = task_resp.json()["task_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task_id

    def test_submit_task_with_metering_and_no_db_does_not_crash(self, client):
        from agency_os.service.api import app as app_module
        from agency_os.service.api.routers import tasks as tasks_router

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        # Regression guard: metering can be configured while task DB is unset.
        # Task submission must still succeed (no trust-tier UnboundLocalError).
        assert app_module.metering_collector is not None
        tasks_router.set_metering(app_module.metering_collector, None)
        try:
            resp = client.post(
                f"/api/v1/orgs/{org_id}/tasks",
                json={"description": "Build user authentication"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "assigned"
            assert data["assigned_to"] is not None
        finally:
            # Restore default behavior for any future route calls.
            tasks_router.set_metering(app_module.metering_collector, app_module.db)


class TestAgents:
    def test_list_agents(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 6

    def test_agent_history_rejects_oversized_limit(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]
        agent_id = client.get(f"/api/v1/orgs/{org_id}/agents").json()[0]["agent_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/agents/{agent_id}/history?limit=101")
        assert resp.status_code == 422

    def test_agent_history_rejects_zero_limit(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]
        agent_id = client.get(f"/api/v1/orgs/{org_id}/agents").json()[0]["agent_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/agents/{agent_id}/history?limit=0")
        assert resp.status_code == 422

    def test_agent_history_rejects_negative_limit(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]
        agent_id = client.get(f"/api/v1/orgs/{org_id}/agents").json()[0]["agent_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/agents/{agent_id}/history?limit=-1")
        assert resp.status_code == 422


class TestGovernance:
    def test_get_governance(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/governance")
        assert resp.status_code == 200
        assert resp.json()["preset"] == "balanced"

    def test_patch_governance(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        resp = client.patch(
            f"/api/v1/orgs/{org_id}/governance",
            json={"preset": "conservative"},
        )
        assert resp.status_code == 200
        assert resp.json()["preset"] == "conservative"

    def test_policy_versioning_canary_promote_and_rollback(self, client):
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]

        canary = client.patch(
            f"/api/v1/orgs/{org_id}/governance",
            json={
                "preset": "conservative",
                "rollout_strategy": "canary",
                "canary_percent": 20,
            },
        )
        assert canary.status_code == 200
        assert canary.json()["policy_version"] == 1
        assert canary.json()["rollout"]["status"] == "canary"
        assert canary.json()["rollout"]["canary_percent"] == 20

        current = client.get(f"/api/v1/orgs/{org_id}/governance")
        assert current.status_code == 200
        assert current.json()["policy_version"] == 1
        assert current.json()["rollout"]["status"] == "canary"

        promoted = client.post(f"/api/v1/orgs/{org_id}/governance/promote")
        assert promoted.status_code == 200
        assert promoted.json()["policy_version"] == 1
        assert promoted.json()["rollout"]["status"] == "active"
        assert promoted.json()["rollout"]["canary_percent"] == 100

        rollback = client.post(f"/api/v1/orgs/{org_id}/governance/rollback")
        assert rollback.status_code == 409

        # Create a second policy version, then rollback to v1.
        second = client.patch(
            f"/api/v1/orgs/{org_id}/governance",
            json={"preset": "aggressive"},
        )
        assert second.status_code == 200
        assert second.json()["policy_version"] == 2
        assert second.json()["previous_policy_version"] == 1

        rollback = client.post(
            f"/api/v1/orgs/{org_id}/governance/rollback",
            json={"target_version": 1},
        )
        assert rollback.status_code == 200
        assert rollback.json()["policy_version"] == 3
        assert rollback.json()["rollback_to_version"] == 1
        assert rollback.json()["preset"] == "conservative"

    def test_governance_history_includes_audits_and_circuit_trips(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = create_resp.json()["org_id"]
        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        assert tenant is not None

        patched = client.patch(
            f"/api/v1/orgs/{org_id}/governance",
            json={"preset": "conservative"},
        )
        assert patched.status_code == 200

        app_module.db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "agent_id": "agent-123",
                "event_type": "circuit_breaker.tripped",
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": 1710000000.0,
                "metadata": {
                    "task_id": "task-abc",
                    "agent_id": "agent-123",
                    "threshold": 3,
                    "consecutive_failures": 3,
                    "reason": "unit test",
                    "duration_sec": 1.2,
                },
            }
        )

        history = client.get(f"/api/v1/orgs/{org_id}/governance/history?limit=10")
        assert history.status_code == 200
        payload = history.json()

        assert payload["stats"]["audit_events"] >= 1
        assert payload["stats"]["circuit_breaker_trips"] == 1
        assert any(
            item["action"] == "governance.policy.versioned"
            for item in payload["audit_timeline"]
        )
        assert payload["circuit_breaker_history"][0]["agent_id"] == "agent-123"
        assert payload["circuit_breaker_history"][0]["threshold"] == 3


class TestMetering:
    def test_org_metering_supports_filters_and_pagination(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert create_resp.status_code == 200
        org_id = create_resp.json()["org_id"]

        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        assert tenant is not None

        app_module.db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "agent_id": "agent-1",
                "event_type": "llm_call",
                "tokens_in": 120,
                "tokens_out": 45,
                "timestamp": 100.0,
                "metadata": {"task_id": "task-a", "source": "test"},
            }
        )
        app_module.db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "agent_id": "agent-1",
                "event_type": "task_outcome",
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": 200.0,
                "metadata": {"task_id": "task-b", "outcome": "success"},
            }
        )

        resp = client.get(
            f"/api/v1/orgs/{org_id}/metering"
            "?eventType=llm_call&startTime=50&endTime=150&limit=10&offset=0"
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["limit"] == 10
        assert payload["offset"] == 0
        assert len(payload["items"]) == 1
        assert payload["items"][0]["event_type"] == "llm_call"
        assert payload["items"][0]["metadata"]["task_id"] == "task-a"

    def test_agent_and_task_metering_queries_are_tenant_scoped(self, client):
        from agency_os.service.api import app as app_module

        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert create_resp.status_code == 200
        org_id = create_resp.json()["org_id"]

        submit = client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "metering query test", "metadata": {}},
        )
        assert submit.status_code == 200
        task_id = submit.json()["task_id"]

        tenant = app_module.tenant_registry.get_by_api_key(client.headers["X-API-Key"])
        assert tenant is not None

        app_module.db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "agent_id": "agent-target",
                "event_type": "llm_call",
                "tokens_in": 10,
                "tokens_out": 5,
                "timestamp": 300.0,
                "metadata": {"task_id": task_id},
            }
        )
        app_module.db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": org_id,
                "agent_id": "agent-other",
                "event_type": "llm_call",
                "tokens_in": 1,
                "tokens_out": 1,
                "timestamp": 301.0,
                "metadata": {"task_id": "another-task"},
            }
        )

        by_agent = client.get(f"/api/v1/orgs/{org_id}/agents/agent-target/metering")
        assert by_agent.status_code == 200
        agent_payload = by_agent.json()
        assert agent_payload["total"] == 1
        assert agent_payload["items"][0]["agent_id"] == "agent-target"

        by_task = client.get(f"/api/v1/tasks/{task_id}/metering")
        assert by_task.status_code == 200
        task_payload = by_task.json()
        assert task_payload["total"] == 1
        assert task_payload["items"][0]["metadata"]["task_id"] == task_id

        missing_task = client.get("/api/v1/tasks/not-a-task/metering")
        assert missing_task.status_code == 404

    def test_unknown_metering_route_returns_404_not_500(self, client):
        resp = client.get("/api/metering")
        assert resp.status_code == 404


class TestTenants:
    def test_create_tenant(self, unauthed_client):
        from agency_os.service.api import app as app_module

        resp = unauthed_client.post(
            "/api/v1/tenants",
            json={
                "name": "New Corp",
                "email": "new@corp.com",
                "password": "StrongPass123!",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Corp"
        assert data["api_key"].startswith("ak-")
        assert data["session_token"].startswith("ts-")
        assert data["session_expires_in"] > 0
        assert data["tenant_id"].startswith("tenant-")

        tenant = app_module.tenant_registry.get_by_api_key(data["api_key"])
        assert tenant is not None
        assert tenant.metadata["tier"] == "free"
        assert tenant.metadata["budget_limit_usd"] == 2.0
        assert tenant.metadata["email"] == "new@corp.com"
        assert tenant.metadata["password_hash"].startswith("pbkdf2_sha256$")
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(log["action"] == "tenant.registered" for log in logs)

    def test_login_with_password_and_session_bearer(self, unauthed_client):
        create = unauthed_client.post(
            "/api/v1/tenants",
            json={
                "name": "Session Corp",
                "email": "session@corp.com",
                "password": "StrongPass123!",
            },
        )
        assert create.status_code == 200
        tenant_id = create.json()["tenant_id"]

        login = unauthed_client.post(
            "/api/v1/tenants/login",
            json={"identifier": "session@corp.com", "password": "StrongPass123!"},
        )
        assert login.status_code == 200
        payload = login.json()
        assert payload["tenant_id"] == tenant_id
        assert payload["session_token"].startswith("ts-")

        me = unauthed_client.get(
            "/api/v1/tenants/me",
            headers={"Authorization": f"Bearer {payload['session_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["tenant_id"] == tenant_id

    def test_get_me(self, client):
        resp = client.get("/api/v1/tenants/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Corp"
        assert data["billing_status"] == "active"
        # Billing fields should be present
        assert "tier" in data
        assert "budget_limit_usd" in data
        assert "total_spent_usd" in data
        assert "stripe_customer_id" in data

    def test_rotate_key(self, client):
        from agency_os.service.api import app as app_module

        old_key = client.headers["X-API-Key"]
        resp = client.post(
            "/api/v1/tenants/me/rotate-key",
            headers={
                "X-API-Key": old_key,
                "X-Manager-Approval": "true",
                "X-Approval-Reason": "Approved credential rotation.",
            },
        )
        assert resp.status_code == 200
        new_key = resp.json()["api_key"]
        assert new_key != old_key

        # Old key should no longer work
        client.headers["X-API-Key"] = old_key
        resp = client.get("/api/v1/tenants/me")
        assert resp.status_code == 401

        # New key works
        client.headers["X-API-Key"] = new_key
        resp = client.get("/api/v1/tenants/me")
        assert resp.status_code == 200

        tenant = app_module.tenant_registry.get_by_api_key(new_key)
        logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        assert any(log["action"] == "tenant.api_key_rotated" for log in logs)

    def test_rotate_key_requires_approval(self, client):
        resp = client.post("/api/v1/tenants/me/rotate-key")
        assert resp.status_code == 403
        assert "approval" in resp.json()["detail"].lower()

    def test_emergency_freeze_blocks_token_operations(self, client):
        freeze = client.post(
            "/api/v1/tenants/me/emergency-freeze",
            json={"enabled": True, "reason": "Incident response containment."},
            headers={
                "X-API-Key": client.headers["X-API-Key"],
                "X-Manager-Approval": "true",
                "X-Approval-Reason": "Enable emergency freeze during incident.",
            },
        )
        assert freeze.status_code == 200
        assert freeze.json()["emergency_freeze"] is True

        blocked = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert blocked.status_code == 423
        assert "emergency freeze" in blocked.json()["detail"].lower()

    def test_list_tenant_organizations(self, client):
        """Test GET /api/v1/tenants/me/organizations returns tenant's orgs."""
        # Create an organization
        create_resp = client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        assert create_resp.status_code == 200
        org_id = create_resp.json()["org_id"]

        # List organizations via tenant endpoint
        resp = client.get("/api/v1/tenants/me/organizations")
        assert resp.status_code == 200
        orgs = resp.json()
        assert isinstance(orgs, list)
        assert len(orgs) >= 1

        # Verify structure
        org = next((o for o in orgs if o["org_id"] == org_id), None)
        assert org is not None
        assert "org_id" in org
        assert "name" in org
        assert "status" in org
        assert "agent_count" in org
        assert "created_at" in org
        assert org["name"] == "saas_dev_studio"  # package_name used as name

    def test_tenant_onboarding_status_progression(self, unauthed_client):
        from agency_os.service.api import app as app_module

        create = unauthed_client.post(
            "/api/v1/tenants",
            json={
                "name": "Onboarding Corp",
                "email": "onboarding@corp.com",
                "password": "StrongPass123!",
            },
        )
        assert create.status_code == 200
        api_key = create.json()["api_key"]
        headers = {"X-API-Key": api_key}

        initial = unauthed_client.get("/api/v1/tenants/me/onboarding", headers=headers)
        assert initial.status_code == 200
        initial_data = initial.json()
        assert initial_data["account_created"] is True
        assert initial_data["has_organization"] is False
        assert initial_data["has_first_task"] is False
        assert initial_data["billing_configured"] is False
        assert initial_data["has_first_api_call"] is False
        assert initial_data["completed_steps"] == 1
        assert initial_data["next_step"] == "create_organization"

        create_org = unauthed_client.post(
            "/api/v1/orgs",
            json={"package_name": "saas_dev_studio"},
            headers=headers,
        )
        assert create_org.status_code == 200
        org_id = create_org.json()["org_id"]

        after_org = unauthed_client.get(
            "/api/v1/tenants/me/onboarding", headers=headers
        )
        assert after_org.status_code == 200
        after_org_data = after_org.json()
        assert after_org_data["has_organization"] is True
        assert after_org_data["has_first_task"] is False
        assert after_org_data["completed_steps"] == 2
        assert after_org_data["next_step"] == "run_first_task"
        assert after_org_data["organizations_count"] == 1

        create_task = unauthed_client.post(
            f"/api/v1/orgs/{org_id}/tasks",
            json={"description": "Run onboarding smoke task"},
            headers=headers,
        )
        assert create_task.status_code == 200

        after_task = unauthed_client.get(
            "/api/v1/tenants/me/onboarding", headers=headers
        )
        assert after_task.status_code == 200
        after_task_data = after_task.json()
        assert after_task_data["has_first_task"] is True
        assert after_task_data["completed_steps"] == 3
        assert after_task_data["is_complete"] is False
        assert after_task_data["next_step"] == "configure_billing"
        assert after_task_data["tasks_count"] >= 1

        tenant = app_module.tenant_registry.get_by_api_key(api_key)
        assert tenant is not None
        tenant.metadata["stripe_customer_id"] = "cus_onboarding"
        tenant.metadata["billing_status"] = "active"
        app_module.tenant_registry.save_metadata(tenant)

        after_billing = unauthed_client.get(
            "/api/v1/tenants/me/onboarding", headers=headers
        )
        assert after_billing.status_code == 200
        after_billing_data = after_billing.json()
        assert after_billing_data["billing_configured"] is True
        assert after_billing_data["is_complete"] is True
        assert after_billing_data["completed_steps"] == 4
        assert after_billing_data["next_step"] == "make_first_api_call"

        app_module.db.save_gateway_request(
            {
                "request_id": "req-onboarding-1",
                "tenant_id": tenant.tenant_id,
                "model_id": "llama-3.1-8b",
                "provider": "test",
                "tokens_in": 10,
                "tokens_out": 25,
                "latency_ms": 120.0,
                "provider_cost": 0.0005,
                "customer_cost": 0.0008,
                "margin": 0.0003,
                "cached": False,
                "routed_by": "test",
                "complexity": "low",
                "status": "success",
                "timestamp": 1_700_000_000.0,
            }
        )

        after_first_call = unauthed_client.get(
            "/api/v1/tenants/me/onboarding", headers=headers
        )
        assert after_first_call.status_code == 200
        after_first_call_data = after_first_call.json()
        assert after_first_call_data["has_first_api_call"] is True
        assert after_first_call_data["next_step"] == "complete"


class TestPricing:
    def test_get_pricing_public_no_auth(self, unauthed_client):
        """Pricing endpoint is public and requires no authentication."""
        resp = unauthed_client.get("/api/pricing")
        assert resp.status_code == 200
        data = resp.json()

        # Verify structure matches pricing.schema.json
        assert "plans" in data
        assert "models" in data
        assert "executionPricing" in data
        assert "volumeDiscounts" in data
        assert "commonFeatures" in data
        assert "metadata" in data

        # Verify plans structure
        assert len(data["plans"]) == 3

    def test_get_plans_public_no_auth(self, unauthed_client):
        """GET /api/plans alias is public and returns same data as /api/pricing."""
        resp = unauthed_client.get("/api/plans")
        assert resp.status_code == 200
        data = resp.json()

        # Verify structure matches pricing.schema.json
        assert "plans" in data
        assert "models" in data
        assert "executionPricing" in data
        assert "volumeDiscounts" in data
        assert "commonFeatures" in data
        assert "metadata" in data

        # Verify plans array has expected entries
        assert len(data["plans"]) == 3
        plan_ids = {p["id"] for p in data["plans"]}
        assert plan_ids == {"free", "pro", "enterprise"}
        plan_ids = [p["id"] for p in data["plans"]]
        assert "free" in plan_ids
        assert "pro" in plan_ids
        assert "enterprise" in plan_ids

        # Verify models structure
        assert "openai" in data["models"]
        assert "anthropic" in data["models"]
        assert len(data["models"]["openai"]) >= 5
        assert len(data["models"]["anthropic"]) >= 3

        # Verify execution pricing
        assert len(data["executionPricing"]) == 3

        # Verify volume discounts
        assert len(data["volumeDiscounts"]) == 4

        # Verify metadata
        assert data["metadata"]["currency"] == "USD"
        assert data["metadata"]["billingCycle"] == "monthly"


class TestPlansV1:
    """Test the /api/v1/plans public endpoint."""

    def test_v1_plans_returns_pricing(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data
        plan_ids = [p["id"] for p in data["plans"]]
        assert "free" in plan_ids
        assert "pro" in plan_ids

    def test_v1_plans_no_auth_required(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/plans")
        assert resp.status_code == 200


class TestTenantProfileUpdate:
    """Test PATCH /api/v1/tenants/me profile updates."""

    def test_update_name(self, client):
        resp = client.patch("/api/v1/tenants/me", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

        # Verify persistence
        me = client.get("/api/v1/tenants/me").json()
        assert me["name"] == "New Name"

    def test_update_email(self, client):
        resp = client.patch("/api/v1/tenants/me", json={"email": "new@example.com"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@example.com"

    def test_update_both(self, client):
        resp = client.patch(
            "/api/v1/tenants/me",
            json={"name": "Updated Corp", "email": "updated@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Corp"
        assert data["email"] == "updated@example.com"

    def test_no_fields_returns_400(self, client):
        resp = client.patch("/api/v1/tenants/me", json={})
        assert resp.status_code == 400
        assert "No fields" in resp.json()["detail"]

    def test_duplicate_email_returns_409(self, unauthed_client):
        from agency_os.service.api import app as app_module

        # Register two tenants
        t1, key1 = app_module.tenant_registry.register(name="Corp A")
        t1.metadata["email"] = "taken@example.com"
        app_module.tenant_registry.save_metadata(t1)

        t2, key2 = app_module.tenant_registry.register(name="Corp B")
        unauthed_client.headers["X-API-Key"] = key2

        resp = unauthed_client.patch(
            "/api/v1/tenants/me", json={"email": "taken@example.com"}
        )
        assert resp.status_code == 409

    def test_unauthenticated_returns_401(self, unauthed_client):
        resp = unauthed_client.patch("/api/v1/tenants/me", json={"name": "Hacker"})
        assert resp.status_code == 401

    def test_profile_update_is_audited(self, client):
        from agency_os.service.api import app as app_module

        client.patch("/api/v1/tenants/me", json={"name": "Audited Corp"})
        logs = app_module.db.get_audit_log()
        assert any(log["action"] == "tenant.profile_updated" for log in logs)


class TestOrgPlanChange:
    """Test PATCH /api/v1/orgs/{org_id} plan changes."""

    def _create_org(self, client):
        resp = client.post("/api/v1/orgs", json={"package_name": "saas_dev_studio"})
        assert resp.status_code == 200
        return resp.json()["org_id"]

    def test_change_package(self, client):
        org_id = self._create_org(client)
        resp = client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"package_name": "saas_dev_studio"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == org_id
        assert data["status"] == "running"
        assert data["agent_count"] > 0

    def test_invalid_package_returns_404(self, client):
        org_id = self._create_org(client)
        resp = client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"package_name": "nonexistent_package"},
        )
        assert resp.status_code == 404

    def test_no_fields_returns_400(self, client):
        org_id = self._create_org(client)
        resp = client.patch(f"/api/v1/orgs/{org_id}", json={})
        assert resp.status_code == 400

    def test_cross_tenant_returns_403(self, unauthed_client):
        from agency_os.service.api import app as app_module

        # Create org under tenant A
        t_a, key_a = app_module.tenant_registry.register(name="Tenant A")
        t_a.metadata["billing_status"] = "active"
        t_a.metadata["stripe_customer_id"] = "cus_a"
        app_module.tenant_registry.save_metadata(t_a)

        unauthed_client.headers["X-API-Key"] = key_a
        resp = unauthed_client.post(
            "/api/v1/orgs", json={"package_name": "saas_dev_studio"}
        )
        org_id = resp.json()["org_id"]

        # Try to update from tenant B
        t_b, key_b = app_module.tenant_registry.register(name="Tenant B")
        unauthed_client.headers["X-API-Key"] = key_b

        resp = unauthed_client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"package_name": "saas_dev_studio"},
        )
        assert resp.status_code == 403

    def test_plan_change_is_audited(self, client):
        from agency_os.service.api import app as app_module

        org_id = self._create_org(client)
        client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"package_name": "saas_dev_studio"},
        )
        logs = app_module.db.get_audit_log()
        assert any(log["action"] == "org.plan_changed" for log in logs)


class TestWaitlist:
    def test_post_signup_public(self, unauthed_client):
        resp = unauthed_client.post(
            "/api/v1/waitlist", json={"email": "test@example.com"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_get_waitlist_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/waitlist")
        assert resp.status_code == 401

    def test_get_waitlist_returns_signups(self, client):
        # Add a signup first
        client.post("/api/v1/waitlist", json={"email": "alice@example.com"})
        client.post("/api/v1/waitlist", json={"email": "bob@example.com"})

        resp = client.get("/api/v1/waitlist")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        emails = {entry["email"] for entry in data}
        assert "alice@example.com" in emails
        assert "bob@example.com" in emails

    def test_get_waitlist_pagination(self, client):
        for i in range(5):
            client.post("/api/v1/waitlist", json={"email": f"page{i}@example.com"})

        resp = client.get("/api/v1/waitlist?limit=2&offset=0")
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1) == 2

        resp = client.get("/api/v1/waitlist?limit=2&offset=2")
        assert resp.status_code == 200
        page2 = resp.json()
        assert len(page2) == 2

        # No overlap
        ids1 = {e["email"] for e in page1}
        ids2 = {e["email"] for e in page2}
        assert ids1.isdisjoint(ids2)

    def test_get_waitlist_stats_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/waitlist/stats")
        assert resp.status_code == 401

    def test_get_waitlist_stats(self, client):
        client.post("/api/v1/waitlist", json={"email": "stats@example.com"})

        resp = client.get("/api/v1/waitlist/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["last_24h"] >= 1
        assert data["last_7d"] >= 1
        assert data["last_30d"] >= 1
