"""Tests for the LLM Gateway."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from agency_os.gateway.cache import ResponseCache
from agency_os.gateway.config import GatewayConfig, ModelConfig
from agency_os.gateway.failover import call_with_failover
from agency_os.gateway.providers.anthropic_provider import AnthropicProvider
from agency_os.gateway.providers.base import (
    CompletionChunk,
    CompletionResult,
    TokenUsage,
)
from agency_os.gateway.providers.registry import ProviderRegistry
from agency_os.gateway.router import Complexity, SmartRouter, classify_complexity
from agency_os.gateway.routing_feedback import RoutingFeedback

# ------------------------------------------------------------------
# Config tests
# ------------------------------------------------------------------


class TestGatewayConfig:
    def test_default_models_loaded(self):
        config = GatewayConfig()
        assert config.get_model("gpt-4o") is not None
        assert config.get_model("claude-sonnet-4") is not None

    def test_unknown_model_returns_none(self):
        config = GatewayConfig()
        assert config.get_model("nonexistent") is None

    def test_list_models_all_enabled(self):
        config = GatewayConfig()
        models = config.list_models()
        assert len(models) >= 4

    def test_list_models_filtered_by_tenant(self):
        config = GatewayConfig()
        metadata = {"allowed_models": ["gpt-4o", "claude-sonnet-4"]}
        models = config.list_models(metadata)
        ids = {m.model_id for m in models}
        assert ids == {"gpt-4o", "claude-sonnet-4"}

    def test_customer_pricing_includes_markup(self):
        config = GatewayConfig()
        model = config.get_model("gpt-4o")
        assert model is not None
        price = config.customer_price_per_1k(model, "input")
        assert price > model.cost_per_1k_input  # markup applied

    def test_custom_models(self):
        custom = [
            ModelConfig(
                model_id="test-model",
                provider="openai",
                actual_model="gpt-test",
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.002,
            )
        ]
        config = GatewayConfig(models=custom)
        assert config.get_model("test-model") is not None
        assert config.get_model("gpt-4o") is None  # defaults replaced

    def test_anthropic_haiku_model_uses_supported_api_id(self):
        config = GatewayConfig()
        model = config.get_model("claude-haiku-3.5")
        assert model is not None
        assert model.actual_model == "claude-3-5-haiku-20241022"


# ------------------------------------------------------------------
# Anthropic message translation tests
# ------------------------------------------------------------------


class TestAnthropicTranslation:
    def test_system_message_extraction(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        system, converted = AnthropicProvider._translate_messages(messages)
        assert system == "You are helpful."
        assert len(converted) == 1
        assert converted[0]["role"] == "user"

    def test_no_system_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        system, converted = AnthropicProvider._translate_messages(messages)
        assert system is None
        assert len(converted) == 1

    def test_multi_turn_conversation(self):
        messages = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]
        system, converted = AnthropicProvider._translate_messages(messages)
        assert system == "Be brief."
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"
        assert converted[2]["role"] == "user"


# ------------------------------------------------------------------
# Provider registry tests
# ------------------------------------------------------------------


class TestProviderRegistry:
    def test_unknown_provider_returns_none(self):
        registry = ProviderRegistry()
        assert registry.get("unknown") is None

    def test_missing_api_key_returns_none(self):
        registry = ProviderRegistry()
        # Without OPENAI_API_KEY set, should return None
        with patch.dict("os.environ", {}, clear=True):
            result = registry.get("openai")
            assert result is None

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_openai_provider_cached(self):
        registry = ProviderRegistry()
        p1 = registry.get("openai")
        p2 = registry.get("openai")
        assert p1 is p2  # same instance


# ------------------------------------------------------------------
# Gateway router tests
# ------------------------------------------------------------------


class TestGatewayRouter:
    @pytest.fixture()
    def client(self):
        """Create a test client with mock provider."""
        from agency_os.service.api import app as app_module
        from agency_os.service.api.routers import gateway

        app = app_module.create_app()

        # Register a tenant with active billing
        tenant, api_key = app_module.tenant_registry.register(name="Gateway Test")
        tenant.metadata["stripe_customer_id"] = "cus_gw_test"
        tenant.metadata["billing_status"] = "active"
        app_module.tenant_registry.save_metadata(tenant)

        # Set up mock provider
        mock_provider = AsyncMock()
        mock_provider.chat_completion = AsyncMock(
            return_value=CompletionResult(
                content="Hello! How can I help?",
                model="gpt-4o",
                finish_reason="stop",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=8,
                    total_tokens=18,
                ),
            )
        )

        async def mock_stream(*args, **kwargs):
            yield CompletionChunk(delta_content="Hello", model="gpt-4o")
            yield CompletionChunk(delta_content="!", model="gpt-4o")
            yield CompletionChunk(
                delta_content="",
                model="gpt-4o",
                finish_reason="stop",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                ),
            )

        mock_provider.chat_completion_stream = mock_stream

        mock_registry = MagicMock(spec=ProviderRegistry)
        mock_registry.get.return_value = mock_provider

        gateway.set_provider_registry(mock_registry)

        test_client = TestClient(app)
        return test_client, tenant, api_key, mock_provider

    def test_chat_completion(self, client):
        test_client, tenant, api_key, mock_provider = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "gpt-4o"
        assert data["choices"][0]["message"]["content"] == "Hello! How can I help?"
        assert data["usage"]["prompt_tokens"] == 10
        assert data["usage"]["completion_tokens"] == 8

    def test_unknown_model_rejected(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "nonexistent-model",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 400
        assert "Unknown model" in resp.json()["detail"]
        assert resp.json()["error_code"] == "unknown_model"

    def test_billing_required_for_incomplete_setup(self):
        """Tenant with incomplete billing setup gets 402."""
        from agency_os.service.api import app as app_module

        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="No Billing")
        tenant.metadata["stripe_customer_id"] = "cus_test"
        tenant.metadata["billing_status"] = "incomplete"
        app_module.tenant_registry.save_metadata(tenant)

        resp = TestClient(app).post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 402

    def test_streaming_response(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        lines = resp.text.strip().split("\n\n")
        # Should have data chunks + [DONE]
        assert lines[-1] == "data: [DONE]"

        # Parse first content chunk
        first_data = json.loads(lines[0].removeprefix("data: "))
        assert first_data["object"] == "chat.completion.chunk"
        assert first_data["choices"][0]["delta"]["content"] == "Hello"

    def test_streaming_always_settles_budget_and_logs_on_success(self, client):
        test_client, tenant, api_key, _ = client
        from agency_os.service.api.routers import gateway

        settle_budget = MagicMock()
        record_usage = MagicMock()
        log_request = MagicMock()
        with (
            patch.object(gateway, "_settle_budget", settle_budget),
            patch.object(gateway, "_record_usage", record_usage),
            patch.object(gateway, "_log_request", log_request),
        ):
            resp = test_client.post(
                "/api/v1/gateway/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
                headers={"X-API-Key": api_key},
            )

        assert resp.status_code == 200
        assert "data: [DONE]" in resp.text
        settle_budget.assert_called_once()
        record_usage.assert_called_once()
        ru_kwargs = record_usage.call_args.kwargs
        assert ru_kwargs["tenant"] == tenant
        assert ru_kwargs["model_id"] == "gpt-4o"
        assert ru_kwargs["tokens_in"] == 10
        assert ru_kwargs["tokens_out"] == 2
        assert "request_id" in ru_kwargs
        log_request.assert_called_once()

    def test_streaming_always_settles_budget_and_logs_on_midstream_failure(
        self, client
    ):
        test_client, tenant, api_key, mock_provider = client
        from agency_os.service.api.routers import gateway

        async def fail_midstream(*args, **kwargs):
            yield CompletionChunk(delta_content="partial", model="gpt-4o")
            raise RuntimeError("stream exploded")

        mock_provider.chat_completion_stream = fail_midstream

        settle_budget = MagicMock()
        record_usage = MagicMock()
        log_request = MagicMock()
        with (
            patch.object(gateway, "_settle_budget", settle_budget),
            patch.object(gateway, "_record_usage", record_usage),
            patch.object(gateway, "_log_request", log_request),
        ):
            resp = test_client.post(
                "/api/v1/gateway/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
                headers={"X-API-Key": api_key},
            )

        assert resp.status_code == 200
        assert "Upstream provider error" in resp.text
        assert "data: [DONE]" in resp.text
        settle_budget.assert_called_once()
        record_usage.assert_called_once()
        ru_kwargs = record_usage.call_args.kwargs
        assert ru_kwargs["tenant"] == tenant
        assert ru_kwargs["model_id"] == "gpt-4o"
        assert ru_kwargs["tokens_in"] == 0
        assert ru_kwargs["tokens_out"] == 0
        assert "request_id" in ru_kwargs
        log_request.assert_called_once()

    def test_list_models(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.get(
            "/api/v1/gateway/models",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 5  # includes "auto"
        # First model is the virtual "auto"
        assert data["data"][0]["id"] == "auto"
        # Second model has real pricing
        second_model = data["data"][1]
        assert "pricing" in second_model
        assert second_model["pricing"]["input_per_1k"] > 0

    def test_model_access_control(self, client):
        """Tenant with allowed_models can only use those models."""
        test_client, tenant, api_key, _ = client
        tenant.metadata["allowed_models"] = ["gpt-4o-mini"]

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 403

        # Cleanup
        del tenant.metadata["allowed_models"]

    def test_empty_messages_rejected(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_invalid_role_rejected(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "hacker", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_temperature_bounds(self, client):
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 5.0,
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_total_content_size_rejected(self, client):
        """Requests exceeding total content size limit get 422."""
        test_client, tenant, api_key, _ = client
        # 2 messages of 600KB each = 1.2MB > 1MB limit
        big_content = "x" * 600_000
        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "user", "content": big_content},
                    {"role": "user", "content": big_content},
                ],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422
        assert "exceeds limit" in resp.json()["detail"][0]["msg"]

    def test_auto_routing(self, client):
        """model='auto' routes to cheapest adequate model."""
        test_client, tenant, api_key, mock_provider = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "x_routed_model" in data
        assert "x_routing" in data
        assert "auto-routed" in data["x_routing"]

    def test_auto_routing_with_budget(self, client):
        """Budget hint overrides complexity classification."""
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hi"}],
                "budget": "high",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "complex" in data["x_routing"]
        assert "/quality" in data["x_routing"]

    def test_auto_routing_with_task_class(self, client):
        """Task class policy participates in model routing."""
        test_client, tenant, api_key, _ = client

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hi"}],
                "task_class": "latency",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "/latency" in data["x_routing"]

    def test_budget_limit_exceeded_rejected(self, client):
        from agency_os.service.api import app as app_module

        test_client, tenant, api_key, _ = client
        tenant.metadata["budget_limit_usd"] = 0.0
        tenant.metadata["total_spent_usd"] = 0.0

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 429
        assert "budget limit" in resp.json()["detail"]
        events = app_module.db.get_metering_events(tenant.tenant_id)
        depleted_events = [e for e in events if e["event_type"] == "budget.depleted"]
        assert len(depleted_events) == 1
        metadata = depleted_events[0]["metadata"]
        assert metadata["budget_limit_usd"] == 0.0
        assert metadata["total_spent_usd"] == 0.0
        assert metadata["attempted_cost_usd"] > 0.0

    def test_budget_reservation_released_on_provider_failure(self, client):
        test_client, tenant, api_key, mock_provider = client
        starting_spend = 0.5
        tenant.metadata["budget_limit_usd"] = 10.0
        tenant.metadata["total_spent_usd"] = starting_spend
        mock_provider.chat_completion = AsyncMock(side_effect=RuntimeError("boom"))

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 502
        assert tenant.metadata["total_spent_usd"] == pytest.approx(starting_spend)

    def test_budget_threshold_auto_pause(self, client):
        """Tenant is auto-paused when spending crosses configured threshold."""
        from agency_os.service.api import app as app_module

        test_client, tenant, api_key, _ = client
        # Configure 95% threshold with $10 limit
        tenant.metadata["budget_limit_usd"] = 10.0
        tenant.metadata["budget_pause_threshold"] = 0.95  # 95%
        tenant.metadata["total_spent_usd"] = (
            9.48  # Close to threshold, request will push over
        )
        tenant.active = True

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "user", "content": "Hello world " * 100}
                ],  # Larger request
            },
            headers={"X-API-Key": api_key},
        )

        # Should be rejected and tenant should be paused
        assert resp.status_code == 429
        assert "auto-paused" in resp.json()["detail"]
        assert "95%" in resp.json()["detail"]
        assert tenant.active is False
        assert tenant.metadata["budget_pause_notified"] is True

        # Verify threshold event was logged
        events = app_module.db.get_metering_events(tenant.tenant_id)
        threshold_events = [
            e for e in events if e["event_type"] == "budget.threshold_exceeded"
        ]
        assert len(threshold_events) == 1
        metadata = threshold_events[0]["metadata"]
        assert metadata["threshold_percent"] == 95.0
        assert metadata["budget_limit_usd"] == 10.0
        assert metadata["tenant_paused"] is True
        audit_logs = app_module.db.get_audit_log(tenant_id=tenant.tenant_id)
        deactivated = [
            log for log in audit_logs if log["action"] == "tenant.deactivated"
        ]
        assert deactivated
        detail = json.loads(deactivated[0]["detail"])
        assert detail["reason"] == "budget_threshold_exceeded"

    def test_budget_threshold_no_duplicate_notifications(self, client):
        """Once tenant is paused, subsequent requests don't trigger duplicate events."""
        from agency_os.service.api import app as app_module

        test_client, tenant, api_key, _ = client
        tenant.metadata["budget_limit_usd"] = 10.0
        tenant.metadata["budget_pause_threshold"] = 0.95
        tenant.metadata["total_spent_usd"] = 9.4
        tenant.metadata["budget_pause_notified"] = True  # Already notified
        tenant.active = False  # Already paused

        # Make request
        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )

        # Should still be rejected (tenant inactive)
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()

        # No new threshold events should be logged
        events = app_module.db.get_metering_events(tenant.tenant_id)
        threshold_events = [
            e for e in events if e["event_type"] == "budget.threshold_exceeded"
        ]
        assert len(threshold_events) == 0  # No new events

    def test_budget_threshold_default_100_percent(self, client):
        """Without threshold config, only hard limit (100%) is enforced."""
        test_client, tenant, api_key, _ = client
        tenant.metadata["budget_limit_usd"] = 10.0
        tenant.metadata["total_spent_usd"] = 9.9  # 99% spent
        # No budget_pause_threshold set (defaults to 1.0 = 100%)
        tenant.active = True

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )

        # Should succeed (below 100%)
        assert resp.status_code == 200
        assert tenant.active is True  # Not paused

    def test_cache_hit(self, client):
        """Second identical deterministic request is served from cache."""
        test_client, tenant, api_key, mock_provider = client

        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "What is 2+2?"}],
            "temperature": 0,
        }

        resp1 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json=payload,
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 200
        assert resp1.json()["x_cache"] == "MISS"
        spend_after_first = tenant.metadata.get("total_spent_usd", 0.0)

        resp2 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json=payload,
            headers={"X-API-Key": api_key},
        )
        assert resp2.status_code == 200
        assert resp2.json()["x_cache"] == "HIT"
        assert (
            resp2.json()["choices"][0]["message"]["content"] == "Hello! How can I help?"
        )
        spend_after_second = tenant.metadata.get("total_spent_usd", 0.0)
        assert spend_after_second == pytest.approx(spend_after_first)

        # Provider should only be called once (cache hit skips it)
        assert mock_provider.chat_completion.call_count == 1

    def test_cross_model_cache_hit_same_family(self, client):
        """Compatible model families can reuse cached deterministic responses."""
        test_client, tenant, api_key, mock_provider = client

        base_payload = {
            "messages": [{"role": "user", "content": "Summarize this text."}],
            "temperature": 0,
        }

        resp1 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={"model": "gpt-4o", **base_payload},
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 200
        assert resp1.json()["x_cache"] == "MISS"

        resp2 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={"model": "gpt-4o-mini", **base_payload},
            headers={"X-API-Key": api_key},
        )
        assert resp2.status_code == 200
        assert resp2.json()["x_cache"] == "CROSS_MODEL_HIT"
        assert resp2.json()["x_cache_model"] == "gpt-4o"
        assert resp2.json()["x_requested_model"] == "gpt-4o-mini"
        assert mock_provider.chat_completion.call_count == 1

    def test_cross_model_cache_miss_incompatible_family(self, client):
        """Incompatible model families must not share cache entries."""
        test_client, tenant, api_key, mock_provider = client

        base_payload = {
            "messages": [{"role": "user", "content": "Summarize this text."}],
            "temperature": 0,
        }

        resp1 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={"model": "gpt-4o", **base_payload},
            headers={"X-API-Key": api_key},
        )
        assert resp1.status_code == 200
        assert resp1.json()["x_cache"] == "MISS"

        resp2 = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={"model": "claude-haiku-3.5", **base_payload},
            headers={"X-API-Key": api_key},
        )
        assert resp2.status_code == 200
        assert resp2.json()["x_cache"] == "MISS"
        assert mock_provider.chat_completion.call_count == 2

    def test_no_cache_for_nonzero_temperature(self, client):
        """Requests with temperature > 0 bypass cache."""
        test_client, tenant, api_key, mock_provider = client

        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Tell me a joke"}],
            "temperature": 0.7,
        }

        test_client.post(
            "/api/v1/gateway/chat/completions",
            json=payload,
            headers={"X-API-Key": api_key},
        )
        test_client.post(
            "/api/v1/gateway/chat/completions",
            json=payload,
            headers={"X-API-Key": api_key},
        )

        # Provider called both times (no caching)
        assert mock_provider.chat_completion.call_count == 2

    def test_stats_endpoint(self, client):
        """GET /stats returns aggregated usage stats."""
        test_client, tenant, api_key, _ = client

        # Make a request first
        test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )

        resp = test_client.get(
            "/api/v1/gateway/stats",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] >= 1
        assert data["total_tokens_in"] > 0
        # Cache stats not exposed (global resource, no per-tenant metrics)
        assert "cache" not in data

    def test_requests_endpoint(self, client):
        """GET /requests returns recent request log."""
        test_client, tenant, api_key, _ = client

        # Make a request first
        test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )

        resp = test_client.get(
            "/api/v1/gateway/requests",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "customer_cost" in data[0]
        # Internal cost data stripped from customer-facing response
        assert "provider_cost" not in data[0]
        assert "margin" not in data[0]


class TestGatewayProviderKeyAdmin:
    @pytest.fixture()
    def admin_client(self, monkeypatch):
        from agency_os.service.api import app as app_module

        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "unit-test-secret-key")
        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="Platform Admin")
        tenant.metadata["is_platform_admin"] = True
        tenant.metadata["permissions"] = ["gateway.provider_key.admin"]
        app_module.tenant_registry.save_metadata(tenant)
        return TestClient(app), tenant, api_key

    def test_rotate_provider_key_and_audit(self, admin_client):
        client, tenant, api_key = admin_client
        _ = tenant
        rotate = client.post(
            "/api/v1/gateway/admin/provider-keys/openai/rotate",
            json={
                "api_key": "sk-rotated-value",
                "reason": "Quarterly credential rotation",
            },
            headers={
                "X-API-Key": api_key,
                "X-Manager-Approval": "true",
                "X-Approval-Reason": "Security maintenance window",
            },
        )
        assert rotate.status_code == 200
        payload = rotate.json()
        assert payload["status"] == "rotated"
        assert payload["provider"] == "openai"

        status = client.get(
            "/api/v1/gateway/admin/provider-keys",
            headers={"X-API-Key": api_key},
        )
        assert status.status_code == 200
        data = status.json()["data"]
        openai_row = next(item for item in data if item["provider"] == "openai")
        assert openai_row["configured"] is True
        assert openai_row["last_rotated_by"].startswith("tenant:")

        audit = client.get(
            "/api/v1/gateway/admin/provider-keys/audit?provider=openai",
            headers={"X-API-Key": api_key},
        )
        assert audit.status_code == 200
        events = audit.json()["events"]
        assert events
        assert events[0]["detail"]["provider"] == "openai"
        assert events[0]["detail"]["new_key_fingerprint"]

    def test_provider_key_admin_requires_platform_admin(self, monkeypatch):
        from agency_os.service.api import app as app_module

        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "unit-test-secret-key")
        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="Regular Tenant")
        tenant.metadata["permissions"] = ["gateway.provider_key.admin"]
        app_module.tenant_registry.save_metadata(tenant)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/gateway/admin/provider-keys",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 403

    def test_provider_key_admin_requires_dedicated_rbac_permission(self, monkeypatch):
        from agency_os.service.api import app as app_module

        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "unit-test-secret-key")
        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(
            name="Platform Admin Missing RBAC"
        )
        tenant.metadata["is_platform_admin"] = True
        app_module.tenant_registry.save_metadata(tenant)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/gateway/admin/provider-keys",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 403
        assert "gateway.provider_key.admin" in resp.json()["detail"]

    def test_admin_provider_key_rotation_requires_explicit_approval(self, admin_client):
        client, tenant, api_key = admin_client
        _ = tenant

        resp = client.post(
            "/api/v1/gateway/admin/provider-keys/openai/rotate",
            json={"api_key": "sk-test-rotated", "reason": "Quarterly rotation"},
            headers={"X-API-Key": api_key},
        )

        assert resp.status_code == 403
        assert "approval" in resp.json()["detail"].lower()

    def test_admin_provider_key_rotation_audited_and_cache_invalidated(
        self, monkeypatch
    ):
        from agency_os.service.api import app as app_module
        from agency_os.service.api.routers import gateway

        monkeypatch.setenv("AGENCY_OS_SECRET_KEY", "gateway-admin-rotation-secret")
        app = app_module.create_app()
        tenant, api_key = app_module.tenant_registry.register(name="Gateway Admin")
        tenant.metadata["is_platform_admin"] = True
        tenant.metadata["permissions"] = ["gateway.provider_key.admin"]
        app_module.tenant_registry.save_metadata(tenant)

        mock_registry = MagicMock(spec=ProviderRegistry)
        gateway.set_provider_registry(mock_registry)

        client = TestClient(app)
        headers = {
            "X-API-Key": api_key,
            "X-Manager-Approval": "true",
            "X-Approval-Reason": "Quarterly rotation window",
        }

        rotate_resp = client.post(
            "/api/v1/gateway/admin/provider-keys/openai/rotate",
            json={
                "api_key": "sk-admin-rotated-key",
                "reason": "Quarterly rotation window",
            },
            headers=headers,
        )
        assert rotate_resp.status_code == 200
        assert rotate_resp.json()["status"] == "rotated"
        mock_registry.invalidate.assert_called_once_with("openai")

        list_resp = client.get("/api/v1/gateway/admin/provider-keys", headers=headers)
        assert list_resp.status_code == 200
        openai_row = next(
            item for item in list_resp.json()["data"] if item["provider"] == "openai"
        )
        assert openai_row["configured"] is True
        assert openai_row["last_rotated_by"] == f"tenant:{tenant.tenant_id}"

        audit_resp = client.get(
            "/api/v1/gateway/admin/provider-keys/audit?provider=openai",
            headers=headers,
        )
        assert audit_resp.status_code == 200
        assert len(audit_resp.json()["events"]) >= 1
        latest_event = audit_resp.json()["events"][0]
        assert latest_event["resource_id"] == "openai"
        assert latest_event["detail"]["reason"] == "Quarterly rotation window"


