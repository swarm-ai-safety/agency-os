"""LLM Gateway proxy router — OpenAI-compatible chat completions.

Features:
- Smart routing: ``model="auto"`` picks cheapest adequate model
- Response caching: deterministic requests served from cache at zero cost
- Per-request cost tracking: every request logged with provider cost, margin
- Streaming SSE support
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from agency_os.gateway.cache import ResponseCache
from agency_os.gateway.config import GatewayConfig, ModelConfig
from agency_os.gateway.failover import call_with_failover
from agency_os.gateway.provider_key_store import (
    SUPPORTED_PROVIDER_KEYS,
    GatewayProviderKeyStore,
)
from agency_os.gateway.providers.registry import ProviderRegistry
from agency_os.gateway.router import SmartRouter
from agency_os.gateway.routing_feedback import RoutingFeedback
from agency_os.metering.collector import MeteringCollector
from agency_os.observability import (
    METRIC_BUDGET_DEPLETED,
    EventTracker,
)
from agency_os.service.api.middleware.auth import (
    get_current_tenant,
    record_free_tier_usage,
    require_action_approval,
    require_active_billing,
)
from agency_os.service.email import send_email
from agency_os.storage import Database
from agency_os.tenancy.provider_keys import (  # noqa: F401
    SUPPORTED_PROVIDERS as BYOK_SUPPORTED_PROVIDERS,
)
from agency_os.tenancy.provider_keys import (
    TenantProviderKeyStore,
)
from agency_os.tenancy.tenant import Tenant, TenantRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gateway", tags=["gateway"])

# Streaming retry policy (pre-first-token only)
_STREAM_CONNECT_MAX_RETRIES = 1
_STREAM_RETRY_DELAY_SECONDS = 0.2
_STREAM_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Concurrent stream limiter: max active streaming connections per tenant
_MAX_CONCURRENT_STREAMS = 10
_active_streams: dict[str, int] = {}
_stream_lock = threading.Lock()

# Module-level singletons — injected by app.py
_metering: MeteringCollector | None = None
_db: Database | None = None
_gateway_config: GatewayConfig | None = None
_provider_registry: ProviderRegistry | None = None
_stripe_billing: Any = None
_smart_router: SmartRouter | None = None
_cache: ResponseCache | None = None
_routing_feedback: RoutingFeedback | None = None
_tenant_registry: TenantRegistry | None = None
_event_tracker: EventTracker | None = None
_provider_key_store: GatewayProviderKeyStore | None = None
_tenant_key_store: TenantProviderKeyStore | None = None
_budget_lock = threading.Lock()


def set_metering(metering: MeteringCollector) -> None:
    global _metering
    _metering = metering


def set_database(db: Database) -> None:
    global _db
    _db = db


def set_gateway_config(config: GatewayConfig) -> None:
    global _gateway_config
    _gateway_config = config


def set_provider_registry(registry: ProviderRegistry) -> None:
    global _provider_registry
    _provider_registry = registry


def set_stripe_billing(billing: Any) -> None:
    global _stripe_billing
    _stripe_billing = billing


def set_smart_router(sr: SmartRouter) -> None:
    global _smart_router
    _smart_router = sr


def set_cache(cache: ResponseCache) -> None:
    global _cache
    _cache = cache


def set_routing_feedback(feedback: RoutingFeedback) -> None:
    global _routing_feedback
    _routing_feedback = feedback


def set_tenant_registry(registry: TenantRegistry) -> None:
    global _tenant_registry
    _tenant_registry = registry


def set_event_tracker(event_tracker: EventTracker) -> None:
    global _event_tracker
    _event_tracker = event_tracker


def set_provider_key_store(key_store: GatewayProviderKeyStore | None) -> None:
    global _provider_key_store
    _provider_key_store = key_store


def set_tenant_key_store(key_store: TenantProviderKeyStore | None) -> None:  # noqa: F841
    global _tenant_key_store
    _tenant_key_store = key_store


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=1_000_000)


# Max total content across all messages (1MB)
_MAX_TOTAL_CONTENT_BYTES = 1_000_000


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0, le=1_000_000)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop: str | list[str] | None = None
    budget: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    task_class: str | None = Field(default=None, pattern=r"^(quality|latency|cost)$")

    @model_validator(mode="after")
    def check_total_content_size(self) -> "ChatCompletionRequest":
        total = sum(len(m.content.encode("utf-8")) for m in self.messages)
        if total > _MAX_TOTAL_CONTENT_BYTES:
            raise ValueError(
                f"Total message content ({total} bytes) exceeds limit ({_MAX_TOTAL_CONTENT_BYTES} bytes)"
            )
        return self


class ProviderKeyRotationRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)
    reason: str = Field(min_length=8, max_length=500)


def _provider_key_fingerprint(api_key: str | None) -> str | None:
    if not api_key:
        return None
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


_GATEWAY_PROVIDER_KEY_ADMIN_PERMISSION = "gateway.provider_key.admin"


def _tenant_has_permission(tenant: Tenant, permission: str) -> bool:
    """Check tenant metadata for an explicit RBAC permission grant."""
    raw_permissions = tenant.metadata.get("permissions", [])
    permissions: list[str] = []
    if isinstance(raw_permissions, list):
        permissions = [str(item).strip().lower() for item in raw_permissions]
    elif isinstance(raw_permissions, dict):
        allow = raw_permissions.get("allow", [])
        if isinstance(allow, list):
            permissions = [str(item).strip().lower() for item in allow]
    wanted = permission.strip().lower()
    return wanted in permissions or "*" in permissions


def _assert_gateway_admin_access(tenant: Tenant) -> None:
    if tenant.metadata.get("is_platform_admin") is not True:
        raise HTTPException(
            status_code=403,
            detail=(
                "Gateway provider key management requires platform admin privileges."
            ),
        )
    if not _tenant_has_permission(tenant, _GATEWAY_PROVIDER_KEY_ADMIN_PERMISSION):
        raise HTTPException(
            status_code=403,
            detail=(
                "Gateway provider key management requires RBAC permission "
                "'gateway.provider_key.admin'."
            ),
        )


def _require_gateway_admin(tenant: Tenant = Depends(get_current_tenant)) -> Tenant:
    _assert_gateway_admin_access(tenant)
    return tenant


def _provider_key_status(limit: int = 200) -> list[dict[str, Any]]:
    if _provider_key_store is None:
        return []
    meta_by_provider = {
        row["provider"]: row for row in _provider_key_store.list_key_metadata()
    }
    raw_audit_logs = (
        _db.get_audit_log(limit=max(500, min(limit * 8, 5000))) if _db else []
    )

    latest_rotation_by_provider: dict[str, dict[str, Any]] = {}
    for log in raw_audit_logs:
        if log.get("action") != "gateway.provider_key.rotated":
            continue
        detail_raw = log.get("detail")
        if not detail_raw:
            continue
        try:
            detail = json.loads(detail_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        provider = str(detail.get("provider", "")).strip().lower()
        if not provider:
            continue
        if provider not in latest_rotation_by_provider:
            latest_rotation_by_provider[provider] = {
                "timestamp": log.get("timestamp"),
                "actor": log.get("actor"),
            }

    providers = sorted(SUPPORTED_PROVIDER_KEYS | set(meta_by_provider.keys()))
    result: list[dict[str, Any]] = []
    for provider in providers:
        metadata = meta_by_provider.get(provider)
        rotation = latest_rotation_by_provider.get(provider, {})
        result.append(
            {
                "provider": provider,
                "configured": metadata is not None,
                "created_at": metadata.get("created_at") if metadata else None,
                "updated_at": metadata.get("updated_at") if metadata else None,
                "last_rotated_at": rotation.get("timestamp"),
                "last_rotated_by": rotation.get("actor"),
            }
        )
    return result


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    tenant: Tenant = Depends(require_active_billing),
) -> Any:
    """OpenAI-compatible chat completions endpoint.

    Features:
    - ``model="auto"``: smart routing picks cheapest adequate model
    - Caching: deterministic requests (temperature=0 or None) are cached
    - Per-request cost tracking with provider cost and margin
    """
    if _gateway_config is None or _provider_registry is None:
        raise HTTPException(status_code=503, detail="Gateway not configured")

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    start_time = time.time()
    routed_by = "explicit"
    complexity = None

    # Smart routing: model="auto"
    if req.model == "auto":
        if _smart_router is None:
            raise HTTPException(status_code=503, detail="Smart routing not configured")
        decision = _smart_router.route(
            messages,
            tenant_metadata=tenant.metadata,
            budget=req.budget,
            task_class=req.task_class,
        )
        model_config = decision.model
        routed_by = decision.reason
        complexity = decision.complexity.value
    else:
        explicit_model = _gateway_config.get_model(req.model)
        if explicit_model is None or not explicit_model.enabled:
            available = [
                m.model_id for m in _gateway_config.list_models(tenant.metadata)
            ]
            available.append("auto")
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model '{req.model}'. Available: {available}",
            )
        # Check tenant model access
        allowed = tenant.metadata.get("allowed_models")
        if allowed and req.model not in allowed:
            raise HTTPException(
                status_code=403, detail="Model not available for your plan"
            )
        model_config = explicit_model

    # Get provider — check for tenant BYOK key first
    byok = False
    provider = None
    if _tenant_key_store is not None:
        tenant_api_key = _tenant_key_store.get_key(
            tenant.tenant_id, model_config.provider
        )
        if tenant_api_key:
            provider = _provider_registry.create_with_key(
                model_config.provider, tenant_api_key, model_config.base_url
            )
            if provider is not None:
                byok = True

    if provider is None:
        provider = _provider_registry.get(model_config.provider, model_config.base_url)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{model_config.provider}' is not available",
        )

    # Atomic budget reservation: lock, check, reserve estimated cost
    effective_max_tokens = req.max_tokens or 4096
    estimated_input_tokens = sum(
        len(m.content.encode("utf-8")) // 4 for m in req.messages
    )
    estimated_cost = _calc_provider_cost(
        model_config, estimated_input_tokens, effective_max_tokens
    )
    with _budget_lock:
        budget_limit = float(tenant.metadata.get("budget_limit_usd", 100.0))
        spent = float(tenant.metadata.get("total_spent_usd", 0.0))

        # Check budget threshold (e.g., 95% = 0.95) for auto-pause
        # Only apply threshold logic if threshold < 1.0 (otherwise use hard limit)
        threshold = float(tenant.metadata.get("budget_pause_threshold", 1.0))
        if threshold < 1.0:
            threshold_amount = budget_limit * threshold
            already_notified = tenant.metadata.get("budget_pause_notified", False)

            # Auto-pause tenant if threshold is exceeded and not already paused
            if not already_notified and (spent + estimated_cost) >= threshold_amount:
                tenant.active = False
                tenant.metadata["budget_pause_notified"] = True
                if _tenant_registry is not None:
                    _tenant_registry.save_metadata(tenant)
                if _db is not None:
                    _db.save_audit_event(
                        actor="system:gateway_budget_guard",
                        action="tenant.deactivated",
                        resource="tenant",
                        resource_id=tenant.tenant_id,
                        detail=json.dumps(
                            {
                                "reason": "budget_threshold_exceeded",
                                "threshold": threshold,
                                "budget_limit_usd": budget_limit,
                                "current_spend_usd": spent,
                                "attempted_cost_usd": estimated_cost,
                            }
                        ),
                        tenant_id=tenant.tenant_id,
                    )

                # Emit webhook/alerting event
                _emit_budget_threshold_exceeded_event(
                    tenant=tenant,
                    budget_limit=budget_limit,
                    threshold=threshold,
                    current_spend=spent,
                    attempted_cost=estimated_cost,
                )

                raise HTTPException(
                    status_code=429,
                    detail=f"Tenant auto-paused: budget threshold ({threshold * 100:.0f}%) exceeded",
                )

        # Hard limit check
        if spent + estimated_cost > budget_limit:
            _emit_budget_depleted_event(
                tenant=tenant,
                budget_limit=budget_limit,
                current_spend=spent,
                attempted_cost=estimated_cost,
            )
            raise HTTPException(
                status_code=429,
                detail="Request would exceed tenant budget limit",
            )
        # Reserve estimated cost atomically
        tenant.metadata["total_spent_usd"] = spent + estimated_cost
        if _tenant_registry is not None:
            _tenant_registry.save_metadata(tenant)

    kwargs: dict[str, Any] = {}
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.max_tokens is not None:
        kwargs["max_tokens"] = req.max_tokens
    if req.top_p is not None:
        kwargs["top_p"] = req.top_p
    if req.stop is not None:
        kwargs["stop"] = req.stop

    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    # Streaming — with failover support and concurrent connection cap
    if req.stream:
        with _stream_lock:
            active = _active_streams.get(tenant.tenant_id, 0)
            if active >= _MAX_CONCURRENT_STREAMS:
                # Release reservation before rejecting
                _settle_budget(tenant, estimated_cost, 0.0)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many concurrent streams (limit: {_MAX_CONCURRENT_STREAMS})",
                )
            _active_streams[tenant.tenant_id] = active + 1

        return StreamingResponse(
            _guarded_stream(
                tenant_id=tenant.tenant_id,
                estimated_cost=estimated_cost,
                provider=provider,
                model_config=model_config,
                messages=messages,
                request_id=request_id,
                tenant=tenant,
                start_time=start_time,
                routed_by=routed_by,
                complexity=complexity,
                gateway_config=_gateway_config,
                provider_registry=_provider_registry,
                byok=byok,
                **kwargs,
            ),
            media_type="text/event-stream",
        )

    # Check cache (only for deterministic requests)
    cacheable = req.temperature is None or req.temperature == 0.0
    cache_key = None
    if cacheable and _cache is not None and not req.stream:
        cache_key = ResponseCache.cache_key(
            messages,
            model_config.model_id,
            req.temperature,
            req.max_tokens,
            req.top_p,
            req.stop,
            tenant_id=tenant.tenant_id,
        )
        cached = _cache.get(cache_key)
        cache_hit_type = "HIT"
        if cached is None:
            # Exact miss — try similarity-based lookup
            cached = _cache.get_similar(
                messages,
                model_config.model_id,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                stop=req.stop,
                tenant_id=tenant.tenant_id,
                allow_model_family_match=True,
            )
            cache_hit_type = "SIMILAR_HIT"
            if cached is not None and cached.model_id != model_config.model_id:
                cache_hit_type = "CROSS_MODEL_HIT"
        if cached is not None:
            latency_ms = (time.time() - start_time) * 1000
            response = dict(cached.response)
            response["id"] = request_id
            response["x_cache"] = cache_hit_type
            if cache_hit_type == "CROSS_MODEL_HIT":
                response["x_cache_model"] = cached.model_id
                response["x_requested_model"] = model_config.model_id

            # Record cost savings from cache hit
            _cache.record_cost_saved(
                _calc_provider_cost(model_config, cached.tokens_in, cached.tokens_out)
            )
            _log_request(
                request_id=request_id,
                tenant=tenant,
                model_config=model_config,
                tokens_in=cached.tokens_in,
                tokens_out=cached.tokens_out,
                latency_ms=latency_ms,
                cached=True,
                routed_by=routed_by,
                complexity=complexity,
                byok=byok,
            )
            _record_usage(
                tenant=tenant,
                model_id=model_config.model_id,
                tokens_in=cached.tokens_in,
                tokens_out=cached.tokens_out,
                cost_per_1k_input=model_config.cost_per_1k_input,
                cost_per_1k_output=model_config.cost_per_1k_output,
                markup_rate=model_config.markup_rate,
                request_id=request_id,
                byok=byok,
            )
            # Cache hit = no provider cost; release full reservation
            _settle_budget(tenant, estimated_cost, 0.0)
            return response

    # Call provider with failover
    try:
        fo_result = await call_with_failover(
            provider=provider,
            model_config=model_config,
            messages=messages,
            gateway_config=_gateway_config,
            provider_registry=_provider_registry,
            **kwargs,
        )
    except Exception as exc:
        if complexity is not None and _routing_feedback is not None:
            _routing_feedback.record(
                model_id=model_config.model_id,
                complexity=complexity,
                score=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                success=False,
                source="gateway_runtime",
            )
        # Release budget reservation on failure
        _settle_budget(tenant, estimated_cost, 0.0)
        logger.warning(
            "All providers failed for tenant %s: %s",
            tenant.tenant_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Upstream provider error") from None

    result = fo_result.result
    # Update model_config if failover occurred
    if fo_result.failed_over:
        model_config = fo_result.model_config

    latency_ms = (time.time() - start_time) * 1000
    tokens_in = result.usage.prompt_tokens
    tokens_out = result.usage.completion_tokens

    if complexity is not None and _routing_feedback is not None:
        if (
            fo_result.failed_over
            and fo_result.original_model is not None
            and fo_result.original_model != model_config.model_id
        ):
            _routing_feedback.record(
                model_id=fo_result.original_model,
                complexity=complexity,
                score=0.0,
                latency_ms=latency_ms,
                success=False,
                source="gateway_runtime",
                failover=True,
            )
        _routing_feedback.record(
            model_id=model_config.model_id,
            complexity=complexity,
            score=1.0,
            latency_ms=latency_ms,
            success=True,
            source="gateway_runtime",
            failover=fo_result.failed_over,
        )

    response = {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_config.model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.content},
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "total_tokens": result.usage.total_tokens,
        },
        "x_cache": "MISS",
    }

    # Add routing info when model=auto was used
    if routed_by != "explicit":
        response["x_routed_model"] = model_config.model_id
        response["x_routing"] = routed_by

    # Add failover info
    if fo_result.failed_over:
        response["x_failover"] = True
        response["x_original_model"] = fo_result.original_model
        routed_by = f"failover: {fo_result.original_model} -> {model_config.model_id}"

    # Store in cache
    if cacheable and _cache is not None and cache_key is not None:
        _cache.put(
            cache_key,
            response,
            model_config.model_id,
            tokens_in,
            tokens_out,
            messages=messages,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            stop=req.stop,
            tenant_id=tenant.tenant_id,
        )

    # Settle budget: replace estimate with actual customer cost
    # BYOK requests don't count against tenant budget (tenant pays provider directly)
    actual_cost = (
        0.0 if byok else _calc_customer_cost(model_config, tokens_in, tokens_out)
    )
    _settle_budget(tenant, estimated_cost, actual_cost)

    # Record usage + log
    _record_usage(
        tenant=tenant,
        model_id=model_config.model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_per_1k_input=model_config.cost_per_1k_input,
        cost_per_1k_output=model_config.cost_per_1k_output,
        markup_rate=model_config.markup_rate,
        request_id=request_id,
        byok=byok,
    )
    _log_request(
        request_id=request_id,
        tenant=tenant,
        model_config=model_config,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cached=False,
        routed_by=routed_by,
        complexity=complexity,
        byok=byok,
    )

    return response


@router.get("/models")
async def list_models(
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """List models available to the authenticated tenant."""
    if _gateway_config is None:
        raise HTTPException(status_code=503, detail="Gateway not configured")

    models = _gateway_config.list_models(tenant.metadata)
    data = [
        {
            "id": m.model_id,
            "object": "model",
            "provider": m.provider,
            "pricing": {
                "input_per_1k": _gateway_config.customer_price_per_1k(m, "input"),
                "output_per_1k": _gateway_config.customer_price_per_1k(m, "output"),
            },
        }
        for m in models
    ]
    # Add "auto" as a virtual model
    data.insert(
        0,
        {
            "id": "auto",
            "object": "model",
            "provider": "auto",
            "pricing": {"input_per_1k": "varies", "output_per_1k": "varies"},
        },
    )
    return {"object": "list", "data": data}


@router.get("/stats")
async def get_stats(
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Get gateway usage stats for the authenticated tenant.

    Note: Cache stats are not exposed as they're global across all tenants.
    Per-tenant cache metrics would require tenant-scoped instrumentation.
    """
    stats: dict[str, Any] = {}
    if _db is not None:
        stats = _db.get_gateway_stats(tenant.tenant_id)
    # Cache stats removed: shared resource, no per-tenant metrics available
    return stats


