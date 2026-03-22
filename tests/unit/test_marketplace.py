"""Tests for the SWARM marketplace — service catalog, worker agents, ACP, and router."""

from __future__ import annotations

import pytest

from agency_os.marketplace.acp import ACPClient, EscrowState, generate_agreement_hash
from agency_os.marketplace.catalog import (
    PricingModel,
    ServiceCatalog,
    ServiceCategory,
    ServicePricing,
    ServiceSLA,
    SwarmService,
)
from agency_os.marketplace.router import ACPRequestRouter, ServiceRequest
from agency_os.marketplace.worker_agent import JobStatus, SwarmWorkerAgent

# -- Fixtures --


def _make_service(
    service_id: str = "test_service",
    category: ServiceCategory = ServiceCategory.SAFETY,
    base_price: float = 10.0,
    handler: str = "agency_os.marketplace.handlers.run_escalation_simulation",
) -> SwarmService:
    return SwarmService(
        service_id=service_id,
        name=f"Test {service_id}",
        description="A test SWARM service",
        category=category,
        capabilities=["test_capability", "safety_check"],
        swarm_module="swarm.test",
        handler=handler,
        pricing=ServicePricing(
            model=PricingModel.FLAT,
            base_price_usd=base_price,
        ),
        sla=ServiceSLA(max_latency_seconds=30.0),
        tags=["test", "safety"],
    )


def _echo_handler(**kwargs):
    """Simple handler that echoes inputs as outputs for testing."""
    return {
        "summary": "Echo result",
        "metrics": {"echoed_params": len(kwargs)},
        "input": kwargs,
    }


# -- ServiceCatalog tests --


class TestServiceCatalog:
    def test_register_and_get(self):
        catalog = ServiceCatalog()
        service = _make_service()
        catalog.register(service)

        result = catalog.get("test_service")
        assert result is not None
        assert result.service_id == "test_service"
        assert result.name == "Test test_service"

    def test_get_unknown_returns_none(self):
        catalog = ServiceCatalog()
        assert catalog.get("nonexistent") is None

    def test_list_by_category(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("s1", ServiceCategory.SAFETY))
        catalog.register(_make_service("s2", ServiceCategory.GOVERNANCE))
        catalog.register(_make_service("s3", ServiceCategory.SAFETY))

        safety = catalog.list_services(category=ServiceCategory.SAFETY)
        assert len(safety) == 2
        gov = catalog.list_services(category=ServiceCategory.GOVERNANCE)
        assert len(gov) == 1

    def test_list_by_capability(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("s1"))
        results = catalog.list_services(capability="safety_check")
        assert len(results) == 1

    def test_list_by_tag(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("s1"))
        results = catalog.list_services(tag="safety")
        assert len(results) == 1
        results = catalog.list_services(tag="nonexistent")
        assert len(results) == 0

    def test_record_invocation_and_stats(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("s1"))
        catalog.record_invocation("s1", latency_seconds=1.5, revenue_usd=10.0)
        catalog.record_invocation("s1", latency_seconds=2.5, revenue_usd=15.0)
        stats = catalog.get_stats("s1")
        assert stats["total_invocations"] == 2
        assert stats["total_revenue_usd"] == 25.0
        assert stats["avg_latency_seconds"] == pytest.approx(2.0)

    def test_catalog_summary(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("s1"))
        summary = catalog.catalog_summary()
        assert len(summary) == 1
        assert summary[0]["service_id"] == "s1"

    def test_load_builtin_services(self):
        catalog = ServiceCatalog()
        count = catalog.load_builtin_services()
        assert count >= 5  # We created 6 YAML files

    def test_disabled_service_filtered(self):
        catalog = ServiceCatalog()
        service = _make_service("disabled")
        service.enabled = False
        catalog.register(service)
        assert len(catalog.list_services(enabled_only=True)) == 0
        assert len(catalog.list_services(enabled_only=False)) == 1