# ------------------------------------------------------------------
# Smart router unit tests
# ------------------------------------------------------------------


class TestSmartRouter:
    def test_simple_message_classified(self):
        result = classify_complexity([{"role": "user", "content": "Hi"}])
        assert result == Complexity.SIMPLE

    def test_complex_message_classified(self):
        result = classify_complexity(
            [{"role": "user", "content": "Please analyze this code step by step"}]
        )
        assert result == Complexity.COMPLEX

    def test_long_content_is_complex(self):
        long_msg = "x " * 5000  # > LONG_MSG_TOKENS * 4 chars
        result = classify_complexity([{"role": "user", "content": long_msg}])
        assert result == Complexity.COMPLEX

    def test_short_content_is_simple(self):
        result = classify_complexity(
            [{"role": "user", "content": "Translate hello to French"}]
        )
        assert result == Complexity.SIMPLE

    def test_multi_turn_is_medium(self):
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
            {"role": "user", "content": "e"},
            {"role": "assistant", "content": "f"},
            {"role": "user", "content": "g"},
        ]
        result = classify_complexity(messages)
        assert result == Complexity.MEDIUM

    def test_router_selects_cheapest_model(self):
        config = GatewayConfig()
        router = SmartRouter(config)
        decision = router.route([{"role": "user", "content": "Hi"}])
        assert decision.complexity == Complexity.SIMPLE
        # Should pick a cheap model (nano or mini)
        assert "nano" in decision.model.model_id or "mini" in decision.model.model_id

    def test_budget_override(self):
        config = GatewayConfig()
        router = SmartRouter(config)
        decision = router.route(
            [{"role": "user", "content": "Hi"}],
            budget="high",
        )
        assert decision.complexity == Complexity.COMPLEX
        assert "/quality" in decision.reason

    def test_task_class_routing_policy(self):
        config = GatewayConfig()
        router = SmartRouter(config)
        decision = router.route(
            [{"role": "user", "content": "Translate hello to French"}],
            task_class="latency",
        )
        assert decision.complexity == Complexity.SIMPLE
        assert decision.reason.startswith("auto-routed: simple/latency")
        assert decision.model.model_id == "gpt-4.1-nano"


