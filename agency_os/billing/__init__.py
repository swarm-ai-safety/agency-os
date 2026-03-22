"""Billing stub — re-exports from billing_private when available.

The proprietary Stripe billing code lives in agency_os.billing_private.
This shim lets legacy ``from agency_os.billing.stripe_billing import …``
paths keep working while the private module is installed.
"""
