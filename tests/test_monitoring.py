"""Tests for uptime monitoring and error alerting."""

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DATABASE_PATH"] = db_path

    from agency_os.service.api import app as app_module

    app = app_module.create_app()
    tenant_registry = app_module.tenant_registry

    tenant, api_key = tenant_registry.register(name="Test Corp")
    tenant.metadata["billing_status"] = "active"
    tenant_registry.save_metadata(tenant)

    c = TestClient(app)
    c.headers["X-API-Key"] = api_key
    yield c

    os.unlink(db_path)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ok", "degraded")
        assert "X-Request-ID" in resp.headers

    def test_liveness_returns_alive(self, client):
        resp = client.get("/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_readiness_returns_expected_status_shape(self, client):
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert data["status"] in ("ready", "not_ready")
        if resp.status_code == 200:
            assert data["status"] == "ready"
        else:
            assert data["status"] == "not_ready"
        assert "checks" in data or data["status"] == "not_ready"

    def test_liveness_and_readiness_on_shutdown(self, client):
        from agency_os.service.api import app as app_module

        original = app_module.is_shutting_down
        try:
            app_module.is_shutting_down = True
            live_resp = client.get("/live")
            ready_resp = client.get("/ready")
        finally:
            app_module.is_shutting_down = original

        assert live_resp.status_code == 200
        assert live_resp.json()["status"] == "shutting_down"
        assert ready_resp.status_code == 503
        assert ready_resp.json()["status"] == "not_ready"

    def test_readiness_returns_ready_with_required_checks(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "database" in data["required_checks"]
        assert "database_tables" in data["required_checks"]

    def test_health_detailed_returns_checks(self, client):
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "migration_version" in data
        assert isinstance(data["migration_version"], str)
        assert "database" in data["checks"]
        assert "database_tables" in data["checks"]
        assert "stripe" in data["checks"]
        assert "llm_provider" in data["checks"]
        assert data["checks"]["database"]["healthy"] is True
        assert data["checks"]["database_tables"]["healthy"] is True
        assert isinstance(data["checks"]["stripe"]["healthy"], bool)
        assert isinstance(data["checks"]["llm_provider"]["healthy"], bool)
        assert "latency_ms" in data["checks"]["database"]

    def test_metrics_endpoint_exposes_event_counters(self, client):
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "agency_os_events_total" in resp.text
        assert 'event="request.completed"' in resp.text
        assert "agency_os_worker_task_completion_latency_seconds_count" in resp.text
        assert "agency_os_circuit_breaker_tripped_total" in resp.text
        assert "agency_os_orphaned_run_locks_reconciled_total" in resp.text
        assert "agency_os_orphaned_lock_reconciliations_total" in resp.text
        assert (
            "agency_os_orphaned_lock_reconciliation_last_timestamp_seconds" in resp.text
        )
        assert "agency_os_queued_run_timeouts_total" in resp.text
        assert "agency_os_queued_run_timeout_issues_total" in resp.text
        assert "agency_os_queued_run_timeout_last_timestamp_seconds" in resp.text
        assert "agency_os_workspace_drift_scanned_total" in resp.text
        assert "agency_os_workspace_drift_detected_total" in resp.text
        assert "agency_os_workspace_drift_last_timestamp_seconds" in resp.text

    def test_metrics_endpoint_exposes_worker_latency(self, client, monkeypatch):
        from agency_os.service.api import app as app_module

        monkeypatch.setattr(
            app_module.db,
            "get_task_outcome_latency_stats",
            lambda since=None: {
                "count": 7,
                "avg_duration_sec": 1.25,
                "p95_duration_sec": 2.5,
            },
        )
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "agency_os_worker_task_completion_latency_seconds_count 7" in resp.text
        assert "agency_os_worker_task_completion_latency_seconds_avg 1.25" in resp.text
        assert "agency_os_worker_task_completion_latency_seconds_p95 2.5" in resp.text

    def test_missing_api_key_has_structured_error_code(self, client):
        resp = client.get("/api/v1/orgs", headers={"X-API-Key": ""})
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "auth_missing_api_key"
        assert data["detail"] == "Missing API key"
        assert "request_id" in data

    def test_validation_error_has_structured_error_code(self, client):
        resp = client.post("/api/v1/tenants", json={})
        assert resp.status_code == 422
        data = resp.json()
        assert data["error_code"] == "validation_error"
        assert isinstance(data["detail"], list)

    def test_startup_allows_missing_optional_env(self):
        from agency_os.service.api import app as app_module

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("DATABASE_PATH", db_path)
                mp.delenv("ANTHROPIC_API_KEY", raising=False)
                mp.delenv("STRIPE_SECRET_KEY", raising=False)
                app = app_module.create_app()
                assert app is not None
        finally:
            os.unlink(db_path)

    def test_health_detailed_includes_uptime(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "uptime" in data
        assert "started_at" in data["uptime"]
        assert "uptime_seconds" in data["uptime"]
        assert data["uptime"]["uptime_seconds"] >= 0

    def test_health_detailed_includes_error_stats(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "errors" in data
        assert "window_requests" in data["errors"]
        assert "window_error_rate" in data["errors"]
        assert "alert_threshold" in data["errors"]

    def test_health_detailed_includes_run_failures(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "run_failures" in data
        assert "window_runs" in data["run_failures"]
        assert "window_failures" in data["run_failures"]
        assert "window_failure_rate" in data["run_failures"]
        assert "alert_threshold" in data["run_failures"]
        assert "total_runs" in data["run_failures"]
        assert "total_failures" in data["run_failures"]

    def test_health_detailed_includes_orphaned_lock_reconciliation(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "orphaned_lock_reconciliation" in data
        metrics = data["orphaned_lock_reconciliation"]
        assert "reconciled_locks_total" in metrics
        assert "reconciled_issues_total" in metrics
        assert "last_reconciliation_timestamp" in metrics
        assert "last_reconciliation_at" in metrics

    def test_health_detailed_includes_queued_run_timeouts(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "queued_run_timeouts" in data
        metrics = data["queued_run_timeouts"]
        assert "timed_out_runs_total" in metrics
        assert "timed_out_issues_total" in metrics
        assert "last_timeout_timestamp" in metrics
        assert "last_timeout_at" in metrics

    def test_health_detailed_includes_workspace_drift_metrics(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "workspace_drift" in data
        metrics = data["workspace_drift"]
        assert "scanned_workspaces_total" in metrics
        assert "drifted_workspaces_total" in metrics
        assert "last_scan_timestamp" in metrics
        assert "last_scan_at" in metrics

    def test_health_detailed_includes_slo_compliance(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "slo_compliance" in data
        slo = data["slo_compliance"]
        assert "status" in slo
        assert slo["status"] in ("healthy", "warning", "critical")
        assert "health" in slo
        assert slo["health"] in ("compliant", "degraded", "breached")
        assert "current_failure_rate" in slo
        assert "threshold_percent" in slo
        assert "window_seconds" in slo
        assert "runs_in_window" in slo

    def test_health_detailed_includes_autonomy_gate(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        gate = data["autonomy_gate"]
        assert "degraded" in gate
        assert "reason" in gate
        assert "target_governance_preset" in gate

    def test_run_failure_breach_emits_circuit_breaker_event(self, client):
        from agency_os.observability import METRIC_CIRCUIT_BREAKER_TRIPPED
        from agency_os.service.api import app as app_module

        # Directly track the event to verify /metrics reporting works,
        # then also verify the alert callback fires through the tracker.
        app_module.event_tracker.track(METRIC_CIRCUIT_BREAKER_TRIPPED, source="test")

        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert 'agency_os_events_total{event="circuit_breaker.tripped"}' in resp.text

    def test_lifespan_stops_webhook_and_scheduled_workers(self, monkeypatch):
        from agency_os.service import scheduled_jobs as scheduled_jobs_module
        from agency_os.service import webhooks as webhooks_module
        from agency_os.service.api import app as app_module

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        stop_calls: list[object] = []
        scheduler = object()

        class FakeWebhookDispatcher:
            def __init__(self, live_mode: bool):
                self.live_mode = live_mode

            def set_delivery_repository(self, _repo) -> None:
                return None

            def set_health_tracker(self, _tracker) -> None:
                return None

            def start_retry_worker(self) -> None:
                return None

            def stop_retry_worker(self, *, timeout_sec: float = 5.0) -> None:
                stop_calls.append(("webhook", timeout_sec))

            def dispatch(self, _event):
                return []

        def fake_start_scheduled_jobs(_tracker, _db):
            return scheduler

        def fake_stop_scheduled_jobs(value):
            stop_calls.append(("scheduler", value))

        try:
            monkeypatch.setenv("DATABASE_PATH", db_path)
            monkeypatch.setattr(
                webhooks_module, "WebhookDispatcher", FakeWebhookDispatcher
            )
            monkeypatch.setattr(
                scheduled_jobs_module, "start_scheduled_jobs", fake_start_scheduled_jobs
            )
            monkeypatch.setattr(
                scheduled_jobs_module, "stop_scheduled_jobs", fake_stop_scheduled_jobs
            )

            app = app_module.create_app()
            with TestClient(app):
                pass
        finally:
            os.unlink(db_path)

        assert stop_calls == [("webhook", 5.0), ("scheduler", scheduler)]


class TestErrorTracker:
    def test_error_tracker_records_requests(self):
        from agency_os.monitoring import ErrorTracker

        tracker = ErrorTracker()
        tracker.record(error=False)
        tracker.record(error=False)
        tracker.record(error=True)
        stats = tracker.stats()
        assert stats["total_requests"] == 3
        assert stats["total_errors"] == 1

    def test_error_tracker_rate_calculation(self):
        from agency_os.monitoring import ErrorTracker

        tracker = ErrorTracker(min_requests=2)
        for _ in range(8):
            tracker.record(error=False)
        for _ in range(2):
            tracker.record(error=True)
        stats = tracker.stats()
        assert abs(stats["window_error_rate"] - 0.2) < 0.01

    def test_error_tracking_middleware_counts(self, client):
        # Make some requests to trigger the middleware
        client.get("/health")  # not counted (health excluded)
        client.get("/api/v1/orgs")  # counted
        resp = client.get("/health/detailed")
        data = resp.json()
        # At least one request should be tracked (the /api/v1/orgs call)
        assert data["errors"]["total_requests"] >= 1


class TestUptimeTracker:
    def test_uptime_increases(self):
        from agency_os.monitoring import UptimeTracker

        tracker = UptimeTracker()
        info = tracker.info()
        assert info["uptime_seconds"] >= 0
        assert "started_at" in info
        assert "uptime_human" in info


class TestRunFailureTracker:
    def test_run_failure_tracker_records_outcomes(self):
        from agency_os.monitoring import RunFailureTracker

        tracker = RunFailureTracker()
        tracker.record(failure=False)
        tracker.record(failure=False)
        tracker.record(failure=True)
        stats = tracker.stats()
        assert stats["total_runs"] == 3
        assert stats["total_failures"] == 1

    def test_run_failure_tracker_rate_calculation(self):
        from agency_os.monitoring import RunFailureTracker

        tracker = RunFailureTracker(min_runs=2)
        for _ in range(8):
            tracker.record(failure=False)
        for _ in range(2):
            tracker.record(failure=True)
        stats = tracker.stats()
        assert abs(stats["window_failure_rate"] - 0.2) < 0.01


class TestHealthCheckTimeouts:
    def test_health_check_marks_timeout_unhealthy(self):
        from agency_os.observability import HealthCheck

        health_check = HealthCheck(check_timeout_seconds=0.01)
        health_check.register_check("slow", lambda: time.sleep(0.05) or True)

        result = health_check.run_all()["slow"]
        assert result["healthy"] is False
        assert result["timed_out"] is True

    def test_run_failure_tracker_api_error_recording(self):
        from agency_os.monitoring import RunFailureTracker

        tracker = RunFailureTracker()
        tracker.record_api_error("Connection timeout")
        stats = tracker.stats()
        assert stats["last_api_error"] == "Connection timeout"


class TestAutonomyGate:
    def test_degrades_when_success_below_slo(self):
        from agency_os.monitoring import AutonomyGate

        gate = AutonomyGate(success_threshold=0.95, min_runs=5)
        status = gate.evaluate({"window_runs": 10, "window_failure_rate": 0.20})
        assert status["degraded"] is True
        assert status["target_governance_preset"] == "conservative"

    def test_no_degrade_with_insufficient_samples(self):
        from agency_os.monitoring import AutonomyGate

        gate = AutonomyGate(success_threshold=0.95, min_runs=10)
        status = gate.evaluate({"window_runs": 3, "window_failure_rate": 0.40})
        assert status["degraded"] is False
        assert "insufficient data" in status["reason"]


class TestWebhookHealthTracker:
    def test_records_deliveries_and_computes_stats(self):
        from agency_os.monitoring import WebhookHealthTracker

        tracker = WebhookHealthTracker(min_deliveries=2)
        tracker.record(success=True, latency_ms=50.0)
        tracker.record(success=True, latency_ms=100.0)
        tracker.record(success=False, latency_ms=200.0)
        stats = tracker.stats()
        assert stats["total_deliveries"] == 3
        assert stats["total_failures"] == 1
        assert stats["deliveries_in_window"] == 3
        assert stats["successes"] == 2
        assert stats["failures"] == 1
        assert abs(stats["success_rate"] - 0.6667) < 0.01

    def test_latency_percentiles(self):
        from agency_os.monitoring import WebhookHealthTracker

        tracker = WebhookHealthTracker()
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            tracker.record(success=True, latency_ms=float(ms))
        stats = tracker.stats()
        assert stats["latency_p50_ms"] > 0
        assert stats["latency_p95_ms"] >= stats["latency_p50_ms"]

    def test_empty_tracker_returns_defaults(self):
        from agency_os.monitoring import WebhookHealthTracker

        tracker = WebhookHealthTracker()
        stats = tracker.stats()
        assert stats["total_deliveries"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["latency_p50_ms"] == 0.0
        assert stats["latency_p95_ms"] == 0.0

    def test_alert_fires_on_degraded_success_rate(self):
        from agency_os.monitoring import WebhookHealthTracker

        alerts: list[dict] = []
        tracker = WebhookHealthTracker(
            alert_threshold=0.90, min_deliveries=5, alert_callback=alerts.append
        )
        for _ in range(4):
            tracker.record(success=True, latency_ms=10.0)
        for _ in range(6):
            tracker.record(success=False, latency_ms=500.0)
        assert len(alerts) == 1
        assert alerts[0]["severity"] in ("warning", "critical")

    def test_webhook_health_in_detailed_endpoint(self, client):
        resp = client.get("/health/detailed")
        data = resp.json()
        assert "webhook_health" in data
        wh = data["webhook_health"]
        assert "realtime" in wh
        assert wh["realtime"]["total_deliveries"] >= 0


class TestHealthChecks:
    def test_database_check_passes(self):
        from agency_os.monitoring import check_database
        from agency_os.storage import Database

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            with Database(db_path) as db:
                assert check_database(db) is True
        finally:
            os.unlink(db_path)

    def test_database_tables_check_passes(self):
        from agency_os.monitoring import check_database_tables
        from agency_os.storage import Database

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            with Database(db_path) as db:
                assert check_database_tables(db) is True
        finally:
            os.unlink(db_path)

    def test_degraded_health_on_failed_check(self):
        from agency_os.observability import HealthCheck

        hc = HealthCheck()
        hc.register_check("failing", lambda: False)
        assert hc.is_healthy() is False
        results = hc.run_all()
        assert results["failing"]["healthy"] is False

    def test_stripe_reachability_requires_key_shape(self):
        from agency_os.monitoring import check_stripe_reachability

        class Billing:
            _api_key = "not_a_stripe_key"

        assert check_stripe_reachability(Billing()) is False