# ------------------------------------------------------------------
# Routing feedback tests
# ------------------------------------------------------------------


class TestRoutingFeedback:
    def test_record_and_get_stats(self):
        fb = RoutingFeedback()
        fb.record("gpt-4o", "complex", 0.9, latency_ms=300, success=True)
        fb.record("gpt-4o", "complex", 0.8, latency_ms=200, success=False)
        stats = fb.get_stats("gpt-4o", "complex")
        assert stats["count"] == 2
        assert stats["avg_score"] == 0.85
        assert stats["avg_latency_ms"] == 250.0
        assert stats["reliability"] == 0.5

    def test_ranking_with_sufficient_samples(self):
        fb = RoutingFeedback(min_samples=2)
        # Model A scores poorly
        for _ in range(3):
            fb.record("model-a", "simple", 0.3)
        # Model B scores well
        for _ in range(3):
            fb.record("model-b", "simple", 0.9)
        ranking = fb.get_model_ranking("simple", ["model-a", "model-b"])
        assert ranking == ["model-b", "model-a"]

    def test_ranking_preserves_order_for_unscored(self):
        fb = RoutingFeedback(min_samples=5)
        # Only 2 samples — below threshold
        fb.record("model-a", "simple", 0.9)
        fb.record("model-a", "simple", 0.8)
        ranking = fb.get_model_ranking("simple", ["model-a", "model-b"])
        # Both unscored (insufficient data), original order preserved
        assert ranking == ["model-a", "model-b"]

    def test_ranking_scored_before_unscored(self):
        fb = RoutingFeedback(min_samples=2)
        for _ in range(3):
            fb.record("model-b", "medium", 0.7)
        # model-a has no data
        ranking = fb.get_model_ranking("medium", ["model-a", "model-b"])
        assert ranking == ["model-b", "model-a"]

    def test_score_clamped(self):
        fb = RoutingFeedback()
        fb.record("m", "simple", -0.5)
        fb.record("m", "simple", 1.5)
        stats = fb.get_stats("m", "simple")
        assert stats["avg_score"] == 0.5  # (0.0 + 1.0) / 2

    def test_compaction(self):
        fb = RoutingFeedback(max_records=10)
        for _ in range(12):
            fb.record("m", "simple", 0.5)
        # After compaction, oldest 10% dropped
        assert fb.total_records <= 12

    def test_get_all_stats(self):
        fb = RoutingFeedback()
        fb.record("m1", "simple", 0.8)
        fb.record("m2", "complex", 0.6)
        all_stats = fb.get_all_stats()
        assert len(all_stats) == 2

    def test_empty_stats(self):
        fb = RoutingFeedback()
        stats = fb.get_stats("nonexistent", "simple")
        assert stats["count"] == 0
        assert stats["avg_score"] is None
        assert stats["avg_latency_ms"] is None
        assert stats["reliability"] is None

    def test_ranking_prefers_lower_latency_when_quality_equal(self):
        fb = RoutingFeedback(min_samples=2)
        for _ in range(3):
            fb.record("model-a", "simple", 0.8, latency_ms=500, success=True)
            fb.record("model-b", "simple", 0.8, latency_ms=120, success=True)
        ranking = fb.get_model_ranking("simple", ["model-a", "model-b"])
        assert ranking == ["model-b", "model-a"]

    def test_ranking_prefers_higher_reliability_when_quality_equal(self):
        fb = RoutingFeedback(min_samples=2)
        for _ in range(3):
            fb.record("model-a", "simple", 0.8, latency_ms=200, success=False)
            fb.record("model-b", "simple", 0.8, latency_ms=200, success=True)
        ranking = fb.get_model_ranking("simple", ["model-a", "model-b"])
        assert ranking == ["model-b", "model-a"]

    def test_ranking_uses_cost_as_tiebreaker(self):
        fb = RoutingFeedback(
            min_samples=2, model_cost_per_1k={"model-a": 0.02, "model-b": 0.002}
        )
        for _ in range(3):
            fb.record("model-a", "simple", 0.8, latency_ms=200, success=True)
            fb.record("model-b", "simple", 0.8, latency_ms=200, success=True)
        ranking = fb.get_model_ranking("simple", ["model-a", "model-b"])
        assert ranking == ["model-b", "model-a"]


