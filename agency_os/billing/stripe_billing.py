"""Backward-compat shim — delegates to billing_private.stripe_billing.

Allows existing ``from agency_os.billing.stripe_billing import StripeBilling``
to keep working. Raises ImportError when billing_private is not installed,
which every call-site already handles gracefully.
"""

from agency_os.billing_private.stripe_billing import StripeBilling  # noqa: F401

__all__ = ["StripeBilling"]
