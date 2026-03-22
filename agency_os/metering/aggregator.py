"""Billing period aggregation shim.

Pricing constants and aggregation logic live in metering_private.
When metering_private is not installed, placeholder constants are
provided so dependent code can still import and function in
development/open-source mode (with zero-cost defaults).
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from agency_os.metering_private.aggregator import (  # noqa: F401
        DEFAULT_COST_PER_1K_INPUT,
        DEFAULT_COST_PER_1K_OUTPUT,
        DEFAULT_MARGIN_RATE,
        MeteringAggregator,
    )
except ImportError:
    # Open-source defaults: no margin, zero cost (metering still works,
    # but cost calculations return 0).
    DEFAULT_COST_PER_1K_INPUT: float = 0.0  # type: ignore[no-redef]
    DEFAULT_COST_PER_1K_OUTPUT: float = 0.0  # type: ignore[no-redef]
    DEFAULT_MARGIN_RATE: float = 0.0  # type: ignore[no-redef]
    MeteringAggregator = None  # type: ignore[assignment,misc]


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