class TestSmartRouterWithFeedback:
    def test_feedback_reranks_candidates(self):
        """SmartRouter prefers higher-scoring models when feedback is available."""
        config = GatewayConfig()
        fb = RoutingFeedback(min_samples=2)
        router = SmartRouter(config, feedback=fb)

        # Record that gpt-4o-mini (usually first for SIMPLE) scores poorly
        # and gpt-4.1-nano scores well
        for _ in range(5):
            fb.record("gpt-4o-mini", "simple", 0.3)
            fb.record("gpt-4.1-nano", "simple", 0.95)

        decision = router.route(
            [{"role": "user", "content": "Translate hello to French"}]
        )
        assert decision.complexity == Complexity.SIMPLE
        # Should prefer gpt-4.1-nano (highest scored) over gpt-4o-mini
        assert decision.model.model_id == "gpt-4.1-nano"

    def test_fallback_to_heuristic_without_feedback(self):
        """Without feedback data, SmartRouter uses default tier ordering."""
        config = GatewayConfig()
        fb = RoutingFeedback(min_samples=100)  # high threshold = no scored models
        router = SmartRouter(config, feedback=fb)

        decision = router.route([{"role": "user", "content": "Hi"}])
        assert decision.complexity == Complexity.SIMPLE
        # Default order: gpt-4.1-nano first
        assert decision.model.model_id == "gpt-4.1-nano"

    def test_no_feedback_object(self):
        """SmartRouter works normally without any feedback object."""
        config = GatewayConfig()
        router = SmartRouter(config)
        decision = router.route([{"role": "user", "content": "Hi"}])
        assert decision.model is not None