class TestServicePricing:
    def test_flat_pricing(self):
        pricing = ServicePricing(model=PricingModel.FLAT, base_price_usd=15.0)
        assert pricing.compute_cost(1) == 15.0
        assert pricing.compute_cost(100) == 15.0

    def test_per_iteration_pricing(self):
        pricing = ServicePricing(
            model=PricingModel.PER_ITERATION,
            base_price_usd=10.0,
            per_unit_usd=2.0,
        )
        assert pricing.compute_cost(5) == 20.0
        assert pricing.compute_cost(1) == 12.0

    def test_price_clamping(self):
        pricing = ServicePricing(
            model=PricingModel.PER_ITERATION,
            base_price_usd=10.0,
            per_unit_usd=100.0,
            max_price_usd=50.0,
        )
        assert pricing.compute_cost(10) == 50.0  # Clamped to max


class TestSwarmServiceManifest:
    def test_to_acp_manifest(self):
        service = _make_service("test_svc", base_price=20.0)
        manifest = service.to_acp_manifest()
        assert manifest["agent_id"] == "swarm_test_svc"
        assert "test_capability" in manifest["capabilities"]
        assert manifest["pricing"]["base"] == 20.0
        assert manifest["pricing"]["currency"] == "USDC"


# -- SwarmWorkerAgent tests --


class TestSwarmWorkerAgent:
    def test_register_handler_and_execute(self):
        catalog = ServiceCatalog()
        service = _make_service("echo_svc")
        catalog.register(service)

        worker = SwarmWorkerAgent(
            agent_id="worker-1", catalog=catalog, service_ids=["echo_svc"]
        )
        worker.register_handler("echo_svc", _echo_handler)

        assert worker.can_handle("echo_svc")
        assert not worker.can_handle("unknown_svc")

        job = worker.submit_job(
            service_id="echo_svc",
            client_agent_id="client-1",
            input_params={"foo": "bar"},
        )
        assert job.status == JobStatus.COMPLETED
        assert job.result["summary"] == "Echo result"
        assert job.cost_usd == 10.0

    def test_job_failure_tracking(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("fail_svc"))

        def fail_handler(**kwargs):
            raise RuntimeError("Intentional failure")

        worker = SwarmWorkerAgent(
            agent_id="worker-2", catalog=catalog, service_ids=["fail_svc"]
        )
        worker.register_handler("fail_svc", fail_handler)

        job = worker.submit_job("fail_svc", "client-1", {})
        assert job.status == JobStatus.FAILED
        assert "Intentional failure" in job.error

        stats = worker.stats()
        assert stats["failed_jobs"] == 1
        assert stats["success_rate"] == 0.0

    def test_unknown_service_raises(self):
        catalog = ServiceCatalog()
        worker = SwarmWorkerAgent(agent_id="w", catalog=catalog)
        with pytest.raises(ValueError, match="Unknown service"):
            worker.submit_job("nonexistent", "c", {})

    def test_stats(self):
        catalog = ServiceCatalog()
        catalog.register(_make_service("svc"))
        worker = SwarmWorkerAgent(
            agent_id="worker-3", catalog=catalog, service_ids=["svc"]
        )
        worker.register_handler("svc", _echo_handler)
        worker.submit_job("svc", "client-1", {})
        worker.submit_job("svc", "client-2", {"x": 1})

        stats = worker.stats()
        assert stats["total_jobs"] == 2
        assert stats["total_revenue_usd"] == 20.0


# -- ACPClient tests --


