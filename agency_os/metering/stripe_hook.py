"""Stripe metered billing integration.

This module provides two reporting paths:
1. Legacy SubscriptionItem usage records (StripeHook.report_usage)
2. Stripe Meter Events via StripeBilling (StripeHook.report_usage_meter)

Path 2 is recommended for new integrations — it uses Stripe's newer Meters API
which supports token-based billing natively.
"""

from __future__ import annotations

import logging
from typing import Any

from agency_os.metering.aggregator import BillingPeriod

logger = logging.getLogger(__name__)


class StripeHook:
    """
    Reports metered usage to Stripe.

    Maps internal token consumption to Stripe billable units.
    Requires `stripe` package for actual Stripe calls.
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._reported: list[dict[str, Any]] = []

    def report_usage(
        self,
        subscription_item_id: str,
        period: BillingPeriod,
    ) -> dict[str, Any]:
        """
        Report metered usage to Stripe for a billing period.

        Args:
            subscription_item_id: Stripe subscription item ID.
            period: Aggregated billing period data.

        Returns:
            Usage record dict (or mock for dev).
        """
        quantity = period.total_tokens_in + period.total_tokens_out
        billable_units = max(1, quantity // 1000)  # Bill per 1K tokens

        record = {
            "subscription_item_id": subscription_item_id,
            "quantity": billable_units,
            "tenant_id": period.tenant_id,
            "total_tokens": quantity,
            "cost_usd": period.total_cost_usd,
        }

        if self._api_key:
            try:
                import stripe

                # Use per-request client to avoid mutating global state
                client = stripe.StripeClient(self._api_key)
                usage_record = client.subscription_items.create_usage_record(
                    subscription_item_id,
                    params={"quantity": billable_units, "action": "set"},
                )
                record["stripe_id"] = usage_record.id
                logger.info(
                    f"Reported {billable_units} units to Stripe for {period.tenant_id}"
                )
            except ImportError:
                logger.warning("stripe package not installed, recording locally only")
            except Exception as e:
                logger.error(f"Stripe reporting failed: {e}")
                record["error"] = str(e)
        else:
            logger.info(
                f"Stripe dry-run: {billable_units} units for {period.tenant_id}"
            )

        self._reported.append(record)
        return record

    def report_usage_meter(
        self,
        stripe_customer_id: str,
        period: BillingPeriod,
        meter_event_name: str = "agency_os_token_usage",
    ) -> dict[str, Any]:
        """Report usage via Stripe Meter Events (newer API).

        Requires StripeBilling to be configured. Falls back to local
        recording if Stripe is not available.
        """
        quantity = period.total_tokens_in + period.total_tokens_out
        billable_units = max(1, quantity // 1000)

        record = {
            "stripe_customer_id": stripe_customer_id,
            "quantity": billable_units,
            "tenant_id": period.tenant_id,
            "total_tokens": quantity,
            "cost_usd": period.total_cost_usd,
            "method": "meter_event",
        }

        try:
            from agency_os.billing_private.stripe_billing import StripeBilling

            billing = StripeBilling()
            # Generate deterministic event identifier for idempotency
            event_id = f"{period.tenant_id}_{period.period_start}_{period.period_end}"
            result = billing.create_meter_event(
                event_name=meter_event_name,
                stripe_customer_id=stripe_customer_id,
                value=billable_units,
                event_identifier=event_id,
            )
            record["meter_event"] = result
            logger.info(
                "Reported %d units via meter event for %s",
                billable_units,
                period.tenant_id,
            )
        except Exception as e:
            logger.error("Meter event reporting failed: %s", e)
            record["error"] = str(e)

        self._reported.append(record)
        return record

    @property
    def reported_records(self) -> list[dict[str, Any]]:
        return list(self._reported)


def report_gateway_usage(
    billing: Any,
    *,
    tenant_id: str,
    stripe_customer_id: str,
    tokens_in: int,
    tokens_out: int,
    cost_per_1k_input: float,
    cost_per_1k_output: float,
    markup_rate: float,
    request_id: str,
    meter_event_name: str = "agency_os_usage_cost",
) -> None:
    """Report a single gateway request's cost to Stripe as a meter event.

    Calculates the customer cost (provider cost + markup) for the specific
    model used, and reports in cents. This ensures per-model margins are
    maintained regardless of which model the customer selects.

    Args:
        billing: StripeBilling instance.
        tenant_id: Agency-OS tenant ID (for logging).
        stripe_customer_id: Stripe customer ID to attribute usage to.
        tokens_in: Input tokens consumed.
        tokens_out: Output tokens consumed.
        cost_per_1k_input: Provider cost per 1k input tokens for the model used.
        cost_per_1k_output: Provider cost per 1k output tokens for the model used.
        markup_rate: Margin rate (e.g. 0.30 for 30%).
        request_id: Gateway request ID, used as event_identifier for idempotency.
        meter_event_name: Stripe meter event name.
    """
    import math

    provider_cost = (tokens_in / 1000) * cost_per_1k_input + (
        tokens_out / 1000
    ) * cost_per_1k_output
    customer_cost = provider_cost * (1 + markup_rate)
    # Report in cents (1 unit = $0.01). Minimum 1 cent per request.
    billable_cents = max(1, math.ceil(customer_cost * 100))

    try:
        billing.create_meter_event(
            event_name=meter_event_name,
            stripe_customer_id=stripe_customer_id,
            value=billable_cents,
            event_identifier=request_id,
        )
        logger.info(
            "Reported %d cents ($%.4f) to Stripe for tenant %s model cost "
            "(in=%d out=%d, request %s)",
            billable_cents,
            customer_cost,
            tenant_id,
            tokens_in,
            tokens_out,
            request_id,
        )
    except Exception:
        logger.warning(
            "Failed to report Stripe meter event for tenant %s (request %s)",
            tenant_id,
            request_id,
        )