# ------------------------------------------------------------------
# Response cache unit tests
# ------------------------------------------------------------------


class TestResponseCache:
    def test_put_and_get(self):
        cache = ResponseCache()
        cache.put("key1", {"content": "hello"}, "gpt-4o", 10, 5)
        entry = cache.get("key1")
        assert entry is not None
        assert entry.response["content"] == "hello"
        assert entry.tokens_in == 10

    def test_miss_returns_none(self):
        cache = ResponseCache()
        assert cache.get("nonexistent") is None

    def test_expired_entry_evicted(self):
        cache = ResponseCache(default_ttl=0.0)  # immediate expiry
        cache.put("key1", {"content": "hello"}, "gpt-4o", 10, 5)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = ResponseCache(max_entries=2)
        cache.put("k1", {"a": 1}, "m", 1, 1)
        cache.put("k2", {"b": 2}, "m", 1, 1)
        cache.put("k3", {"c": 3}, "m", 1, 1)  # evicts k1
        assert cache.get("k1") is None
        assert cache.get("k2") is not None
        assert cache.get("k3") is not None

    def test_stats_tracking(self):
        cache = ResponseCache()
        cache.put("k1", {"a": 1}, "m", 1, 1)
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_key_deterministic(self):
        msgs = [{"role": "user", "content": "Hello"}]
        k1 = ResponseCache.cache_key(msgs, "gpt-4o", temperature=0)
        k2 = ResponseCache.cache_key(msgs, "gpt-4o", temperature=0)
        assert k1 == k2

    def test_cache_key_differs_by_tenant(self):
        msgs = [{"role": "user", "content": "Hello"}]
        k1 = ResponseCache.cache_key(msgs, "gpt-4o", tenant_id="tenant-a")
        k2 = ResponseCache.cache_key(msgs, "gpt-4o", tenant_id="tenant-b")
        assert k1 != k2

    def test_cache_key_differs_by_model(self):
        msgs = [{"role": "user", "content": "Hello"}]
        k1 = ResponseCache.cache_key(msgs, "gpt-4o")
        k2 = ResponseCache.cache_key(msgs, "gpt-4o-mini")
        assert k1 != k2

    def test_cache_key_differs_by_top_p(self):
        msgs = [{"role": "user", "content": "Hello"}]
        k1 = ResponseCache.cache_key(msgs, "gpt-4o", top_p=1.0)
        k2 = ResponseCache.cache_key(msgs, "gpt-4o", top_p=0.9)
        assert k1 != k2

    def test_cache_key_differs_by_stop(self):
        msgs = [{"role": "user", "content": "Hello"}]
        k1 = ResponseCache.cache_key(msgs, "gpt-4o", stop=["END"])
        k2 = ResponseCache.cache_key(msgs, "gpt-4o", stop=["DONE"])
        assert k1 != k2

    def test_cost_saved_tracking(self):
        cache = ResponseCache()
        cache.record_cost_saved(0.005)
        cache.record_cost_saved(0.003)
        assert cache.stats["cost_saved_usd"] == 0.008

    def test_similarity_hit_same_meaning(self):
        """Similar prompts should match via similarity cache."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs_a = [
            {
                "role": "user",
                "content": "Please summarize the following article about machine learning and artificial intelligence trends in 2026",
            }
        ]
        msgs_b = [
            {
                "role": "user",
                "content": "Please summarize the following article about artificial intelligence and machine learning trends in 2026",
            }
        ]
        key_a = cache.cache_key(msgs_a, "gpt-4o", tenant_id="t1")
        cache.put(
            key_a,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs_a,
            max_tokens=None,
            tenant_id="t1",
        )
        # Exact miss on msgs_b
        key_b = cache.cache_key(msgs_b, "gpt-4o", tenant_id="t1")
        assert cache.get(key_b) is None
        # Similarity hit
        result = cache.get_similar(msgs_b, "gpt-4o", tenant_id="t1")
        assert result is not None
        assert result.response == {"resp": 1}
        assert cache.stats["similarity_hits"] == 1

    def test_similarity_miss_different_meaning(self):
        """Very different prompts should not match."""
        cache = ResponseCache(similarity_threshold=0.85)
        msgs_a = [{"role": "user", "content": "What is the capital of France?"}]
        msgs_b = [
            {"role": "user", "content": "Explain quantum computing in detail please"}
        ]
        key_a = cache.cache_key(msgs_a, "gpt-4o", tenant_id="t1")
        cache.put(
            key_a,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs_a,
            tenant_id="t1",
        )
        result = cache.get_similar(msgs_b, "gpt-4o", tenant_id="t1")
        assert result is None

    def test_similarity_tenant_isolation(self):
        """Similarity lookups must not cross tenant boundaries."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4o", tenant_id="tenant-a")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs,
            tenant_id="tenant-a",
        )
        # Same prompt, different tenant — should NOT match
        result = cache.get_similar(msgs, "gpt-4o", tenant_id="tenant-b")
        assert result is None

    def test_similarity_model_isolation(self):
        """Similarity lookups must match on model."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4o", tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs,
            tenant_id="t1",
        )
        result = cache.get_similar(msgs, "gpt-4o-mini", tenant_id="t1")
        assert result is None

    def test_similarity_allows_same_family_when_enabled(self):
        """Cross-model reuse allowed within compatible families when enabled."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4o", tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs,
            tenant_id="t1",
        )
        result = cache.get_similar(
            msgs,
            "gpt-4o-mini",
            tenant_id="t1",
            allow_model_family_match=True,
        )
        assert result is not None
        assert result.model_id == "gpt-4o"

    def test_similarity_rejects_lower_tier_cached_model(self):
        """Do not reuse lower-tier cache entries for higher-tier requests."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4.1-mini", tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4.1-mini",
            10,
            5,
            messages=msgs,
            tenant_id="t1",
        )
        result = cache.get_similar(
            msgs,
            "gpt-4.1",
            tenant_id="t1",
            allow_model_family_match=True,
        )
        assert result is None

    def test_similarity_allows_open_model_cross_provider_family(self):
        """Same-base-model variants across providers can share similarity cache."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "Explain transformers briefly."}]
        key = cache.cache_key(msgs, "llama-3.1-70b", tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "llama-3.1-70b",
            10,
            5,
            messages=msgs,
            tenant_id="t1",
        )
        result = cache.get_similar(
            msgs,
            "fireworks-llama-3.1-70b",
            tenant_id="t1",
            allow_model_family_match=True,
        )
        assert result is not None
        assert result.model_id == "llama-3.1-70b"

    def test_similarity_top_p_isolation(self):
        """Similarity lookups must match on top_p."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4o", top_p=1.0, tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs,
            top_p=1.0,
            tenant_id="t1",
        )
        result = cache.get_similar(msgs, "gpt-4o", top_p=0.9, tenant_id="t1")
        assert result is None

    def test_similarity_stop_isolation(self):
        """Similarity lookups must match on stop sequence."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        key = cache.cache_key(msgs, "gpt-4o", stop=["END"], tenant_id="t1")
        cache.put(
            key,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs,
            stop=["END"],
            tenant_id="t1",
        )
        result = cache.get_similar(msgs, "gpt-4o", stop=["DONE"], tenant_id="t1")
        assert result is None

    def test_similarity_stats_tracked(self):
        """Similarity hits are tracked separately from exact hits."""
        cache = ResponseCache(similarity_threshold=0.5)
        msgs_a = [{"role": "user", "content": "What is the capital of France?"}]
        msgs_b = [{"role": "user", "content": "What is the capital city of France?"}]
        key_a = cache.cache_key(msgs_a, "gpt-4o", tenant_id="t1")
        cache.put(
            key_a,
            {"resp": 1},
            "gpt-4o",
            10,
            5,
            messages=msgs_a,
            tenant_id="t1",
        )
        # Exact hit
        cache.get(key_a)
        # Similarity hit
        cache.get_similar(msgs_b, "gpt-4o", tenant_id="t1")
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["similarity_hits"] == 1
        assert stats["similarity_index_size"] == 1

    def test_similarity_eviction_cleans_index(self):
        """When entries are evicted, their similarity index entries are removed too."""
        cache = ResponseCache(max_entries=2, similarity_threshold=0.5)
        for i in range(3):
            msgs = [
                {"role": "user", "content": f"prompt number {i} with some words here"}
            ]
            key = cache.cache_key(msgs, "gpt-4o", tenant_id="t1")
            cache.put(
                key,
                {"resp": i},
                "gpt-4o",
                10,
                5,
                messages=msgs,
                tenant_id="t1",
            )
        assert cache.stats["entries"] == 2
        assert cache.stats["similarity_index_size"] == 2