class TestACPClient:
    def test_register_and_discover(self):
        acp = ACPClient()
        manifest = {
            "agent_id": "swarm_safety",
            "capabilities": ["escalation_simulation", "alignment_test"],
            "category": "safety",
            "pricing": {"base": 15.0},
        }
        reg = acp.register_service("swarm_safety", manifest)
        assert reg.active

        results = acp.discover(capability="escalation")
        assert len(results) == 1
        assert results[0]["provider_agent_id"] == "swarm_safety"

    def test_discover_with_price_filter(self):
        acp = ACPClient()
        acp.register_service(
            "cheap", {"capabilities": ["test"], "pricing": {"base": 5.0}}
        )
        acp.register_service(
            "expensive", {"capabilities": ["test"], "pricing": {"base": 50.0}}
        )

        results = acp.discover(max_price_usd=10.0)
        assert len(results) == 1

    def test_discover_inactive_filtered(self):
        acp = ACPClient()
        acp.register_service("agent1", {"capabilities": ["test"]})
        acp.unregister_service("agent1")

        results = acp.discover()
        assert len(results) == 0

    def test_escrow_lifecycle_success(self):
        acp = ACPClient(platform_fee_rate=0.10)
        acp.register_service("provider", {"capabilities": ["test"]})

        escrow = acp.create_escrow("client", "provider", "svc", 100.0)
        assert escrow.state == EscrowState.CREATED

        assert acp.mark_executing(escrow.escrow_id)
        assert acp.get_escrow(escrow.escrow_id).state == EscrowState.EXECUTING

        assert acp.submit_evaluation(escrow.escrow_id, score=0.9)
        assert acp.get_escrow(escrow.escrow_id).state == EscrowState.EVALUATING

        settlement = acp.settle(escrow.escrow_id, tx_hash="0xabc123")
        assert settlement["state"] == "settled"
        assert settlement["provider_payout_usd"] == 90.0
        assert settlement["platform_fee_usd"] == 10.0
        assert settlement["tx_hash"] == "0xabc123"

    def test_escrow_refund_on_low_score(self):
        acp = ACPClient()
        escrow = acp.create_escrow("client", "provider", "svc", 50.0)
        acp.mark_executing(escrow.escrow_id)
        acp.submit_evaluation(escrow.escrow_id, score=0.2)
        settlement = acp.settle(escrow.escrow_id)
        assert settlement["state"] == "refunded"
        assert settlement["refund_amount_usd"] == 50.0

    def test_escrow_expiry(self):
        acp = ACPClient(escrow_ttl_seconds=0.0)  # Immediate expiry
        escrow = acp.create_escrow("c", "p", "s", 10.0)
        expired = acp.expire_stale_escrows()
        assert escrow.escrow_id in expired
        assert acp.get_escrow(escrow.escrow_id).state == EscrowState.EXPIRED

    def test_platform_stats(self):
        acp = ACPClient()
        acp.register_service("a1", {"capabilities": ["test"]})
        acp.register_service("a2", {"capabilities": ["test"]})
        stats = acp.platform_stats()
        assert stats["active_providers"] == 2
        assert stats["total_registrations"] == 2

    def test_reputation_update(self):
        acp = ACPClient(platform_fee_rate=0.0)
        acp.register_service("provider", {"capabilities": ["test"]})

        escrow = acp.create_escrow("client", "provider", "svc", 10.0)
        acp.mark_executing(escrow.escrow_id)
        acp.submit_evaluation(escrow.escrow_id, score=0.8)
        acp.settle(escrow.escrow_id)

        reg = acp._registrations["provider"]
        assert reg.total_jobs_completed == 1
        assert reg.reputation_score == pytest.approx(0.8)


class TestAgreementHash:
    def test_deterministic(self):
        h1 = generate_agreement_hash("c1", "p1", "svc", 10.0)
        h2 = generate_agreement_hash("c1", "p1", "svc", 10.0)
        assert h1 == h2

    def test_different_inputs(self):
        h1 = generate_agreement_hash("c1", "p1", "svc", 10.0)
        h2 = generate_agreement_hash("c2", "p1", "svc", 10.0)
        assert h1 != h2


# -- ACPRequestRouter tests --


