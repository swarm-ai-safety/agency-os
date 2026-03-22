"""Smart model router — picks cheapest adequate model for each request.

When ``model="auto"`` the router classifies the request complexity
(simple / medium / complex) and maps it to the cheapest model tier.
Customers pay less, the platform keeps the margin difference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agency_os.gateway.config import GatewayConfig, ModelConfig
from agency_os.gateway.routing_feedback import RoutingFeedback


class Complexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class RoutingDecision:
    """Result of the smart router's model selection."""

    model: ModelConfig
    complexity: Complexity
    reason: str


# Heuristic signals for complexity classification
_COMPLEX_PATTERNS = re.compile(
    r"(?i)"
    r"(?:analyze|reason|compare|evaluate|critique|debug|architect|design|plan|prove|derive)"
    r"|(?:step.by.step|chain.of.thought|think.carefully|in.depth)"
    r"|(?:write.(?:a\s)?(?:full|complete|detailed|comprehensive))"
    r"|(?:code.review|refactor|optimize|security.audit)"
    r"|(?:essay|report|whitepaper|proposal|strategy)"
)

_SIMPLE_PATTERNS = re.compile(
    r"(?i)"
    r"(?:^(?:hi|hello|hey|thanks|thank you|yes|no|ok|okay)\b)"
    r"|(?:translate|summarize|classify|label|extract|list|convert|format)"
    r"|(?:what.is|who.is|when.was|define|explain.briefly)"
    r"|(?:true.or.false|yes.or.no|pick.one)"
)

# Token thresholds for complexity escalation
_SHORT_MSG_TOKENS = 100  # rough char/4 heuristic
_LONG_MSG_TOKENS = 2000


def classify_complexity(messages: list[dict[str, Any]]) -> Complexity:
    """Classify request complexity using heuristics.

    Uses message content patterns, conversation length, and
    total content size to estimate whether a request needs
    a frontier model or can be handled by a cheaper one.
    """
    # Get the last user message (most relevant for routing)
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return Complexity.MEDIUM

    last_user = user_messages[-1].get("content", "")
    total_chars = sum(len(m.get("content", "")) for m in messages)
    num_turns = len(messages)

    # Check for explicit complexity signals
    if _COMPLEX_PATTERNS.search(last_user):
        return Complexity.COMPLEX

    if _SIMPLE_PATTERNS.search(last_user) and total_chars < _LONG_MSG_TOKENS * 4:
        return Complexity.SIMPLE

    # Length-based heuristics
    if total_chars > _LONG_MSG_TOKENS * 4:
        # Long context = likely complex
        return Complexity.COMPLEX

    if num_turns > 6:
        # Multi-turn conversations benefit from better models
        return Complexity.MEDIUM

    if total_chars < _SHORT_MSG_TOKENS * 4:
        return Complexity.SIMPLE

    return Complexity.MEDIUM


# Model tier mapping: complexity -> preferred model IDs (cheapest first)
_DEFAULT_TIER_MAP: dict[Complexity, list[str]] = {
    Complexity.SIMPLE: ["gpt-4.1-nano", "gpt-4o-mini", "claude-haiku-4"],
    Complexity.MEDIUM: ["gpt-4.1-mini", "gpt-4o-mini", "claude-haiku-4", "gpt-4o"],
    Complexity.COMPLEX: ["gpt-4o", "gpt-4.1", "claude-sonnet-4", "claude-opus-4"],
}

_DEFAULT_TASK_CLASS = "cost"

# Task class policy mapping: task_class -> complexity tier -> model preference order.
_DEFAULT_TASK_CLASS_MAP: dict[str, dict[Complexity, list[str]]] = {
    "cost": _DEFAULT_TIER_MAP,
    "latency": {
        Complexity.SIMPLE: [
            "gpt-4.1-nano",
            "groq-llama-3.1-8b",
            "gpt-4o-mini",
            "claude-haiku-4",
        ],
        Complexity.MEDIUM: [
            "groq-llama-3.1-70b",
            "gpt-4o-mini",
            "gpt-4.1-mini",
            "claude-haiku-4",
            "gpt-4o",
        ],
        Complexity.COMPLEX: ["gpt-4o", "claude-sonnet-4", "gpt-4.1", "claude-opus-4"],
    },
    "quality": {
        Complexity.SIMPLE: ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "claude-sonnet-4"],
        Complexity.MEDIUM: ["gpt-4o", "gpt-4.1", "claude-sonnet-4", "claude-opus-4"],
        Complexity.COMPLEX: ["claude-opus-4", "gpt-4.1", "claude-sonnet-4", "gpt-4o"],
    },
}


class SmartRouter:
    """Routes ``model="auto"`` requests to the cheapest adequate model."""

    def __init__(
        self,
        config: GatewayConfig,
        tier_map: dict[Complexity, list[str]] | None = None,
        task_class_map: dict[str, dict[Complexity, list[str]]] | None = None,
        feedback: RoutingFeedback | None = None,
    ) -> None:
        self._config = config
        self._tier_map = tier_map or _DEFAULT_TIER_MAP
        if task_class_map is None:
            task_class_map = _DEFAULT_TASK_CLASS_MAP
        self._task_class_map = task_class_map
        self._feedback = feedback

    def route(
        self,
        messages: list[dict[str, Any]],
        *,
        tenant_metadata: dict[str, Any] | None = None,
        budget: str | None = None,
        task_class: str | None = None,
    ) -> RoutingDecision:
        """Select a model for the given messages.

        Args:
            messages: The chat messages to route.
            tenant_metadata: Tenant metadata for access control.
            budget: Optional budget hint ("low", "medium", "high").
            task_class: Optional policy target ("quality", "latency", "cost").
        """
        complexity = classify_complexity(messages)

        # Resolve task class with request override > tenant default > cost.
        if task_class is None and tenant_metadata:
            task_class = tenant_metadata.get("default_task_class")
        task_class = str(task_class or _DEFAULT_TASK_CLASS).lower()
        if task_class not in self._task_class_map:
            task_class = _DEFAULT_TASK_CLASS

        # Budget hint can override complexity
        if budget == "low":
            complexity = Complexity.SIMPLE
            task_class = "cost"
        elif budget == "high":
            complexity = Complexity.COMPLEX
            task_class = "quality"

        # Get available models for this tenant
        available = {m.model_id for m in self._config.list_models(tenant_metadata)}

        # Find preferred available model for this task class + complexity tier.
        task_class_tiers = self._task_class_map.get(task_class, self._tier_map)
        candidates = list(task_class_tiers.get(complexity, self._tier_map[complexity]))

        # Re-rank candidates using eval feedback when available
        if self._feedback is not None:
            candidates = self._feedback.get_model_ranking(complexity.value, candidates)

        for model_id in candidates:
            if model_id in available:
                model = self._config.get_model(model_id)
                if model and model.enabled:
                    return RoutingDecision(
                        model=model,
                        complexity=complexity,
                        reason=f"auto-routed: {complexity.value}/{task_class} -> {model_id}",
                    )

        # Fallback: cheapest available model by input cost
        all_models = sorted(
            self._config.list_models(tenant_metadata),
            key=lambda m: m.cost_per_1k_input,
        )
        if all_models:
            return RoutingDecision(
                model=all_models[0],
                complexity=complexity,
                reason=f"auto-routed: fallback -> {all_models[0].model_id}",
            )

        raise ValueError("No models available for routing")