# ------------------------------------------------------------------
# Failover tests
# ------------------------------------------------------------------


def _mock_result(content: str = "OK") -> CompletionResult:
    return CompletionResult(
        content=content,
        model="test",
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )


class TestFailover:
    @pytest.fixture()
    def failover_deps(self):
        """Set up GatewayConfig, ProviderRegistry, and mock providers for failover tests."""
        config = GatewayConfig()

        primary = AsyncMock()
        fallback = AsyncMock()

        registry = MagicMock(spec=ProviderRegistry)

        def get_provider(name, base_url=None):
            if name == "openai":
                return primary
            if name == "anthropic":
                return fallback
            return None

        registry.get.side_effect = get_provider
        return config, registry, primary, fallback

    @pytest.mark.asyncio()
    async def test_success_no_retry(self, failover_deps):
        """Successful call returns immediately without retry."""
        config, registry, primary, _ = failover_deps
        primary.chat_completion.return_value = _mock_result("hello")

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
        )

        assert result.result.content == "hello"
        assert not result.failed_over
        assert result.attempts == 1
        assert len(result.errors) == 0

    @pytest.mark.asyncio()
    async def test_retry_on_timeout(self, failover_deps):
        """Retries on timeout, succeeds on second attempt."""
        config, registry, primary, _ = failover_deps
        primary.chat_completion.side_effect = [
            httpx.ReadTimeout("timeout"),
            _mock_result("recovered"),
        ]

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            retry_delay=0.0,
        )

        assert result.result.content == "recovered"
        assert not result.failed_over
        assert result.attempts == 2

    @pytest.mark.asyncio()
    async def test_failover_to_other_provider(self, failover_deps):
        """Falls back to Anthropic when OpenAI exhausts retries."""
        config, registry, primary, fallback = failover_deps
        primary.chat_completion.side_effect = httpx.ReadTimeout("timeout")
        fallback.chat_completion.return_value = _mock_result("from anthropic")

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            max_retries=1,
            retry_delay=0.0,
        )

        assert result.result.content == "from anthropic"
        assert result.failed_over
        assert result.original_model == "gpt-4o"
        assert result.model_config.model_id == "claude-sonnet-4"

    @pytest.mark.asyncio()
    async def test_no_retry_on_non_retryable(self, failover_deps):
        """Non-retryable errors skip to failover immediately."""
        config, registry, primary, fallback = failover_deps

        # 400 Bad Request is not retryable
        resp = httpx.Response(400, request=httpx.Request("POST", "http://test"))
        primary.chat_completion.side_effect = httpx.HTTPStatusError(
            "bad request", request=resp.request, response=resp
        )
        fallback.chat_completion.return_value = _mock_result("fallback")

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            max_retries=2,
            retry_delay=0.0,
        )

        # Should have only tried primary once (no retries for 400)
        assert primary.chat_completion.call_count == 1
        assert result.failed_over
        assert result.result.content == "fallback"

    @pytest.mark.asyncio()
    async def test_retry_on_429(self, failover_deps):
        """429 rate limit is retryable."""
        config, registry, primary, _ = failover_deps

        resp = httpx.Response(429, request=httpx.Request("POST", "http://test"))
        primary.chat_completion.side_effect = [
            httpx.HTTPStatusError("rate limited", request=resp.request, response=resp),
            _mock_result("after rate limit"),
        ]

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            retry_delay=0.0,
        )

        assert result.result.content == "after rate limit"
        assert not result.failed_over
        assert result.attempts == 2

    @pytest.mark.asyncio()
    async def test_all_providers_fail_raises(self, failover_deps):
        """Raises RuntimeError when all providers and fallbacks fail."""
        config, registry, primary, fallback = failover_deps
        primary.chat_completion.side_effect = httpx.ReadTimeout("timeout")
        fallback.chat_completion.side_effect = httpx.ReadTimeout("also timeout")

        model = config.get_model("gpt-4o")
        with pytest.raises(RuntimeError, match="All providers failed"):
            await call_with_failover(
                provider=primary,
                model_config=model,
                messages=[{"role": "user", "content": "hi"}],
                gateway_config=config,
                provider_registry=registry,
                max_retries=0,
                retry_delay=0.0,
            )

    @pytest.mark.asyncio()
    async def test_errors_tracked(self, failover_deps):
        """All errors are tracked in the result."""
        config, registry, primary, fallback = failover_deps
        primary.chat_completion.side_effect = httpx.ReadTimeout("primary down")
        fallback.chat_completion.return_value = _mock_result("ok")

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            max_retries=0,
            retry_delay=0.0,
        )

        assert len(result.errors) == 1
        assert "ReadTimeout" in result.errors[0]

    @pytest.mark.asyncio()
    async def test_errors_do_not_include_raw_exception_details(self, failover_deps):
        """Tracked errors are sanitized to type-only labels."""
        config, registry, primary, fallback = failover_deps
        primary.chat_completion.side_effect = RuntimeError(
            "token=sk-live-secret should-not-appear"
        )
        fallback.chat_completion.return_value = _mock_result("ok")

        model = config.get_model("gpt-4o")
        result = await call_with_failover(
            provider=primary,
            model_config=model,
            messages=[{"role": "user", "content": "hi"}],
            gateway_config=config,
            provider_registry=registry,
            max_retries=0,
            retry_delay=0.0,
        )

        assert len(result.errors) == 1
        assert result.errors[0] == "gpt-4o: RuntimeError"
        assert "sk-live-secret" not in result.errors[0]