class TestACPRequestRouter:
    def _setup_router(self):
        catalog = ServiceCatalog()
        service = _make_service("test_svc", base_price=10.0)
        catalog.register(service)

        acp = ACPClient()
        router = ACPRequestRouter(catalog=catalog, acp_client=acp)

        worker = SwarmWorkerAgent(
            agent_id="worker-1", catalog=catalog, service_ids=["test_svc"]
        )
        worker.register_handler("test_svc", _echo_handler)
        router.register_worker(worker)

        acp.register_service("worker-1", service.to_acp_manifest())
        return router

    def test_successful_request(self):
        router = self._setup_router()
        request = ServiceRequest(
            request_id="req-001",
            client_agent_id="buyer-agent",
            service_id="test_svc",
            input_params={"foo": "bar"},
        )
        response = router.handle_request(request)
        assert response.status == "completed"
        assert response.cost_usd == 10.0
        assert response.escrow_id is not None
        assert response.result["summary"] == "Echo result"

    def test_unknown_service_rejected(self):
        router = self._setup_router()
        request = ServiceRequest(
            request_id="req-002",
            client_agent_id="buyer",
            service_id="nonexistent",
            input_params={},
        )
        response = router.handle_request(request)
        assert response.status == "rejected"
        assert "not found" in response.error.lower()

    def test_price_exceeded_rejected(self):
        router = self._setup_router()
        request = ServiceRequest(
            request_id="req-003",
            client_agent_id="buyer",
            service_id="test_svc",
            input_params={},
            max_price_usd=1.0,
        )
        response = router.handle_request(request)
        assert response.status == "rejected"
        assert "exceeds" in response.error.lower()

    def test_request_log_summary(self):
        router = self._setup_router()
        for i in range(3):
            router.handle_request(
                ServiceRequest(
                    request_id=f"req-{i}",
                    client_agent_id="buyer",
                    service_id="test_svc",
                    input_params={},
                )
            )
        summary = router.request_log_summary()
        assert summary["total_requests"] == 3
        assert summary["total_revenue_usd"] == 30.0
        assert "test_svc" in summary["by_service"]

    def test_certification_for_safety_service(self):
        catalog = ServiceCatalog()
        service = _make_service(
            "safety_svc", category=ServiceCategory.SAFETY, base_price=10.0
        )
        catalog.register(service)

        acp = ACPClient()
        router = ACPRequestRouter(catalog=catalog, acp_client=acp)

        def safety_handler(**kwargs):
            return {
                "summary": "Safety check passed",
                "risk_score": 0.12,
                "alignment_score": 0.85,
                "metrics": {"checks": 5},
            }

        worker = SwarmWorkerAgent(
            agent_id="safety-worker", catalog=catalog, service_ids=["safety_svc"]
        )
        worker.register_handler("safety_svc", safety_handler)
        router.register_worker(worker)
        acp.register_service("safety-worker", service.to_acp_manifest())

        response = router.handle_request(
            ServiceRequest(
                request_id="req-cert",
                client_agent_id="buyer",
                service_id="safety_svc",
                input_params={},
            )
        )
        assert response.status == "completed"
        assert response.certification is not None
        assert response.certification["certified_by"] == "SWARM Safety Oracle"
        assert response.certification["risk_score"] == 0.12
        assert response.certification["alignment_grade"] in (
            "A",
            "A-",
            "B+",
            "B",
            "C",
            "F",
        )


# -- Security hardening tests --


class TestInputValidation:
    """Tests for C2: input parameter validation and sanitization."""

    def test_forbidden_params_rejected(self):
        from agency_os.marketplace.worker_agent import _validate_input_params

        with pytest.raises(ValueError, match="Forbidden parameter"):
            _validate_input_params({"__class__": "exploit"}, {})

    def test_undeclared_params_stripped(self):
        from agency_os.marketplace.worker_agent import _validate_input_params

        schema = {"properties": {"allowed": {"type": "string"}}}
        result = _validate_input_params({"allowed": "good", "secret": "bad"}, schema)
        assert "allowed" in result
        assert "secret" not in result

    def test_type_mismatch_uses_default(self):
        from agency_os.marketplace.worker_agent import _validate_input_params

        schema = {"properties": {"count": {"type": "integer", "default": 5}}}
        result = _validate_input_params({"count": "not_a_number"}, schema)
        assert result["count"] == 5

    def test_enum_constraint_enforced(self):
        from agency_os.marketplace.worker_agent import _validate_input_params

        schema = {
            "properties": {
                "level": {"type": "string", "enum": ["low", "high"], "default": "low"}
            }
        }
        result = _validate_input_params({"level": "INVALID"}, schema)
        assert result["level"] == "low"

    def test_no_schema_strips_internal_keys(self):
        from agency_os.marketplace.worker_agent import _validate_input_params

        result = _validate_input_params({"public": 1, "_internal": 2}, {})
        assert "public" in result
        assert "_internal" not in result


