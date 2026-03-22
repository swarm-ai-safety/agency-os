"""Stripe metered billing integration shim.

Full implementation lives in metering_private. This shim re-exports
when available, and provides no-op stubs when not installed.
"""

from __future__ import annotations

try:
    from agency_os.metering_private.stripe_hook import (  # noqa: F401
        StripeHook,
        report_gateway_usage,
    )
except ImportError:
    import logging
    from typing import Any

    from agency_os.metering.aggregator import BillingPeriod

    logger = logging.getLogger(__name__)

    class StripeHook:  # type: ignore[no-redef]
        """No-op stub when metering_private is not installed."""

        def __init__(self, api_key: str | None = None):
            self._reported: list[dict[str, Any]] = []

        def report_usage(
            self, subscription_item_id: str, period: BillingPeriod
        ) -> dict[str, Any]:
            record = {"stub": True, "tenant_id": period.tenant_id}
            self._reported.append(record)
            return record

        def report_usage_meter(
            self,
            stripe_customer_id: str,
            period: BillingPeriod,
            meter_event_name: str = "agency_os_token_usage",
        ) -> dict[str, Any]:
            record = {"stub": True, "tenant_id": period.tenant_id}
            self._reported.append(record)
            return record

        @property
        def reported_records(self) -> list[dict[str, Any]]:
            return list(self._reported)

    def report_gateway_usage(  # type: ignore[no-redef]
        billing: Any, **kwargs: Any
    ) -> None:
        """No-op when metering_private is not installed."""
        pass