class TestFailoverIntegration:
    """Test failover through the gateway HTTP endpoint."""

    @pytest.fixture()
    def client_with_failover(self):
        from agency_os.service.api import app as app_module
        from agency_os.service.api.routers import gateway

        app = app_module.create_app()

        tenant, api_key = app_module.tenant_registry.register(name="Failover Test")
        tenant.metadata["stripe_customer_id"] = "cus_fo_test"
        tenant.metadata["billing_status"] = "active"
        app_module.tenant_registry.save_metadata(tenant)

        # Primary provider always fails
        primary = AsyncMock()
        primary.chat_completion.side_effect = httpx.ReadTimeout("timeout")

        # Fallback provider works
        fallback = AsyncMock()
        fallback.chat_completion.return_value = CompletionResult(
            content="Fallback response",
            model="claude-sonnet-4-20250514",
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

        mock_registry = MagicMock(spec=ProviderRegistry)

        def get_provider(name, base_url=None):
            if name == "openai":
                return primary
            if name == "anthropic":
                return fallback
            return None

        mock_registry.get.side_effect = get_provider
        gateway.set_provider_registry(mock_registry)

        return TestClient(app), api_key, primary, fallback

    def test_failover_response_includes_metadata(self, client_with_failover):
        """HTTP response includes failover metadata when primary fails."""
        test_client, api_key, _, _ = client_with_failover

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["x_failover"] is True
        assert data["x_original_model"] == "gpt-4o"
        assert data["model"] == "claude-sonnet-4"
        assert data["choices"][0]["message"]["content"] == "Fallback response"

    def test_streaming_retries_once_before_fallback(self, client_with_failover):
        """Streaming retries the same provider once before fallback."""
        test_client, api_key, primary, fallback = client_with_failover
        calls = {"primary": 0, "fallback": 0}

        async def primary_stream(*args, **kwargs):
            calls["primary"] += 1
            if calls["primary"] == 1:
                raise httpx.ReadTimeout("timeout")
            yield CompletionChunk(delta_content="Recovered", model="gpt-4o")
            yield CompletionChunk(
                delta_content="",
                model="gpt-4o",
                finish_reason="stop",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                ),
            )

        async def fallback_stream(*args, **kwargs):
            calls["fallback"] += 1
            yield CompletionChunk(delta_content="Fallback", model="claude-sonnet-4")
            yield CompletionChunk(
                delta_content="",
                model="claude-sonnet-4",
                finish_reason="stop",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                ),
            )

        primary.chat_completion_stream = primary_stream
        fallback.chat_completion_stream = fallback_stream

        resp = test_client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        assert calls["primary"] == 2
        assert calls["fallback"] == 0
        assert "Recovered" in resp.text
        assert "data: [DONE]" in resp.text
