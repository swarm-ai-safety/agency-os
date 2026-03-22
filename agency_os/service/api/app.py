"""FastAPI application for agency-os."""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from agency_os.metering.collector import MeteringCollector
from agency_os.monitoring import (
    AutonomyGate,
    ErrorTracker,
    RunFailureTracker,
    UptimeTracker,
    WebhookHealthTracker,
    check_database,
    check_database_tables,
    check_llm_provider_available,
    check_stripe_reachability,
)
from agency_os.observability import (
    METRIC_CIRCUIT_BREAKER_TRIPPED,
    METRIC_REQUEST_COMPLETED,
    EventTracker,
    HealthCheck,
    bind_request_id,
    configure_logging,
    reset_request_id,
)
from agency_os.service.api.middleware.auth import (
    set_database as set_auth_database,
)
from agency_os.service.api.middleware.auth import (
    set_rate_limiter,
    set_tenant_registry,
)
from agency_os.service.api.middleware.rate_limit import RateLimiter
from agency_os.service.api.middleware.rate_limit_headers import (
    RateLimitHeaderMiddleware,
)
from agency_os.service.api.routers import (
    agents,
    auth_oidc,
    configure,
    gateway,
    governance,
    marketplace,
    metering,
    organizations,
    packages,
    pricing,
    tasks,
    tenants,
    timeline,
    waitlist,
    webhooks,
)
from agency_os.storage import Database
from agency_os.tenancy.tenant import TenantRegistry

logger = logging.getLogger(__name__)

# Global singletons — initialized in create_app()
db: Database | None = None
tenant_registry: TenantRegistry | None = None
metering_collector: MeteringCollector | None = None
health_check: HealthCheck | None = None
event_tracker: EventTracker | None = None
error_tracker: ErrorTracker | None = None
uptime_tracker: UptimeTracker | None = None
run_failure_tracker: RunFailureTracker | None = None
autonomy_gate: AutonomyGate | None = None
webhook_dispatcher: Any | None = None
webhook_health_tracker: WebhookHealthTracker | None = None
scheduled_jobs_scheduler: Any | None = None
is_shutting_down = False
OPTIONAL_ENV_VARS = ("ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY")
_ERROR_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_error",
    502: "upstream_provider_error",
    503: "service_unavailable",
}


def _resolve_error_code(status_code: int, detail: Any) -> str:
    detail_text = str(detail) if detail is not None else ""
    detail_lower = detail_text.lower()
    if status_code == 400 and "unknown model" in detail_lower:
        return "unknown_model"
    if status_code == 401 and "Missing API key" in detail_text:
        return "auth_missing_api_key"
    if status_code == 401 and "Invalid API key" in detail_text:
        return "auth_invalid_api_key"
    if status_code == 403 and "Tenant is deactivated" in detail_text:
        return "tenant_inactive"
    if status_code == 429 and "budget limit" in detail_lower:
        return "budget_limit_exceeded"
    if status_code == 429 and (
        "auto-paused" in detail_lower or "threshold" in detail_lower
    ):
        return "budget_threshold_exceeded"
    if status_code == 429 and "concurrent streams" in detail_lower:
        return "stream_limit_exceeded"
    return _ERROR_CODE_BY_STATUS.get(status_code, "unknown_error")


