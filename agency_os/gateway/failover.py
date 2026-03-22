"""Provider failover with retry for the LLM gateway.

Wraps provider calls with:
- Retries on transient errors (rate limits, timeouts, server errors)
- Cross-provider fallback when retries are exhausted
- Failover tracking for observability
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from agency_os.gateway.config import GatewayConfig, ModelConfig
from agency_os.gateway.providers.base import CompletionResult, LLMProvider
from agency_os.gateway.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

# Transient HTTP status codes that warrant a retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Default retry config
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 0.5  # seconds, doubles each retry


@dataclass
class FailoverResult:
    """Result of a provider call with failover metadata."""

    result: CompletionResult
    model_config: ModelConfig
    provider: LLMProvider
    failed_over: bool = False
    original_model: str | None = None
    attempts: int = 1
    errors: list[str] = field(default_factory=list)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is transient and worth retrying."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


async def call_with_failover(
    *,
    provider: LLMProvider,
    model_config: ModelConfig,
    messages: list[dict],
    gateway_config: GatewayConfig,
    provider_registry: ProviderRegistry,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    **kwargs: Any,
) -> FailoverResult:
    """Call a provider with retry and cross-provider fallback.

    1. Try the primary provider up to max_retries times
    2. On exhaustion, try each fallback model's provider once
    3. Raise the last error if all options fail
    """
    errors: list[str] = []
    attempts = 0

    # Phase 1: Retry primary provider
    delay = retry_delay
    for attempt in range(max_retries + 1):
        attempts += 1
        try:
            result = await provider.chat_completion(
                model=model_config.actual_model,
                messages=messages,
                **kwargs,
            )
            return FailoverResult(
                result=result,
                model_config=model_config,
                provider=provider,
                attempts=attempts,
                errors=errors,
            )
        except Exception as exc:
            error_msg = f"{model_config.model_id}: {type(exc).__name__}"
            errors.append(error_msg)
            logger.warning(
                "Provider attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries + 1,
                model_config.model_id,
                type(exc).__name__,
            )
            if attempt < max_retries and _is_retryable(exc):
                await asyncio.sleep(delay)
                delay *= 2
                continue
            break

    # Phase 2: Cross-provider fallback
    fallbacks = gateway_config.get_fallbacks(model_config.model_id)
    original_model = model_config.model_id

    for fb_model in fallbacks:
        fb_provider = provider_registry.get(fb_model.provider, fb_model.base_url)
        if fb_provider is None:
            continue

        attempts += 1
        try:
            result = await fb_provider.chat_completion(
                model=fb_model.actual_model,
                messages=messages,
                **kwargs,
            )
            logger.info(
                "Failover succeeded: %s -> %s",
                original_model,
                fb_model.model_id,
            )
            return FailoverResult(
                result=result,
                model_config=fb_model,
                provider=fb_provider,
                failed_over=True,
                original_model=original_model,
                attempts=attempts,
                errors=errors,
            )
        except Exception as exc:
            error_msg = f"{fb_model.model_id}: {type(exc).__name__}"
            errors.append(error_msg)
            logger.warning(
                "Fallback %s also failed: %s",
                fb_model.model_id,
                type(exc).__name__,
            )

    # All options exhausted
    raise RuntimeError(f"All providers failed for {original_model}: {errors}") from None
