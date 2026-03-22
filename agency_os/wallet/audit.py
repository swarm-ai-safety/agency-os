"""Audit logging for wallet operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Wallet audit event types."""

    WALLET_CREATED = "wallet_created"
    WALLET_EXPORTED = "wallet_exported"
    WALLET_IMPORTED = "wallet_imported"
    TRANSACTION_SENT = "transaction_sent"
    TRANSACTION_FAILED = "transaction_failed"
    BALANCE_CHECKED = "balance_checked"
    PAYMENT_VERIFIED = "payment_verified"
    PAYMENT_REJECTED = "payment_rejected"


class AuditEvent(BaseModel):
    """Structured audit log event."""

    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_id: str | None = Field(default=None, description="Agent performing action")
    wallet_id: str | None = Field(default=None)
    transaction_id: str | None = Field(default=None)
    amount_usdc: Decimal | None = Field(default=None)
    to_address: str | None = Field(default=None)
    from_address: str | None = Field(default=None)
    network: str | None = Field(default=None)
    status: str | None = Field(default=None)
    error: str | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)

    @field_serializer("amount_usdc", when_used="json")
    def serialize_amount_usdc(self, value: Decimal | None) -> str | None:
        """Serialize Decimal values as strings in JSON mode."""
        if value is None:
            return None
        return str(value)


class AuditLogger:
    """
    Structured audit logger for wallet operations.

    Emits structured logs for security-sensitive wallet operations
    including wallet creation, transactions, and exports.
    """

    def __init__(self, logger_name: str = "agency_os.wallet.audit"):
        """
        Initialize audit logger.

        Args:
            logger_name: Name for the audit logger
        """
        self._logger = logging.getLogger(logger_name)
        self._events: list[AuditEvent] = []

    def log_event(self, event: AuditEvent) -> None:
        """
        Log an audit event.

        Args:
            event: Audit event to log
        """
        self._events.append(event)

        # Emit structured log
        log_data = event.model_dump(exclude_none=True)
        self._logger.info(
            f"[AUDIT] {event.event_type.value}",
            extra={"audit_event": log_data},
        )

    def wallet_created(
        self,
        wallet_id: str,
        agent_id: str,
        address: str,
        network: str,
    ) -> None:
        """Log wallet creation."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.WALLET_CREATED,
                wallet_id=wallet_id,
                agent_id=agent_id,
                to_address=address,
                network=network,
                status="success",
            )
        )

    def wallet_exported(
        self,
        wallet_id: str,
        agent_id: str | None = None,
    ) -> None:
        """Log wallet export (sensitive operation)."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.WALLET_EXPORTED,
                wallet_id=wallet_id,
                agent_id=agent_id,
                status="success",
                metadata={"warning": "contains_sensitive_key_material"},
            )
        )

    def wallet_imported(
        self,
        wallet_id: str,
        agent_id: str | None = None,
    ) -> None:
        """Log wallet import."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.WALLET_IMPORTED,
                wallet_id=wallet_id,
                agent_id=agent_id,
                status="success",
            )
        )

    def transaction_sent(
        self,
        transaction_id: str,
        wallet_id: str,
        agent_id: str,
        amount_usdc: Decimal,
        to_address: str,
        from_address: str,
        network: str,
        status: str,
    ) -> None:
        """Log successful transaction."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.TRANSACTION_SENT,
                transaction_id=transaction_id,
                wallet_id=wallet_id,
                agent_id=agent_id,
                amount_usdc=amount_usdc,
                to_address=to_address,
                from_address=from_address,
                network=network,
                status=status,
            )
        )

    def transaction_failed(
        self,
        wallet_id: str,
        agent_id: str,
        amount_usdc: Decimal,
        to_address: str,
        error: str,
    ) -> None:
        """Log failed transaction."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.TRANSACTION_FAILED,
                wallet_id=wallet_id,
                agent_id=agent_id,
                amount_usdc=amount_usdc,
                to_address=to_address,
                status="failed",
                error=error,
            )
        )

    def balance_checked(
        self,
        wallet_id: str,
        agent_id: str | None,
        balance_usdc: Decimal,
    ) -> None:
        """Log balance check."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.BALANCE_CHECKED,
                wallet_id=wallet_id,
                agent_id=agent_id,
                amount_usdc=balance_usdc,
                status="success",
            )
        )

    def payment_verified(
        self,
        transaction_hash: str,
        sender_address: str,
        amount_usdc: Decimal,
        recipient_address: str,
        network: str,
    ) -> None:
        """Log successful x402 payment verification."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.PAYMENT_VERIFIED,
                transaction_id=transaction_hash,
                amount_usdc=amount_usdc,
                from_address=sender_address,
                to_address=recipient_address,
                network=network,
                status="verified",
            )
        )

    def payment_rejected(
        self,
        transaction_hash: str,
        reason: str,
        sender_address: str | None = None,
        amount_usdc: Decimal | None = None,
    ) -> None:
        """Log rejected x402 payment verification."""
        self.log_event(
            AuditEvent(
                event_type=AuditEventType.PAYMENT_REJECTED,
                transaction_id=transaction_hash,
                from_address=sender_address,
                amount_usdc=amount_usdc,
                status="rejected",
                error=reason,
            )
        )

    def get_recent_events(self, limit: int = 100) -> list[AuditEvent]:
        """
        Get recent audit events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent audit events, most recent first
        """
        return self._events[-limit:][::-1]

    def clear_events(self) -> None:
        """Clear in-memory event cache (for testing)."""
        self._events.clear()