def _validate_startup_config() -> None:
    # Keep public endpoints (e.g. waitlist) available even when optional
    # provider/billing secrets are not configured.
    missing_optional = [
        key for key in OPTIONAL_ENV_VARS if not os.environ.get(key, "").strip()
    ]
    if missing_optional:
        logger.warning(
            "Optional environment variables not set: %s. "
            "Related features will return service_unavailable until configured.",
            ", ".join(sorted(missing_optional)),
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    global \
        db, \
        tenant_registry, \
        metering_collector, \
        health_check, \
        event_tracker, \
        error_tracker, \
        uptime_tracker, \
        run_failure_tracker, \
        autonomy_gate, \
        webhook_dispatcher, \
        webhook_health_tracker, \
        scheduled_jobs_scheduler

    configure_logging(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        json_format=os.environ.get("LOG_JSON", "true").lower()
        not in ("0", "false", "no"),
    )

    @asynccontextmanager
    async def app_lifespan(_app: FastAPI):
        global is_shutting_down
        is_shutting_down = False
        try:
            yield
        finally:
            is_shutting_down = True
            if webhook_dispatcher is not None and hasattr(
                webhook_dispatcher, "stop_retry_worker"
            ):
                try:
                    webhook_dispatcher.stop_retry_worker()
                except Exception as e:
                    logger.warning("Failed stopping webhook retry worker: %s", e)
            stop_scheduled_jobs(scheduled_jobs_scheduler)

    app = FastAPI(
        title="Agency-OS",
        description="Turnkey autonomous AI organization platform",
        version="0.1.0",
        lifespan=app_lifespan,
    )

    _validate_startup_config()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        error_code = _resolve_error_code(exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": error_code,
                "request_id": getattr(request.state, "request_id", None),
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": jsonable_encoder(exc.errors()),
                "error_code": "validation_error",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled API exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_code": "internal_error",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # Initialize database
    db = Database()
    logger.info("Database initialized")

    # Initialize tenant registry backed by database
    tenant_registry = TenantRegistry(db=db)

    # Add rate limit header middleware (must be added before routing)
    app.add_middleware(RateLimitHeaderMiddleware)

    # CORS — allow the landing site to call the API
    allowed_origins = os.environ.get("CORS_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key"],
        )

    # Initialize metering collector
    metering_collector = MeteringCollector()
    tasks.set_metering(metering_collector, db)
    agents.set_agent_deps(metering_collector, db)

    # Initialize timeline collector for time-lapse feature
    from agency_os.timeline.collector import TimelineCollector

    timeline_collector = TimelineCollector(db=db)
    timeline.set_timeline_deps(timeline_collector, db)
    organizations.set_timeline_collector(timeline_collector)

    # Initialize webhook dispatcher and repository
    from agency_os.service.webhook_repository import WebhookRepository
    from agency_os.service.webhooks import WebhookDispatcher
    from agency_os.tenancy.secrets import SecretStore

    live_mode = os.environ.get("WEBHOOK_LIVE_MODE", "").lower() in ("true", "1", "yes")
    webhook_dispatcher = WebhookDispatcher(live_mode=live_mode)
    webhook_health_tracker = WebhookHealthTracker()
    webhook_dispatcher.set_health_tracker(webhook_health_tracker)
    webhooks.set_webhook_health_tracker(webhook_health_tracker)

    # Initialize secret store for webhook secret encryption and gateway provider keys
    secret_store = None
    try:
        secret_store = SecretStore()
    except ValueError as e:
        logger.warning(
            "SecretStore initialization failed (%s). Webhook secrets will not be encrypted.",
            e,
        )
        # In test/dev, continue without encryption if AGENCY_OS_SECRET_KEY is not set
        # In production, this would be a critical failure
        secret_store = None

    # Create webhook repository with persistence
    if secret_store:
        webhook_repository = WebhookRepository(db, webhook_dispatcher, secret_store)
        webhook_repository.load_all()  # Load existing webhooks from database
        webhook_dispatcher.set_delivery_repository(webhook_repository)
        webhook_dispatcher.start_retry_worker()
        webhooks.set_webhook_repository(webhook_repository)
        logger.info(
            "Webhook repository initialized with encryption (live_mode=%s)", live_mode
        )
    else:
        # Fallback: set dispatcher directly without persistence (legacy mode)
        webhooks.set_webhook_dispatcher(webhook_dispatcher)
        logger.info(
            "Webhook dispatcher initialized without persistence (live_mode=%s)",
            live_mode,
        )

    # Tasks router still needs dispatcher for event dispatch
    tasks.set_webhook_dispatcher(webhook_dispatcher)

    # Wire up tenant registry and rate limiter
    set_tenant_registry(tenant_registry)
    set_auth_database(db)
    set_rate_limiter(RateLimiter(requests_per_minute=60))
    auth_oidc.set_tenant_registry(tenant_registry)
    tenants.set_tenant_registry(tenant_registry)
    tenants.set_database(db)
    tenants.reset_signup_rate_limiter()
    tenants.reset_login_rate_limiter()
    organizations.set_org_store({})
    organizations.set_database(db)
    organizations.rehydrate_orgs_from_db()
    metering.set_database(db)
    governance.set_database(db)
    waitlist.set_db(db)

    # Wire up LLM Gateway
    from agency_os.gateway.cache import ResponseCache
    from agency_os.gateway.config import GatewayConfig
    from agency_os.gateway.provider_key_store import GatewayProviderKeyStore
    from agency_os.gateway.providers.registry import ProviderRegistry
    from agency_os.gateway.router import SmartRouter
    from agency_os.gateway.routing_feedback import RoutingFeedback

    gateway_config = GatewayConfig()
    provider_key_store = None
    if secret_store is not None:
        provider_key_store = GatewayProviderKeyStore(db, secret_store)
        provider_key_store.bootstrap_from_env()
    provider_registry = ProviderRegistry(key_store=provider_key_store)
    model_cost_per_1k = {
        m.model_id: m.cost_per_1k_input + m.cost_per_1k_output
        for m in gateway_config.list_models()
    }
    routing_feedback = RoutingFeedback(model_cost_per_1k=model_cost_per_1k)
    smart_router = SmartRouter(gateway_config, feedback=routing_feedback)
    response_cache = ResponseCache()
    gateway.set_metering(metering_collector)
    gateway.set_database(db)
    gateway.set_gateway_config(gateway_config)
    gateway.set_provider_registry(provider_registry)
    gateway.set_smart_router(smart_router)
    gateway.set_cache(response_cache)
    gateway.set_routing_feedback(routing_feedback)
    gateway.set_tenant_registry(tenant_registry)
    gateway.set_provider_key_store(provider_key_store)

    # Wire up BYOK tenant provider key store
    from agency_os.tenancy.provider_keys import TenantProviderKeyStore  # noqa: F401

    tenant_key_store = None
    if secret_store is not None:
        tenant_key_store = TenantProviderKeyStore(db, secret_store)
    gateway.set_tenant_key_store(tenant_key_store)

    # Wire up Stripe billing (optional — requires billing_private package)
    stripe_billing = None
    try:
        from agency_os.billing_private import StripeBilling
        from agency_os.billing_private import checkout as _checkout_mod

        _checkout_mod.set_tenant_registry(tenant_registry)
        _checkout_mod.set_database(db)
        stripe_billing = StripeBilling()
        _checkout_mod.set_stripe_billing(stripe_billing)
        gateway.set_stripe_billing(stripe_billing)
        logger.info("Stripe billing enabled")
    except ImportError:
        logger.info(
            "Stripe billing not initialized (billing_private not installed). "
            "Install with: pip install 'agency-os[billing]'"
        )
    except RuntimeError as e:
        logger.warning("Stripe billing disabled: %s", e)

    # Wire up Agentic Wallet client (optional — requires wallet_private + CDP SDK)
    try:
        from agency_os.wallet_private import AgenticWalletClient, WalletConfig
        from agency_os.wallet_private import wallets_router as _wallets_mod

        wallet_config = WalletConfig.from_env()
        wallet_client = AgenticWalletClient(wallet_config)
        _wallets_mod.set_wallet_client(wallet_client)
        logger.info(
            "Agentic Wallet client enabled (network: %s)", wallet_config.network
        )
    except KeyError as e:
        logger.info(
            "Agentic Wallet client not initialized (missing env var: %s). "
            "Wallet endpoints will return 503.",
            e,
        )
    except ImportError:
        logger.info(
            "Agentic Wallet client not initialized (CDP SDK not installed). "
            "Install with: pip install 'agency-os[wallet]'"
        )

    # Wire up SWARM marketplace (agent-to-agent service commerce)
    from agency_os.marketplace.acp import ACPClient
    from agency_os.marketplace.catalog import ServiceCatalog
    from agency_os.marketplace.router import ACPRequestRouter
    from agency_os.marketplace.worker_agent import SwarmWorkerAgent

    service_catalog = ServiceCatalog()
    loaded = service_catalog.load_builtin_services()
    logger.info("SWARM marketplace: loaded %d service definitions", loaded)

    acp_client = ACPClient(
        platform_fee_rate=float(os.environ.get("ACP_PLATFORM_FEE_RATE", "0.05")),
        escrow_ttl_seconds=float(os.environ.get("ACP_ESCROW_TTL", "600")),
    )
    acp_request_router = ACPRequestRouter(
        catalog=service_catalog, acp_client=acp_client
    )

    # Create default worker agents for each service and register handlers
    from agency_os.marketplace import handlers as swarm_handlers

    handler_map = {
        "escalation_simulation": swarm_handlers.run_escalation_simulation,
        "governance_audit": swarm_handlers.run_governance_audit,
        "alignment_test": swarm_handlers.run_alignment_test,
        "red_team_eval": swarm_handlers.run_red_team_eval,
        "misalignment_scoring": swarm_handlers.run_misalignment_scoring,
        "safety_certification": swarm_handlers.run_safety_certification,
    }
    for service_id, handler_fn in handler_map.items():
        service = service_catalog.get(service_id)
        if service is None:
            continue
        worker = SwarmWorkerAgent(
            agent_id=f"swarm_{service_id}_worker",
            catalog=service_catalog,
            service_ids=[service_id],
        )
        worker.register_handler(
            service_id, cast(Callable[..., dict[str, Any]], handler_fn)
        )
        acp_request_router.register_worker(worker)

        # Register in ACP marketplace
        manifest = service.to_acp_manifest()
        acp_client.register_service(worker.agent_id, manifest)

    marketplace.set_catalog(service_catalog)
    marketplace.set_acp_client(acp_client)
    marketplace.set_request_router(acp_request_router)
    marketplace.set_database(db)
    logger.info("SWARM marketplace initialized with %d services", loaded)

    # Register routers
    app.include_router(organizations.router)
    app.include_router(configure.router)
    app.include_router(packages.router)
    app.include_router(tasks.router)
    app.include_router(agents.router)
    app.include_router(governance.router)
    app.include_router(auth_oidc.router)
    # Billing routers (optional — only when billing_private is installed)
    try:
        from agency_os.billing_private.billing_router import (
            router as billing_router,
        )
        from agency_os.billing_private.checkout import router as checkout_router

        app.include_router(billing_router)
        app.include_router(checkout_router)
    except ImportError:
        pass  # billing endpoints not available without billing_private
    app.include_router(tenants.router)
    app.include_router(webhooks.router)
    app.include_router(waitlist.router)
    # Wallet router (optional — only when wallet_private is installed)
    try:
        from agency_os.wallet_private.wallets_router import router as wallets_router

        app.include_router(wallets_router)
    except ImportError:
        pass  # wallet endpoints not available without wallet_private
    app.include_router(pricing.router)
    app.include_router(metering.router)
    app.include_router(gateway.router)
    app.include_router(marketplace.router)
    app.include_router(timeline.router)

    # Alias /api/plans to /api/pricing for API-first account management compatibility
    @app.get("/api/plans", tags=["pricing"])
    async def get_plans_alias() -> dict[str, Any]:
        """Alias for GET /api/pricing. Returns current pricing plans and model costs."""
        from agency_os.service.api.routers.pricing import _get_pricing_data

        return _get_pricing_data()

    # Initialize monitoring with SLO alert webhook callback
    def slo_alert_callback(alert_data: dict) -> None:
        """Dispatch SLO breach alerts via webhook."""
        try:
            from agency_os.service.webhooks import WebhookEvent

            if event_tracker is not None:
                event_tracker.track(
                    METRIC_CIRCUIT_BREAKER_TRIPPED,
                    source="run_failure_slo",
                    severity=alert_data.get("severity"),
                    failure_rate=alert_data.get("failure_rate"),
                )
            if db is not None:
                db.save_metering_event(
                    {
                        "tenant_id": "system",
                        "org_id": "system",
                        "agent_id": "scheduler",
                        "event_type": METRIC_CIRCUIT_BREAKER_TRIPPED,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "timestamp": time.time(),
                        "metadata": {
                            "source": "run_failure_slo",
                            "severity": alert_data.get("severity"),
                            "failure_rate": alert_data.get("failure_rate"),
                            "window_seconds": alert_data.get("window_seconds"),
                        },
                    }
                )
            webhook_dispatcher.dispatch(
                WebhookEvent(
                    event_type="slo.run_failure_rate_breach",
                    org_id="system",
                    payload=alert_data,
                )
            )
            webhook_dispatcher.dispatch(
                WebhookEvent(
                    event_type=METRIC_CIRCUIT_BREAKER_TRIPPED,
                    org_id="system",
                    payload={
                        "source": "run_failure_slo",
                        **alert_data,
                    },
                )
            )
        except Exception as e:
            logger.warning("Failed to dispatch SLO alert webhook: %s", e)

    uptime_tracker = UptimeTracker()
    error_tracker = ErrorTracker()
    run_failure_tracker = RunFailureTracker(alert_callback=slo_alert_callback)
    autonomy_gate = AutonomyGate(
        success_threshold=float(os.environ.get("RUN_SUCCESS_SLO_THRESHOLD", "0.95")),
        min_runs=int(os.environ.get("RUN_SUCCESS_SLO_MIN_RUNS", "10")),
    )
    tasks.set_autonomy_gate_status_getter(
        lambda: autonomy_gate.evaluate(run_failure_tracker.stats())
    )
    health_check = HealthCheck(
        check_timeout_seconds=float(
            os.environ.get("HEALTH_CHECK_TIMEOUT_SECONDS", "2.0")
        )
    )
    event_tracker = EventTracker()
    try:
        from agency_os.billing_private import checkout as _checkout_evt

        _checkout_evt.set_event_tracker(event_tracker)
    except ImportError:
        pass
    gateway.set_event_tracker(event_tracker)
    health_check.register_check("database", lambda: check_database(db))
    health_check.register_check("database_tables", lambda: check_database_tables(db))
    health_check.register_check(
        "stripe",
        lambda: check_stripe_reachability(
            stripe_billing,
            timeout_seconds=float(
                os.environ.get("HEALTH_CHECK_STRIPE_TIMEOUT_SECONDS", "2.0")
            ),
            verify_network=os.environ.get(
                "HEALTH_CHECK_STRIPE_VERIFY_NETWORK", "false"
            ).lower()
            in ("1", "true", "yes"),
        ),
    )
    health_check.register_check(
        "llm_provider",
        lambda: check_llm_provider_available(provider_registry, "anthropic"),
    )

    # Start scheduled background jobs (run statistics polling, lock cleanup)
    from agency_os.service.scheduled_jobs import (
        get_orphaned_lock_reconciliation_metrics,
        get_queued_run_timeout_metrics,
        get_workspace_drift_metrics,
        reset_orphaned_lock_reconciliation_metrics,
        reset_queued_run_timeout_metrics,
        reset_workspace_drift_metrics,
        start_scheduled_jobs,
        stop_scheduled_jobs,
    )

    reset_orphaned_lock_reconciliation_metrics()
    reset_queued_run_timeout_metrics()
    reset_workspace_drift_metrics()
    scheduled_jobs_scheduler = start_scheduled_jobs(run_failure_tracker, db)

    @app.middleware("http")
    async def request_tracing_middleware(request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request_token = bind_request_id(request_id)
        start = time.monotonic()
        response = None
        try:
            response = await call_next(request)
        finally:
            reset_request_id(request_token)
        latency_ms = (time.monotonic() - start) * 1000.0
        if response is None:
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "error_code": "internal_error",
                    "request_id": request_id,
                },
            )
        response.headers["X-Request-ID"] = request_id
        if event_tracker is not None:
            event_tracker.track(
                METRIC_REQUEST_COMPLETED,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=round(latency_ms, 2),
            )
        return response

    @app.middleware("http")
    async def error_tracking_middleware(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/health"):
            error_tracker.record(error=(response.status_code >= 500))
        return response

    @app.get("/health")
    async def health() -> dict:
        is_healthy = health_check.is_healthy()
        status = "ok" if is_healthy else "degraded"
        return {"status": status}

    @app.get("/live")
    async def liveness() -> dict:
        if is_shutting_down:
            return {"status": "shutting_down"}
        return {"status": "alive"}

    @app.get("/ready")
    async def readiness() -> JSONResponse:
        if is_shutting_down:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        checks = health_check.run_all()
        required_checks_env = os.environ.get(
            "HEALTH_CHECK_REQUIRED", "database,database_tables"
        )
        required_checks = {
            name.strip() for name in required_checks_env.split(",") if name.strip()
        }
        required_results = [
            result for name, result in checks.items() if name in required_checks
        ]
        is_healthy = bool(required_results) and all(
            result["healthy"] for result in required_results
        )
        status_code = 200 if is_healthy else 503
        status = "ready" if is_healthy else "not_ready"
        return JSONResponse(
            status_code=status_code,
            content={
                "status": status,
                "checks": checks,
                "required_checks": sorted(required_checks),
            },
        )

    @app.get("/health/detailed")
    async def health_detailed() -> dict:
        checks = health_check.run_all()
        is_healthy = all(r["healthy"] for r in checks.values())
        migration_version = db.get_migration_version() if db is not None else None

        # Compute SLO compliance status
        run_stats = run_failure_tracker.stats()
        autonomy_status = autonomy_gate.evaluate(run_stats)
        failure_rate = run_stats.get("window_failure_rate", 0.0)
        threshold = run_stats.get("alert_threshold", 0.15)

        # Red/Yellow/Green health indicators
        if failure_rate >= threshold:
            slo_status = "critical"  # Red
            slo_health = "breached"
        elif failure_rate >= threshold * 0.75:
            slo_status = "warning"  # Yellow
            slo_health = "degraded"
        else:
            slo_status = "healthy"  # Green
            slo_health = "compliant"

        slo_compliance = {
            "status": slo_status,
            "health": slo_health,
            "current_failure_rate": round(failure_rate * 100, 2),
            "threshold_percent": round(threshold * 100, 2),
            "window_seconds": run_stats.get("window_seconds", 3600),
            "runs_in_window": run_stats.get("window_runs", 0),
        }

        # Webhook delivery health
        wh_health: dict[str, Any] = {}
        if webhook_health_tracker is not None:
            wh_health["realtime"] = webhook_health_tracker.stats()
        if (
            webhook_dispatcher is not None
            and getattr(webhook_dispatcher, "_delivery_repository", None) is not None
        ):
            wh_health["persistent"] = (
                webhook_dispatcher._delivery_repository.delivery_stats_global()
            )

        return {
            "status": "ok" if is_healthy else "degraded",
            "checks": checks,
            "migration_version": migration_version,
            "uptime": uptime_tracker.info(),
            "errors": error_tracker.stats(),
            "run_failures": run_failure_tracker.stats(),
            "orphaned_lock_reconciliation": get_orphaned_lock_reconciliation_metrics(),
            "queued_run_timeouts": get_queued_run_timeout_metrics(),
            "workspace_drift": get_workspace_drift_metrics(),
            "slo_compliance": slo_compliance,
            "autonomy_gate": autonomy_status,
            "webhook_health": wh_health,
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus-style observability counters."""
        event_counts = event_tracker.summary() if event_tracker is not None else {}
        error_stats = error_tracker.stats()
        run_stats = run_failure_tracker.stats()
        orphaned_lock_metrics = get_orphaned_lock_reconciliation_metrics()
        queued_run_timeout_metrics = get_queued_run_timeout_metrics()
        workspace_drift_metrics = get_workspace_drift_metrics()
        task_latency = db.get_task_outcome_latency_stats() if db is not None else {}
        worker_metrics = db.get_worker_task_metrics() if db is not None else {}
        lines = [
            "# HELP agency_os_events_total Total in-process tracked events by name",
            "# TYPE agency_os_events_total counter",
        ]
        for name in sorted(event_counts):
            metric_name = name.replace(".", "_").replace("-", "_")
            lines.append(
                f'agency_os_events_total{{event="{name}"}} {event_counts[name]}'
            )
            lines.append(f"agency_os_event_{metric_name}_total {event_counts[name]}")
        lines.extend(
            [
                "# TYPE agency_os_error_requests_total counter",
                f"agency_os_error_requests_total {error_stats.get('total_requests', 0)}",
                "# TYPE agency_os_error_total counter",
                f"agency_os_error_total {error_stats.get('total_errors', 0)}",
                "# TYPE agency_os_run_total counter",
                f"agency_os_run_total {run_stats.get('total_runs', 0)}",
                "# TYPE agency_os_run_failures_total counter",
                f"agency_os_run_failures_total {run_stats.get('total_failures', 0)}",
                "# TYPE agency_os_worker_task_completion_latency_seconds_count gauge",
                f"agency_os_worker_task_completion_latency_seconds_count {task_latency.get('count', 0)}",
                "# TYPE agency_os_worker_task_completion_latency_seconds_avg gauge",
                f"agency_os_worker_task_completion_latency_seconds_avg {task_latency.get('avg_duration_sec', 0.0)}",
                "# TYPE agency_os_worker_task_completion_latency_seconds_p95 gauge",
                f"agency_os_worker_task_completion_latency_seconds_p95 {task_latency.get('p95_duration_sec', 0.0)}",
                "# TYPE agency_os_worker_task_outcomes_total counter",
                f"agency_os_worker_task_outcomes_total {int(worker_metrics.get('task_outcomes_total', 0))}",
                "# TYPE agency_os_worker_task_outcomes_success_total counter",
                f"agency_os_worker_task_outcomes_success_total {int(worker_metrics.get('task_outcomes_success_total', 0))}",
                "# TYPE agency_os_worker_task_outcomes_failure_total counter",
                f"agency_os_worker_task_outcomes_failure_total {int(worker_metrics.get('task_outcomes_failure_total', 0))}",
                "# TYPE agency_os_circuit_breaker_tripped_total counter",
                f"agency_os_circuit_breaker_tripped_total {int(worker_metrics.get('circuit_breaker_tripped_total', 0))}",
                "# TYPE agency_os_orphaned_run_locks_reconciled_total counter",
                f"agency_os_orphaned_run_locks_reconciled_total {int(cast(Any, orphaned_lock_metrics.get('reconciled_locks_total', 0)))}",
                "# TYPE agency_os_orphaned_lock_reconciliations_total counter",
                f"agency_os_orphaned_lock_reconciliations_total {int(cast(Any, orphaned_lock_metrics.get('reconciled_issues_total', 0)))}",
                "# TYPE agency_os_orphaned_lock_reconciliation_last_timestamp_seconds gauge",
                f"agency_os_orphaned_lock_reconciliation_last_timestamp_seconds {float(cast(Any, orphaned_lock_metrics.get('last_reconciliation_timestamp') or 0.0))}",
                "# TYPE agency_os_queued_run_timeouts_total counter",
                f"agency_os_queued_run_timeouts_total {int(cast(Any, queued_run_timeout_metrics.get('timed_out_runs_total', 0)))}",
                "# TYPE agency_os_queued_run_timeout_issues_total counter",
                f"agency_os_queued_run_timeout_issues_total {int(cast(Any, queued_run_timeout_metrics.get('timed_out_issues_total', 0)))}",
                "# TYPE agency_os_queued_run_timeout_last_timestamp_seconds gauge",
                f"agency_os_queued_run_timeout_last_timestamp_seconds {float(cast(Any, queued_run_timeout_metrics.get('last_timeout_timestamp') or 0.0))}",
                "# TYPE agency_os_workspace_drift_scanned_total counter",
                f"agency_os_workspace_drift_scanned_total {int(cast(Any, workspace_drift_metrics.get('scanned_workspaces_total', 0)))}",
                "# TYPE agency_os_workspace_drift_detected_total counter",
                f"agency_os_workspace_drift_detected_total {int(cast(Any, workspace_drift_metrics.get('drifted_workspaces_total', 0)))}",
                "# TYPE agency_os_workspace_drift_last_timestamp_seconds gauge",
                f"agency_os_workspace_drift_last_timestamp_seconds {float(cast(Any, workspace_drift_metrics.get('last_scan_timestamp') or 0.0))}",
            ]
        )
        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    return app


# Default app instance
app = create_app()