class TestHandlerAllowlist:
    """Tests for C3: handler path allowlisting."""

    def test_disallowed_handler_not_resolved(self):
        catalog = ServiceCatalog()
        service = _make_service(
            "evil_svc",
            handler="os.system",  # Not in allowlist
        )
        catalog.register(service)
        worker = SwarmWorkerAgent(
            agent_id="w", catalog=catalog, service_ids=["evil_svc"]
        )
        assert not worker.can_handle("evil_svc")


class TestEscrowSecurity:
    """Tests for H4: fund verification and escrow bounds."""

    def test_negative_amount_rejected(self):
        acp = ACPClient()
        with pytest.raises(ValueError, match="positive"):
            acp.create_escrow("c", "p", "s", -5.0)

    def test_excessive_amount_rejected(self):
        acp = ACPClient()
        with pytest.raises(ValueError, match="maximum"):
            acp.create_escrow("c", "p", "s", 50000.0)

    def test_insufficient_funds_rejected(self):
        class FakeBalanceChecker:
            def get_balance(self, agent_id: str) -> float:
                return 5.0

        acp = ACPClient(balance_checker=FakeBalanceChecker())
        with pytest.raises(ValueError, match="Insufficient funds"):
            acp.create_escrow("c", "p", "s", 100.0)

    def test_evaluation_score_clamped(self):
        acp = ACPClient()
        escrow = acp.create_escrow("c", "p", "s", 10.0)
        acp.mark_executing(escrow.escrow_id)
        acp.submit_evaluation(escrow.escrow_id, score=5.0)
        assert acp.get_escrow(escrow.escrow_id).evaluation_score == 1.0

    def test_evaluation_score_clamped_negative(self):
        acp = ACPClient()
        escrow = acp.create_escrow("c", "p", "s", 10.0)
        acp.mark_executing(escrow.escrow_id)
        acp.submit_evaluation(escrow.escrow_id, score=-2.0)
        assert acp.get_escrow(escrow.escrow_id).evaluation_score == 0.0


class TestAgreementHashSecurity:
    """Tests for M1: full SHA-256 hash."""

    def test_full_sha256_length(self):
        h = generate_agreement_hash("c1", "p1", "svc", 10.0)
        assert len(h) == 64  # Full SHA-256 hex digest


class TestMemoryBounds:
    """Tests for M3: bounded in-memory stores."""

    def test_escrow_eviction(self):
        from agency_os.marketplace.acp import MAX_ESCROWS

        acp = ACPClient()
        # Fill with terminal escrows
        for _i in range(100):
            e = acp.create_escrow("c", "p", "s", 1.0)
            acp.mark_executing(e.escrow_id)
            acp.submit_evaluation(e.escrow_id, score=0.9)
            acp.settle(e.escrow_id)
        # Should not exceed max
        assert len(acp._escrows) <= MAX_ESCROWS

    def test_request_log_bounded(self):
        from agency_os.marketplace.router import MAX_REQUEST_LOG

        catalog = ServiceCatalog()
        catalog.register(_make_service("svc"))
        acp = ACPClient()
        router = ACPRequestRouter(catalog=catalog, acp_client=acp)
        worker = SwarmWorkerAgent(agent_id="w", catalog=catalog, service_ids=["svc"])
        worker.register_handler("svc", _echo_handler)
        router.register_worker(worker)
        acp.register_service("w", _make_service("svc").to_acp_manifest())

        # Add more than maxlen entries
        for i in range(50):
            router.handle_request(
                ServiceRequest(
                    request_id=f"r-{i}",
                    client_agent_id="buyer",
                    service_id="svc",
                    input_params={},
                )
            )
        assert len(router._request_log) <= MAX_REQUEST_LOG


class TestFeeRateValidation:
    def test_invalid_fee_rate_rejected(self):
        with pytest.raises(ValueError, match="platform_fee_rate"):
            ACPClient(platform_fee_rate=1.5)

    def test_invalid_negative_fee_rate_rejected(self):
        with pytest.raises(ValueError, match="platform_fee_rate"):
            ACPClient(platform_fee_rate=-0.1)
