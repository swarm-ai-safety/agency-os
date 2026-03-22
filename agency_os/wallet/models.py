"""Data models for wallet operations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_serializer


class WalletStatus(str, Enum):
    """Wallet status."""

    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"


class TransactionStatus(str, Enum):
    """Transaction status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class TransactionType(str, Enum):
    """Transaction type."""

    SEND = "send"
    RECEIVE = "receive"
    TRADE = "trade"
    EARN = "earn"


class Wallet(BaseModel):
    """Agentic wallet representation."""

    id: str = Field(description="Wallet ID")
    tenant_id: str = Field(description="Tenant ID that owns this wallet")
    agent_id: str = Field(description="Agent ID that owns this wallet")
    address: str = Field(description="Blockchain address")
    network: str = Field(description="Network (e.g., base-mainnet, base-sepolia)")
    status: WalletStatus = Field(default=WalletStatus.ACTIVE)
    balance_usdc: Decimal = Field(default=Decimal("0"), description="USDC balance")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_serializer("balance_usdc", when_used="json")
    def serialize_balance_usdc(self, value: Decimal) -> str:
        """Serialize Decimal values as strings in JSON mode."""
        return str(value)


class WalletTransaction(BaseModel):
    """Wallet transaction record."""

    id: str = Field(description="Transaction ID")
    wallet_id: str = Field(description="Source wallet ID")
    type: TransactionType
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    amount_usdc: Decimal = Field(description="Transaction amount in USDC")
    to_address: str | None = Field(default=None, description="Recipient address")
    from_address: str | None = Field(default=None, description="Sender address")
    tx_hash: str | None = Field(default=None, description="Blockchain transaction hash")
    error: str | None = Field(default=None, description="Error message if failed")
    metadata: dict | None = Field(default=None, description="Additional metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confirmed_at: datetime | None = None

    @field_serializer("amount_usdc", when_used="json")
    def serialize_amount_usdc(self, value: Decimal) -> str:
        """Serialize Decimal values as strings in JSON mode."""
        return str(value)


class WalletCreationRequest(BaseModel):
    """Request to create a new wallet."""

    agent_id: str = Field(description="Agent ID for wallet owner")
    network: str = Field(
        default="base-sepolia", description="Network to create wallet on"
    )


class TransactionRequest(BaseModel):
    """Request to execute a transaction."""

    wallet_id: str = Field(description="Source wallet ID")
    to_address: str = Field(description="Recipient blockchain address")
    amount_usdc: Decimal = Field(description="Amount in USDC to send")
    metadata: dict | None = Field(
        default=None, description="Optional transaction metadata"
    )
