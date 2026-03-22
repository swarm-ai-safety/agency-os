"""Tests for AI-powered configuration and SSE org provisioning."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agency_os.service.api.routers.configure import (
    _build_catalog_context,
    _check_monthly_quota,
    _monthly_usage,
    _parse_config_response,
)


class TestMonthlyQuota:
    def setup_method(self):
        _monthly_usage.clear()

    def test_allows_calls_within_quota(self):
        for _ in range(10):
            _check_monthly_quota("tenant-1", "free")

    def test_rejects_calls_over_quota(self):
        for _ in range(10):
            _check_monthly_quota("tenant-2", "free")

        with pytest.raises(HTTPException) as exc_info:
            _check_monthly_quota("tenant-2", "free")
        assert exc_info.value.status_code == 429
        assert "quota exceeded" in exc_info.value.detail.lower()

    def test_pro_tier_has_higher_quota(self):
        for _ in range(200):
            _check_monthly_quota("tenant-3", "pro")

        with pytest.raises(HTTPException):
            _check_monthly_quota("tenant-3", "pro")

    def test_tenants_are_independent(self):
        for _ in range(10):
            _check_monthly_quota("tenant-a", "free")

        # tenant-b should still have full quota
        _check_monthly_quota("tenant-b", "free")

    def test_resets_on_new_month(self):
        # Exhaust quota
        for _ in range(10):
            _check_monthly_quota("tenant-4", "free")

        # Simulate month rollover by changing the stored month key
        _monthly_usage["tenant-4"] = ("1999-01", 10)

        # Should work again (new month)
        _check_monthly_quota("tenant-4", "free")


class TestBuildCatalogContext:
    def test_includes_all_templates(self):
        catalog = _build_catalog_context()
        assert "saas-dev-studio" in catalog
        assert "biotech-research" in catalog
        assert "marketing-agency" in catalog
        assert "product-squad" in catalog
        assert "devops-team" in catalog

    def test_includes_governance_presets(self):
        catalog = _build_catalog_context()
        assert "conservative" in catalog
        assert "balanced" in catalog
        assert "aggressive" in catalog

    def test_includes_bid_strategies(self):
        catalog = _build_catalog_context()
        assert "quality_weighted" in catalog
        assert "specialization_bonus" in catalog
        assert "budget_conscious" in catalog


class TestParseConfigResponse:
    def test_parses_clean_json(self):
        raw = json.dumps({"package_name": "test", "agents": []})
        result = _parse_config_response(raw)
        assert result["package_name"] == "test"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"package_name": "test", "agents": []}\n```'
        result = _parse_config_response(raw)
        assert result["package_name"] == "test"

    def test_extracts_json_from_text(self):
        raw = 'Here is the config:\n{"package_name": "test", "agents": []}\nDone!'
        result = _parse_config_response(raw)
        assert result["package_name"] == "test"

    def test_raises_on_invalid_json(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _parse_config_response("not json at all")
        assert exc_info.value.status_code == 502


@pytest.fixture
def authed_client():
    """Shared test client with an authenticated tenant."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    tenant_registry = app_module.tenant_registry

    tenant, api_key = tenant_registry.register(name="Test Corp")
    tenant.metadata["stripe_customer_id"] = "cus_test"
    tenant.metadata["billing_status"] = "active"
    tenant_registry.save_metadata(tenant)

    c = TestClient(app)
    c.headers["X-API-Key"] = api_key
    yield c

    os.unlink(db_path)


class TestConfigureEndpoint:
    @pytest.fixture
    def client(self, authed_client):
        return authed_client

    @pytest.fixture
    def mock_llm_response(self):
        return json.dumps(
            {
                "package_name": "custom-data-team",
                "display_name": "Custom Data Team",
                "explanation": "A team optimized for data analysis workflows.",
                "agents": [
                    {
                        "ref": "engineering/senior-developer",
                        "count": 1,
                        "title": "Data Engineer",
                        "bid_strategy": "quality_weighted",
                        "initial_balance": 800.0,
                        "domain_tags": ["python", "sql", "data"],
                    }
                ],
                "governance_preset": "balanced",
                "governance_overrides": {},
                "workflows": [
                    {
                        "name": "data_pipeline",
                        "stages": [{"ingest": ["senior-developer"]}],
                    }
                ],
                "budget_limit_usd": 75.0,
                "based_on_template": None,
                "follow_up_question": None,
            }
        )

    def test_configure_returns_recommendation(self, client, mock_llm_response):
        with patch(
            "agency_os.service.api.routers.configure._call_llm",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            resp = client.post(
                "/api/v1/orgs/configure",
                json={
                    "description": "I need a team to build data pipelines and ETL processes"
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["package_name"] == "custom-data-team"
        assert len(data["agents"]) == 1
        assert data["agents"][0]["ref"] == "engineering/senior-developer"

    def test_configure_respects_budget_cap(self, client, mock_llm_response):
        with patch(
            "agency_os.service.api.routers.configure._call_llm",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            resp = client.post(
                "/api/v1/orgs/configure",
                json={
                    "description": "Build me a data team for analytics",
                    "budget_limit_usd": 50.0,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["budget_limit_usd"] <= 50.0

    def test_configure_rejects_short_description(self, client):
        resp = client.post(
            "/api/v1/orgs/configure",
            json={"description": "hi"},
        )
        assert resp.status_code == 422

    def test_refine_accepts_conversation(self, client, mock_llm_response):
        with patch(
            "agency_os.service.api.routers.configure._call_llm",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            resp = client.post(
                "/api/v1/orgs/configure/refine",
                json={
                    "description": "Actually, add a QA engineer too",
                    "conversation": [
                        {"role": "user", "content": "I need a data team"},
                        {"role": "assistant", "content": mock_llm_response},
                    ],
                },
            )

        assert resp.status_code == 200


class TestSSEOrgStream:
    @pytest.fixture
    def client(self, authed_client):
        return authed_client

    def test_stream_returns_sse_events(self, client):
        resp = client.post(
            "/api/v1/orgs/stream",
            json={"package_name": "saas_dev_studio"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = []
        for line in resp.text.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        log_events = [e for e in events if "phase" in e]
        result_events = [e for e in events if "org_id" in e]

        assert len(log_events) >= 3
        assert len(result_events) == 1
        assert result_events[0]["agent_count"] == 6

    def test_stream_error_on_bad_package(self, client):
        resp = client.post(
            "/api/v1/orgs/stream",
            json={"package_name": "nonexistent"},
        )
        assert resp.status_code == 200

        events = []
        for line in resp.text.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        error_events = [
            e
            for e in events
            if "message" in e and "not found" in e.get("message", "").lower()
        ]
        assert len(error_events) == 1
