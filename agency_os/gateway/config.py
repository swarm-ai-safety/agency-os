"""Gateway model configuration and pricing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from agency_os.metering.aggregator import DEFAULT_MARGIN_RATE

ProviderType = Literal[
    "openai",
    "anthropic",
    "ollama",
    "together",
    "fireworks",
    "groq",
    "custom_openai",
]


class ModelConfig(BaseModel):
    """Configuration for a single model available through the gateway."""

    model_id: str
    provider: ProviderType
    actual_model: str  # Real model name sent to the provider
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    markup_rate: float = DEFAULT_MARGIN_RATE
    max_tokens_limit: int = 128_000
    enabled: bool = True
    base_url: str | None = None  # Custom API base URL (OpenAI-compatible endpoints)


# Default model registry
_DEFAULT_MODELS: list[ModelConfig] = [
    # OpenAI
    ModelConfig(
        model_id="gpt-4o",
        provider="openai",
        actual_model="gpt-4o",
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
    ),
    ModelConfig(
        model_id="gpt-4o-mini",
        provider="openai",
        actual_model="gpt-4o-mini",
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
    ),
    ModelConfig(
        model_id="gpt-4.1",
        provider="openai",
        actual_model="gpt-4.1",
        cost_per_1k_input=0.002,
        cost_per_1k_output=0.008,
    ),
    ModelConfig(
        model_id="gpt-4.1-mini",
        provider="openai",
        actual_model="gpt-4.1-mini",
        cost_per_1k_input=0.0004,
        cost_per_1k_output=0.0016,
    ),
    ModelConfig(
        model_id="gpt-4.1-nano",
        provider="openai",
        actual_model="gpt-4.1-nano",
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0004,
    ),
    # Anthropic — prices from https://platform.claude.com/docs/en/about-claude/pricing
    ModelConfig(
        model_id="claude-opus-4.6",
        provider="anthropic",
        actual_model="claude-opus-4-6-20250715",
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.025,
    ),
    ModelConfig(
        model_id="claude-opus-4.5",
        provider="anthropic",
        actual_model="claude-opus-4-5-20250620",
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.025,
    ),
    ModelConfig(
        model_id="claude-opus-4",
        provider="anthropic",
        actual_model="claude-opus-4-20250514",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    ),
    ModelConfig(
        model_id="claude-sonnet-4.6",
        provider="anthropic",
        actual_model="claude-sonnet-4-6-20250715",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    ModelConfig(
        model_id="claude-sonnet-4.5",
        provider="anthropic",
        actual_model="claude-sonnet-4-5-20250620",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    ModelConfig(
        model_id="claude-sonnet-4",
        provider="anthropic",
        actual_model="claude-sonnet-4-20250514",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    ModelConfig(
        model_id="claude-haiku-4.5",
        provider="anthropic",
        actual_model="claude-haiku-4-5-20251001",
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.005,
    ),
    ModelConfig(
        model_id="claude-haiku-3.5",
        provider="anthropic",
        actual_model="claude-3-5-haiku-20241022",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
    ),
    # Together AI — open models
    ModelConfig(
        model_id="llama-3.1-70b",
        provider="together",
        actual_model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        cost_per_1k_input=0.00088,
        cost_per_1k_output=0.00088,
        max_tokens_limit=131_072,
    ),
    ModelConfig(
        model_id="llama-3.1-8b",
        provider="together",
        actual_model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        cost_per_1k_input=0.00018,
        cost_per_1k_output=0.00018,
        max_tokens_limit=131_072,
    ),
    ModelConfig(
        model_id="mistral-small",
        provider="together",
        actual_model="mistralai/Mistral-Small-24B-Instruct-2501",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.0008,
        max_tokens_limit=32_768,
    ),
    # Fireworks AI
    ModelConfig(
        model_id="fireworks-llama-3.1-70b",
        provider="fireworks",
        actual_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        cost_per_1k_input=0.0009,
        cost_per_1k_output=0.0009,
        max_tokens_limit=131_072,
    ),
    # Groq — ultra-low latency
    ModelConfig(
        model_id="groq-llama-3.1-70b",
        provider="groq",
        actual_model="llama-3.1-70b-versatile",
        cost_per_1k_input=0.00059,
        cost_per_1k_output=0.00079,
        max_tokens_limit=131_072,
    ),
    ModelConfig(
        model_id="groq-llama-3.1-8b",
        provider="groq",
        actual_model="llama-3.1-8b-instant",
        cost_per_1k_input=0.00005,
        cost_per_1k_output=0.00008,
        max_tokens_limit=131_072,
    ),
]


# Cross-provider fallback mappings: model_id -> list of fallback model_ids
# Used when the primary provider is down or rate-limited.
DEFAULT_FALLBACKS: dict[str, list[str]] = {
    "gpt-4o": ["claude-sonnet-4", "llama-3.1-70b"],
    "gpt-4.1": ["claude-sonnet-4", "llama-3.1-70b"],
    "gpt-4o-mini": ["claude-haiku-4", "llama-3.1-8b"],
    "gpt-4.1-mini": ["claude-haiku-4", "llama-3.1-8b"],
    "gpt-4.1-nano": ["claude-haiku-4", "groq-llama-3.1-8b"],
    "claude-sonnet-4": ["gpt-4o", "llama-3.1-70b"],
    "claude-opus-4": ["gpt-4.1", "llama-3.1-70b"],
    "claude-haiku-4": ["gpt-4o-mini", "llama-3.1-8b"],
    # Open model fallbacks — cross-provider for resilience
    "llama-3.1-70b": ["fireworks-llama-3.1-70b", "groq-llama-3.1-70b"],
    "llama-3.1-8b": ["groq-llama-3.1-8b"],
    "mistral-small": ["llama-3.1-70b"],
    "fireworks-llama-3.1-70b": ["llama-3.1-70b", "groq-llama-3.1-70b"],
    "groq-llama-3.1-70b": ["llama-3.1-70b", "fireworks-llama-3.1-70b"],
    "groq-llama-3.1-8b": ["llama-3.1-8b"],
}


class GatewayConfig:
    """Model registry with pricing and tenant access control."""

    def __init__(
        self,
        models: list[ModelConfig] | None = None,
        default_markup: float = DEFAULT_MARGIN_RATE,
        fallbacks: dict[str, list[str]] | None = None,
    ) -> None:
        self._default_markup = default_markup
        self._models: dict[str, ModelConfig] = {}
        for m in models or _DEFAULT_MODELS:
            self._models[m.model_id] = m
        self._fallbacks = fallbacks if fallbacks is not None else DEFAULT_FALLBACKS

    def get_model(self, model_id: str) -> ModelConfig | None:
        """Look up a model by ID."""
        return self._models.get(model_id)

    def list_models(
        self, tenant_metadata: dict[str, Any] | None = None
    ) -> list[ModelConfig]:
        """List models available to a tenant.

        If tenant has ``allowed_models`` in metadata, filter to that list.
        Otherwise return all enabled models.
        """
        enabled = [m for m in self._models.values() if m.enabled]
        if tenant_metadata:
            allowed = tenant_metadata.get("allowed_models")
            if allowed:
                allowed_set = set(allowed)
                enabled = [m for m in enabled if m.model_id in allowed_set]
        return enabled

    def get_fallbacks(self, model_id: str) -> list[ModelConfig]:
        """Get fallback models for a given model, in priority order."""
        fallback_ids = self._fallbacks.get(model_id, [])
        return [
            self._models[fid]
            for fid in fallback_ids
            if fid in self._models and self._models[fid].enabled
        ]

    def customer_price_per_1k(
        self, model: ModelConfig, direction: str = "input"
    ) -> float:
        """Calculate customer-facing price per 1K tokens (cost + markup)."""
        cost = (
            model.cost_per_1k_input
            if direction == "input"
            else model.cost_per_1k_output
        )
        return cost * (1 + model.markup_rate)
