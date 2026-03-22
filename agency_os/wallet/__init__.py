"""Wallet module — public protocol definitions + optional CDP integration.

Public API (always available):
- Wallet, WalletTransaction (data models)
- X402Protocol, X402PaymentRequest, X402PaymentProof, X402Middleware
- AuditLogger, AuditEvent, AuditEventType

Private API (requires wallet_private / CDP SDK):
- AgenticWalletClient, WalletConfig — re-exported from wallet_private
  when installed; ImportError otherwise.
"""

from __future__ import annotations

from agency_os.wallet.audit import AuditEvent, AuditEventType, AuditLogger
from agency_os.wallet.models import Wallet, WalletTransaction
from agency_os.wallet.x402 import (
    X402Middleware,
    X402PaymentProof,
    X402PaymentRequest,
    X402Protocol,
)

__all__ = [
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "Wallet",
    "WalletTransaction",
    "X402Protocol",
    "X402PaymentRequest",
    "X402PaymentProof",
    "X402Middleware",
]

# Backward-compat: re-export private classes when available
try:
    from agency_os.wallet_private.agentic_client import AgenticWalletClient
    from agency_os.wallet_private.config import WalletConfig

    __all__ += ["AgenticWalletClient", "WalletConfig"]
except ImportError:
    pass
