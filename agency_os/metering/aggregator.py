"""Roll up metering data per tenant per billing period."""

from __future__ import annotations

import time
from dataclasses import dataclass

from agency_os.metering.collector import MeteringCollector


@dataclass
class BillingPeriod:
    """A billing period summary."""

    tenant_id: str
    period_start: float
    period_end: float
    total_tokens_in: int
    total_tokens_out: int
    total_events: int
    total_cost_usd: float
    provider_cost_usd: float = 0.0
    margin_usd: float = 0.0


# Provider cost: what Anthropic/OpenAI charges us
DEFAULT_COST_PER_1K_INPUT = 0.003
DEFAULT_COST_PER_1K_OUTPUT = 0.015

# Default markup: 30% margin on provider cost
DEFAULT_MARGIN_RATE = 0.30


class MeteringAggregator:
    """
    Aggregates metering data into billing periods.

    Applies a margin on top of provider costs to generate revenue.
    ``total_cost_usd`` is what the customer pays; ``provider_cost_usd``
    is the raw LLM cost; ``margin_usd`` is the difference.
    """

    def __init__(
        self,
        collector: MeteringCollector,
        cost_per_1k_input: float = DEFAULT_COST_PER_1K_INPUT,
        cost_per_1k_output: float = DEFAULT_COST_PER_1K_OUTPUT,
        margin_rate: float = DEFAULT_MARGIN_RATE,
    ):
        self._collector = collector
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output
        if not 0.0 <= margin_rate <= 5.0:
            raise ValueError(
                f"margin_rate must be between 0.0 and 5.0, got {margin_rate}"
            )
        self._margin_rate = margin_rate

    def aggregate(
        self,
        tenant_id: str,
        period_start: float | None = None,
        period_end: float | None = None,
    ) -> BillingPeriod:
        """
        Aggregate usage for a tenant within a time period.

        Defaults to last 30 days if no period specified.
        """
        now = time.time()
        if period_end is None:
            period_end = now
        if period_start is None:
            period_start = now - (30 * 24 * 3600)  # 30 days

        events = self._collector.get_tenant_events(tenant_id)
        period_events = [e for e in events if period_start <= e.timestamp <= period_end]

        tokens_in = sum(e.tokens_in for e in period_events)
        tokens_out = sum(e.tokens_out for e in period_events)

        provider_cost = (tokens_in / 1000) * self._cost_per_1k_input + (
            tokens_out / 1000
        ) * self._cost_per_1k_output
        margin = provider_cost * self._margin_rate
        customer_cost = provider_cost + margin

        return BillingPeriod(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            total_events=len(period_events),
            total_cost_usd=round(customer_cost, 4),
            provider_cost_usd=round(provider_cost, 4),
            margin_usd=round(margin, 4),
        )