@router.get("/requests")
async def get_requests(
    tenant: Tenant = Depends(require_active_billing),
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get recent gateway requests for the authenticated tenant."""
    if _db is None:
        return []
    rows = _db.get_gateway_requests(tenant.tenant_id, limit=min(limit, 200))
    # Strip internal cost data from customer-facing response
    internal_fields = {"provider_cost", "margin"}
    return [{k: v for k, v in r.items() if k not in internal_fields} for r in rows]


@router.get("/admin/provider-keys")
async def list_provider_keys(
    tenant: Tenant = Depends(_require_gateway_admin),
) -> dict[str, Any]:
    """List provider key configuration status and last rotation metadata."""
    _ = tenant
    if _provider_key_store is None:
        raise HTTPException(
            status_code=503,
            detail="Gateway provider key store is not configured",
        )
    return {"data": _provider_key_status()}


@router.post("/admin/provider-keys/{provider}/rotate")
async def rotate_provider_key(
    provider: str,
    req: ProviderKeyRotationRequest,
    tenant: Tenant = Depends(require_action_approval("gateway.provider_key.rotate")),
) -> dict[str, Any]:
    """Rotate an encrypted gateway provider API key and emit immutable audit events."""
    _assert_gateway_admin_access(tenant)
    if _provider_key_store is None:
        raise HTTPException(
            status_code=503,
            detail="Gateway provider key store is not configured",
        )

    provider_name = provider.strip().lower()
    if provider_name not in SUPPORTED_PROVIDER_KEYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported provider '{provider_name}'. "
                f"Supported: {sorted(SUPPORTED_PROVIDER_KEYS)}"
            ),
        )

    old_key = _provider_key_store.get_key(provider_name)
    _provider_key_store.set_key(provider_name, req.api_key)
    if _provider_registry is not None:
        _provider_registry.invalidate(provider_name)

    if _db is not None:
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="gateway.provider_key.rotated",
            resource="gateway_provider_key",
            resource_id=provider_name,
            detail=json.dumps(
                {
                    "provider": provider_name,
                    "reason": req.reason,
                    "replaced_existing_key": bool(old_key),
                    "old_key_fingerprint": _provider_key_fingerprint(old_key),
                    "new_key_fingerprint": _provider_key_fingerprint(req.api_key),
                }
            ),
            tenant_id=tenant.tenant_id,
        )

    return {
        "status": "rotated",
        "provider": provider_name,
        "replaced_existing_key": bool(old_key),
        "message": "Provider key rotated and provider cache invalidated.",
    }


@router.get("/admin/provider-keys/audit")
async def get_provider_key_audit(
    limit: int = 50,
    provider: str | None = None,
    tenant: Tenant = Depends(_require_gateway_admin),
) -> dict[str, Any]:
    """Return provider key rotation audit events."""
    _ = tenant
    if _db is None:
        return {"events": []}
    provider_name = provider.strip().lower() if provider else None
    raw_audit_logs = _db.get_audit_log(limit=max(min(limit, 200) * 8, 500))
    events: list[dict[str, Any]] = []
    for log in raw_audit_logs:
        if log.get("action") != "gateway.provider_key.rotated":
            continue
        detail_raw = log.get("detail")
        if not detail_raw:
            continue
        try:
            detail = json.loads(detail_raw)
        except (json.JSONDecodeError, TypeError):
            detail = {"raw": detail_raw}
        event_provider = str(detail.get("provider", "")).strip().lower()
        if provider_name and provider_name != event_provider:
            continue
        events.append(
            {
                "timestamp": log.get("timestamp"),
                "actor": log.get("actor"),
                "action": log.get("action"),
                "resource_id": log.get("resource_id"),
                "detail": detail,
            }
        )
    events.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
    return {"events": events[: min(limit, 200)]}


# ------------------------------------------------------------------
# BYOK — Tenant-owned provider keys
# ------------------------------------------------------------------


class TenantProviderKeyRequest(BaseModel):  # noqa: F841
    """Request body for storing a tenant provider key."""

    api_key: str = Field(min_length=1, max_length=4096)


@router.put("/provider-keys/{provider}")
async def set_tenant_provider_key(
    provider: str,
    req: TenantProviderKeyRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Store a provider API key for the calling tenant (BYOK)."""
    if _tenant_key_store is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant provider key store is not configured",
        )
    provider_name = provider.strip().lower()
    if provider_name not in BYOK_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported provider '{provider_name}'. "
                f"Supported: {sorted(BYOK_SUPPORTED_PROVIDERS)}"
            ),
        )

    fingerprint = _tenant_key_store.set_key(
        tenant.tenant_id, provider_name, req.api_key
    )

    if _db is not None:
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="byok.provider_key.set",
            resource="tenant_provider_key",
            resource_id=provider_name,
            detail=json.dumps(
                {
                    "provider": provider_name,
                    "key_fingerprint": fingerprint,
                }
            ),
            tenant_id=tenant.tenant_id,
        )

    return {
        "status": "stored",
        "provider": provider_name,
        "key_fingerprint": fingerprint,
    }


@router.delete("/provider-keys/{provider}")
async def delete_tenant_provider_key(
    provider: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Remove a stored provider API key for the calling tenant."""
    if _tenant_key_store is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant provider key store is not configured",
        )
    provider_name = provider.strip().lower()
    deleted = _tenant_key_store.delete_key(tenant.tenant_id, provider_name)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No key stored for provider '{provider_name}'",
        )

    if _db is not None:
        _db.save_audit_event(
            actor=f"tenant:{tenant.tenant_id}",
            action="byok.provider_key.deleted",
            resource="tenant_provider_key",
            resource_id=provider_name,
            detail=json.dumps({"provider": provider_name}),
            tenant_id=tenant.tenant_id,
        )

    return {"status": "deleted", "provider": provider_name}


@router.get("/provider-keys")
async def list_tenant_provider_keys(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """List provider keys the calling tenant has stored (metadata only)."""
    if _tenant_key_store is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant provider key store is not configured",
        )
    keys = _tenant_key_store.list_providers(tenant.tenant_id)
    return {"data": keys}


@router.get("/savings")
async def get_savings(
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Get cost savings breakdown from caching and smart routing.

    Returns:
    - total_requests: total number of requests
    - cache_hits: number of requests served from cache
    - cache_savings_usd: total cost saved from cache hits (provider cost = $0)
    - smart_routed: number of requests that used auto routing
    - total_cost_usd: actual total customer cost
    """
    if _db is None:
        return {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_savings_usd": 0.0,
            "smart_routed": 0,
            "total_cost_usd": 0.0,
        }
    return _db.get_gateway_savings(tenant.tenant_id)


@router.get("/top-models")
async def get_top_models(
    tenant: Tenant = Depends(require_active_billing),
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Get top N models by request count.

    Returns list of models with their request counts.
    """
    if _db is None:
        return []
    return _db.get_gateway_top_models(tenant.tenant_id, limit=min(limit, 20))


class EvalScoreRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    complexity: str = Field(pattern=r"^(simple|medium|complex)$")
    score: float = Field(ge=0.0, le=1.0)
    latency_ms: float | None = Field(default=None, ge=0.0)
    success: bool | None = None


@router.post("/eval")
async def record_eval_score(
    req: EvalScoreRequest,
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Record an eval score for a completed request.

    This feeds the routing feedback loop so the SmartRouter
    can learn which models perform best for which task types.
    """
    if _routing_feedback is None:
        raise HTTPException(status_code=503, detail="Routing feedback not configured")

    _routing_feedback.record(
        model_id=req.model_id,
        complexity=req.complexity,
        score=req.score,
        latency_ms=req.latency_ms,
        success=req.success,
        request_id=req.request_id,
        tenant_id=tenant.tenant_id,
    )
    return {"status": "recorded"}


@router.get("/eval/stats")
async def get_eval_stats(
    tenant: Tenant = Depends(require_active_billing),
) -> dict[str, Any]:
    """Get routing feedback stats across all models and complexity tiers."""
    if _routing_feedback is None:
        raise HTTPException(status_code=503, detail="Routing feedback not configured")
    return {
        "total_records": _routing_feedback.total_records,
        "models": _routing_feedback.get_all_stats(),
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _guarded_stream(
    *, tenant_id: str, estimated_cost: float, **kwargs: Any
) -> Any:
    """Wrap _stream_response to ensure concurrent stream counter is decremented."""
    try:
        async for chunk in _stream_response(estimated_cost=estimated_cost, **kwargs):
            yield chunk
    finally:
        with _stream_lock:
            count = _active_streams.get(tenant_id, 1)
            if count <= 1:
                _active_streams.pop(tenant_id, None)
            else:
                _active_streams[tenant_id] = count - 1


def _settle_budget(tenant: Tenant, estimated_cost: float, actual_cost: float) -> None:
    """Settle a budget reservation: release unused portion or charge overage."""
    diff = actual_cost - estimated_cost
    with _budget_lock:
        spent = float(tenant.metadata.get("total_spent_usd", 0.0))
        tenant.metadata["total_spent_usd"] = spent + diff
        if _tenant_registry is not None:
            _tenant_registry.save_metadata(tenant)


def _emit_budget_threshold_exceeded_event(
    *,
    tenant: Tenant,
    budget_limit: float,
    threshold: float,
    current_spend: float,
    attempted_cost: float,
) -> None:
    """Persist a budget threshold exceeded event and emit webhook alert."""
    if _db is not None:
        _db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": "gateway",
                "agent_id": "gateway",
                "event_type": "budget.threshold_exceeded",
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": time.time(),
                "metadata": {
                    "budget_limit_usd": budget_limit,
                    "threshold_percent": threshold * 100,
                    "threshold_amount_usd": budget_limit * threshold,
                    "total_spent_usd": current_spend,
                    "attempted_cost_usd": attempted_cost,
                    "tenant_paused": True,
                },
            }
        )
    logger.warning(
        "budget.threshold_exceeded tenant=%s threshold=%.0f%% spent=%.6f limit=%.6f attempted=%.6f tenant_paused=True",
        tenant.tenant_id,
        threshold * 100,
        current_spend,
        budget_limit,
        attempted_cost,
    )
    if _event_tracker is not None:
        _event_tracker.track(
            "budget.threshold_exceeded",
            tenant_id=tenant.tenant_id,
            threshold_percent=threshold * 100,
        )
    _send_budget_warning_email(
        tenant=tenant,
        subject=f"Budget threshold ({threshold * 100:.0f}%) exceeded — account paused",
        html=f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px; color: #e5a00d;">Budget Warning</h2>
  <p style="color: #666; line-height: 1.5;">
    Your account has been <strong>automatically paused</strong> because spending
    reached <strong>{threshold * 100:.0f}%</strong> of your
    <strong>${budget_limit:,.2f}</strong> budget limit.
  </p>
  <table style="width: 100%; margin: 24px 0; border-collapse: collapse;">
    <tr><td style="padding: 6px 0; color: #999;">Current spend</td><td style="padding: 6px 0; text-align: right; font-weight: 600;">${current_spend:,.2f}</td></tr>
    <tr><td style="padding: 6px 0; color: #999;">Budget limit</td><td style="padding: 6px 0; text-align: right; font-weight: 600;">${budget_limit:,.2f}</td></tr>
    <tr><td style="padding: 6px 0; color: #999;">Threshold</td><td style="padding: 6px 0; text-align: right; font-weight: 600;">{threshold * 100:.0f}%</td></tr>
  </table>
  <p style="color: #666; line-height: 1.5;">
    To resume service, increase your budget or upgrade your plan in the
    <a href="https://zero-human-labs.com/dashboard" style="color: #00ff88;">dashboard</a>.
  </p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">Zero Human Labs</p>
</div>""",
    )


def _emit_budget_depleted_event(
    *,
    tenant: Tenant,
    budget_limit: float,
    current_spend: float,
    attempted_cost: float,
) -> None:
    """Persist an explicit budget-depleted event for observability."""
    if _db is not None:
        _db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": "gateway",
                "agent_id": "gateway",
                "event_type": "budget.depleted",
                "tokens_in": 0,
                "tokens_out": 0,
                "timestamp": time.time(),
                "metadata": {
                    "budget_limit_usd": budget_limit,
                    "total_spent_usd": current_spend,
                    "attempted_cost_usd": attempted_cost,
                },
            }
        )
    logger.warning(
        "budget.depleted tenant=%s spent=%.6f limit=%.6f attempted=%.6f",
        tenant.tenant_id,
        current_spend,
        budget_limit,
        attempted_cost,
    )
    if _event_tracker is not None:
        _event_tracker.track(
            METRIC_BUDGET_DEPLETED,
            tenant_id=tenant.tenant_id,
            budget_limit_usd=budget_limit,
            total_spent_usd=current_spend,
            attempted_cost_usd=attempted_cost,
        )
    _send_budget_warning_email(
        tenant=tenant,
        subject="Budget limit reached — requests blocked",
        html=f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="margin: 0 0 16px; color: #e53e3e;">Budget Depleted</h2>
  <p style="color: #666; line-height: 1.5;">
    Your account has hit its <strong>${budget_limit:,.2f}</strong> budget limit.
    New requests are being <strong>blocked</strong> until the limit is raised.
  </p>
  <table style="width: 100%; margin: 24px 0; border-collapse: collapse;">
    <tr><td style="padding: 6px 0; color: #999;">Total spent</td><td style="padding: 6px 0; text-align: right; font-weight: 600;">${current_spend:,.2f}</td></tr>
    <tr><td style="padding: 6px 0; color: #999;">Budget limit</td><td style="padding: 6px 0; text-align: right; font-weight: 600;">${budget_limit:,.2f}</td></tr>
  </table>
  <p style="color: #666; line-height: 1.5;">
    Increase your budget or upgrade your plan in the
    <a href="https://zero-human-labs.com/dashboard" style="color: #00ff88;">dashboard</a>.
  </p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
  <p style="color: #999; font-size: 12px;">Zero Human Labs</p>
</div>""",
    )


_budget_email_sent: dict[str, float] = {}
_BUDGET_EMAIL_COOLDOWN = 3600  # 1 hour between emails per tenant


def _send_budget_warning_email(*, tenant: Tenant, subject: str, html: str) -> None:
    """Send a budget warning email to the tenant if they have an email on file.

    Rate-limited to one email per tenant per hour to prevent spam on repeated
    budget-exceeded requests. Runs in a background thread to avoid blocking the
    gateway request path.
    """
    email = tenant.metadata.get("email")
    if not email:
        logger.debug(
            "No email on file for tenant %s — skipping budget notification",
            tenant.tenant_id,
        )
        return

    now = time.time()
    last_sent = _budget_email_sent.get(tenant.tenant_id, 0)
    if now - last_sent < _BUDGET_EMAIL_COOLDOWN:
        logger.debug(
            "Budget email for tenant %s suppressed (cooldown)", tenant.tenant_id
        )
        return
    _budget_email_sent[tenant.tenant_id] = now

    threading.Thread(
        target=send_email,
        kwargs={"to": email, "subject": subject, "html": html},
        daemon=True,
    ).start()


def _calc_provider_cost(model: ModelConfig, tokens_in: int, tokens_out: int) -> float:
    """Calculate raw provider cost for a request."""
    return (tokens_in / 1000) * model.cost_per_1k_input + (
        tokens_out / 1000
    ) * model.cost_per_1k_output


def _calc_customer_cost(model: ModelConfig, tokens_in: int, tokens_out: int) -> float:
    """Calculate what the customer pays (provider cost + markup)."""
    provider = _calc_provider_cost(model, tokens_in, tokens_out)
    return provider * (1 + model.markup_rate)


def _is_stream_retryable(exc: Exception) -> bool:
    """Return True when a pre-stream failure should be retried."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _STREAM_RETRYABLE_STATUS_CODES
    return False


async def _stream_response(
    *,
    provider: Any,
    model_config: ModelConfig,
    messages: list[dict],
    request_id: str,
    tenant: Tenant,
    start_time: float,
    routed_by: str,
    complexity: str | None,
    estimated_cost: float,
    gateway_config: GatewayConfig | None = None,
    provider_registry: ProviderRegistry | None = None,
    byok: bool = False,
    **kwargs: Any,
) -> Any:
    """Generate SSE stream in OpenAI-compatible format.

    Attempts the primary provider first. If the stream fails before
    yielding any data, tries fallback providers.
    """
    total_tokens_in = 0
    total_tokens_out = 0
    active_model = model_config
    stream_started = False

    try:
        # Build list of (provider, model_config) to try
        candidates = [(provider, model_config)]
        if gateway_config is not None and provider_registry is not None:
            for fb_model in gateway_config.get_fallbacks(model_config.model_id):
                fb_provider = provider_registry.get(
                    fb_model.provider, fb_model.base_url
                )
                if fb_provider is not None:
                    candidates.append((fb_provider, fb_model))

        for attempt_provider, attempt_model in candidates:
            retries_left = _STREAM_CONNECT_MAX_RETRIES
            retry_delay = _STREAM_RETRY_DELAY_SECONDS
            while True:
                try:
                    async for chunk in attempt_provider.chat_completion_stream(
                        model=attempt_model.actual_model, messages=messages, **kwargs
                    ):
                        stream_started = True
                        active_model = attempt_model
                        if chunk.usage:
                            total_tokens_in = chunk.usage.prompt_tokens
                            total_tokens_out = chunk.usage.completion_tokens

                        sse_data: dict[str, Any] = {
                            "id": request_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": attempt_model.model_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": chunk.finish_reason,
                                }
                            ],
                        }
                        if chunk.delta_content:
                            sse_data["choices"][0]["delta"]["content"] = (
                                chunk.delta_content
                            )
                        if chunk.usage:
                            sse_data["usage"] = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens,
                            }
                        yield f"data: {json.dumps(sse_data)}\n\n"

                    yield "data: [DONE]\n\n"
                    return
                except Exception as exc:
                    if stream_started:
                        # Already sent data to client — can't switch providers
                        logger.warning(
                            "Stream failed mid-response for tenant %s model %s",
                            tenant.tenant_id,
                            attempt_model.model_id,
                        )
                        yield f"data: {json.dumps({'error': 'Upstream provider error'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    if retries_left > 0 and _is_stream_retryable(exc):
                        logger.warning(
                            "Stream connect failed for %s, retrying (%d left): %s",
                            attempt_model.model_id,
                            retries_left,
                            type(exc).__name__,
                        )
                        retries_left -= 1
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    # No data sent and no retry path left — try fallback provider
                    logger.warning(
                        "Stream connect failed for %s, trying fallback: %s",
                        attempt_model.model_id,
                        type(exc).__name__,
                    )
                    break
        else:
            # All providers failed before any data was sent
            yield f"data: {json.dumps({'error': 'Upstream provider error'})}\n\n"
            yield "data: [DONE]\n\n"
    finally:
        latency_ms = (time.time() - start_time) * 1000

        # Settle budget: replace estimate with actual cost
        actual_cost = (
            0.0
            if byok
            else _calc_customer_cost(active_model, total_tokens_in, total_tokens_out)
        )
        _settle_budget(tenant, estimated_cost, actual_cost)

        _record_usage(
            tenant=tenant,
            model_id=active_model.model_id,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost_per_1k_input=active_model.cost_per_1k_input,
            cost_per_1k_output=active_model.cost_per_1k_output,
            markup_rate=active_model.markup_rate,
            request_id=request_id,
            byok=byok,
        )
        _log_request(
            request_id=request_id,
            tenant=tenant,
            model_config=active_model,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            latency_ms=latency_ms,
            cached=False,
            routed_by=routed_by,
            complexity=complexity,
            byok=byok,
        )


def _log_request(
    *,
    request_id: str,
    tenant: Tenant,
    model_config: ModelConfig,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
    cached: bool,
    routed_by: str,
    complexity: str | None,
    byok: bool = False,
) -> None:
    """Log request to gateway_requests table with cost breakdown."""
    if _db is None:
        return
    if byok:
        # BYOK: tenant pays provider directly, we charge nothing
        provider_cost = 0.0
        customer_cost = 0.0
        margin = 0.0
    else:
        provider_cost = _calc_provider_cost(model_config, tokens_in, tokens_out)
        if cached:
            provider_cost = 0.0  # cache hit = zero provider cost
        customer_cost = _calc_customer_cost(model_config, tokens_in, tokens_out)
        margin = customer_cost - provider_cost

    _db.save_gateway_request(
        {
            "request_id": request_id,
            "tenant_id": tenant.tenant_id,
            "model_id": model_config.model_id,
            "provider": model_config.provider,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 2),
            "provider_cost": round(provider_cost, 6),
            "customer_cost": round(customer_cost, 6),
            "margin": round(margin, 6),
            "cached": cached,
            "routed_by": routed_by,
            "complexity": complexity,
            "status": "ok",
            "timestamp": time.time(),
        }
    )


def _record_usage(
    *,
    tenant: Tenant,
    model_id: str,
    tokens_in: int,
    tokens_out: int,
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    markup_rate: float = 0.30,
    request_id: str = "",
    byok: bool = False,
) -> None:
    """Record token usage to metering collector, DB, and Stripe."""
    from agency_os.metering.stripe_hook import report_gateway_usage

    timestamp = time.time()

    if _metering is not None:
        _metering.record_llm_call(
            tenant_id=tenant.tenant_id,
            org_id="gateway",
            agent_id="gateway",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model_id,
        )

    if _db is not None:
        _db.save_metering_event(
            {
                "tenant_id": tenant.tenant_id,
                "org_id": "gateway",
                "agent_id": "gateway",
                "event_type": "llm_call",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "timestamp": timestamp,
                "metadata": {"model": model_id, "source": "gateway"},
            }
        )

    # Report to Stripe if configured (skip for BYOK — tenant pays provider directly)
    customer_id = tenant.metadata.get("stripe_customer_id")
    if _stripe_billing is not None and customer_id and not byok:
        # Use request_id for idempotency; fall back to timestamp-based id
        resolved_request_id = request_id or (
            f"{tenant.tenant_id}_{model_id}_{int(timestamp * 1000)}"
        )
        report_gateway_usage(
            _stripe_billing,
            tenant_id=tenant.tenant_id,
            stripe_customer_id=customer_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_per_1k_input=cost_per_1k_input,
            cost_per_1k_output=cost_per_1k_output,
            markup_rate=markup_rate,
            request_id=resolved_request_id,
        )

    # Track free demo consumption for unpaid free-tier tenants.
    record_free_tier_usage(tenant, tokens_in + tokens_out)
