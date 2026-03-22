"""x402 protocol implementation for HTTP-based payments.

x402 is an open payment protocol that enables instant, automatic stablecoin
payments directly over HTTP. This module provides server-side payment verification
and client-side payment execution.

Spec: https://github.com/coinbase/x402
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import httpx

from agency_os.wallet.audit import AuditLogger

logger = logging.getLogger(__name__)


@dataclass
class X402PaymentRequest:
    """x402 payment requirement parsed from HTTP headers."""

    amount_usdc: Decimal
    recipient_address: str
    network: str = "base"
    memo: str | None = None
    payment_id: str | None = None


@dataclass
class X402PaymentProof:
    """x402 payment proof submitted by client."""

    transaction_hash: str
    sender_address: str
    amount_usdc: Decimal
    network: str
    payment_id: str | None = None


class X402Protocol:
    """
    x402 protocol handler for machine-to-machine payments.

    Enables API endpoints to require payment and automatically verify
    stablecoin transactions on Base blockchain.
    """

    # x402 HTTP headers
    HEADER_PAYMENT_REQUIRED = "X-Payment-Required"
    HEADER_PAYMENT_AMOUNT = "X-Payment-Amount"
    HEADER_PAYMENT_ADDRESS = "X-Payment-Address"
    HEADER_PAYMENT_NETWORK = "X-Payment-Network"
    HEADER_PAYMENT_MEMO = "X-Payment-Memo"
    HEADER_PAYMENT_ID = "X-Payment-Id"
    HEADER_PAYMENT_PROOF = "X-Payment-Proof"

    def __init__(
        self,
        facilitator_url: str = "https://x402.coinbase.com",
        cache_ttl_seconds: int = 3600,
        audit_logger: AuditLogger | None = None,
    ):
        """
        Initialize x402 protocol handler.

        Args:
            facilitator_url: URL of x402 facilitator service for payment verification
            cache_ttl_seconds: How long to cache verified payment proofs (default: 1 hour)
            audit_logger: Optional audit logger for payment verification events
        """
        self.facilitator_url = facilitator_url
        self._client = httpx.AsyncClient(timeout=30.0)
        self._audit = audit_logger or AuditLogger()

        # Cache verified payment proofs to prevent replay attacks
        # Maps transaction_hash -> (verification_timestamp, verified_amount, verified_recipient)
        self._verified_payments: dict[str, tuple[datetime, Decimal, str]] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    def create_payment_headers(
        self,
        amount_usdc: Decimal,
        recipient_address: str,
        network: str = "base",
        memo: str | None = None,
        payment_id: str | None = None,
    ) -> dict[str, str]:
        """
        Create x402 payment-required headers for HTTP response.

        Args:
            amount_usdc: Payment amount in USDC
            recipient_address: Recipient blockchain address
            network: Blockchain network (default: base)
            memo: Optional payment memo
            payment_id: Optional unique payment ID for tracking

        Returns:
            Dictionary of HTTP headers to include in 402 Payment Required response
        """
        headers = {
            self.HEADER_PAYMENT_REQUIRED: "true",
            self.HEADER_PAYMENT_AMOUNT: str(amount_usdc),
            self.HEADER_PAYMENT_ADDRESS: recipient_address,
            self.HEADER_PAYMENT_NETWORK: network,
        }

        if memo:
            headers[self.HEADER_PAYMENT_MEMO] = memo

        if payment_id:
            headers[self.HEADER_PAYMENT_ID] = payment_id

        return headers

    def parse_payment_request(self, headers: dict[str, str]) -> X402PaymentRequest:
        """
        Parse x402 payment request from HTTP headers.

        Args:
            headers: HTTP response headers from 402 response

        Returns:
            Parsed payment request

        Raises:
            ValueError: If required headers are missing or invalid
        """
        if not headers.get(self.HEADER_PAYMENT_REQUIRED):
            raise ValueError("Not an x402 payment request (missing X-Payment-Required)")

        amount_str = headers.get(self.HEADER_PAYMENT_AMOUNT)
        if not amount_str:
            raise ValueError("Missing required header: X-Payment-Amount")

        recipient = headers.get(self.HEADER_PAYMENT_ADDRESS)
        if not recipient:
            raise ValueError("Missing required header: X-Payment-Address")

        try:
            amount = Decimal(amount_str)
        except Exception as e:
            raise ValueError(f"Invalid payment amount '{amount_str}': {e}") from e

        return X402PaymentRequest(
            amount_usdc=amount,
            recipient_address=recipient,
            network=headers.get(self.HEADER_PAYMENT_NETWORK, "base"),
            memo=headers.get(self.HEADER_PAYMENT_MEMO),
            payment_id=headers.get(self.HEADER_PAYMENT_ID),
        )

    def parse_payment_proof(self, headers: dict[str, str]) -> X402PaymentProof | None:
        """
        Parse x402 payment proof from HTTP request headers.

        Args:
            headers: HTTP request headers containing payment proof

        Returns:
            Parsed payment proof if present, None otherwise

        Raises:
            ValueError: If proof header is present but malformed
        """
        proof_header = headers.get(self.HEADER_PAYMENT_PROOF)
        if not proof_header:
            return None

        # Parse proof format: "tx_hash:sender_address:amount:network[:payment_id]"
        parts = proof_header.split(":")
        if len(parts) < 4:
            raise ValueError(
                f"Invalid payment proof format (expected tx:sender:amount:network): {proof_header}"
            )

        tx_hash, sender, amount_str, network = parts[:4]
        payment_id = parts[4] if len(parts) > 4 else None

        try:
            amount = Decimal(amount_str)
        except Exception as e:
            raise ValueError(f"Invalid amount in payment proof: {amount_str}") from e

        return X402PaymentProof(
            transaction_hash=tx_hash,
            sender_address=sender,
            amount_usdc=amount,
            network=network,
            payment_id=payment_id,
        )

    def _is_payment_cached(
        self,
        transaction_hash: str,
        expected_amount: Decimal,
        expected_recipient: str,
    ) -> bool:
        """
        Check if payment proof is already verified and cached.

        Args:
            transaction_hash: Transaction hash to check
            expected_amount: Expected payment amount
            expected_recipient: Expected recipient address

        Returns:
            True if payment is cached with matching parameters, False otherwise
        """
        if transaction_hash not in self._verified_payments:
            return False

        timestamp, cached_amount, cached_recipient = self._verified_payments[
            transaction_hash
        ]

        # Check if cache is still valid
        if datetime.now(UTC) - timestamp > self._cache_ttl:
            # Cache expired, remove it
            del self._verified_payments[transaction_hash]
            return False

        # Check if cached parameters match expected parameters
        # This prevents replaying a verified payment for different amount/recipient
        if cached_amount != expected_amount or cached_recipient != expected_recipient:
            # Audit log replay attack attempt
            self._audit.payment_rejected(
                transaction_hash=transaction_hash,
                reason=(
                    f"Replay attack: tx was verified for {cached_amount} USDC "
                    f"to {cached_recipient}, now being reused for {expected_amount} USDC "
                    f"to {expected_recipient}"
                ),
                amount_usdc=expected_amount,
            )

            logger.warning(
                f"Replay attack detected: tx {transaction_hash} was verified for "
                f"{cached_amount} USDC to {cached_recipient}, but now being used for "
                f"{expected_amount} USDC to {expected_recipient}"
            )
            return False

        # Valid cached payment
        logger.info(
            f"Payment {transaction_hash} verified from cache (no replay attack)"
        )
        return True

    async def verify_payment(
        self,
        proof: X402PaymentProof,
        expected_amount: Decimal,
        expected_recipient: str,
    ) -> bool:
        """
        Verify a payment proof against expected parameters.

        Uses the x402 facilitator service to verify the transaction on-chain.
        Caches verified payments to prevent replay attacks.

        Args:
            proof: Payment proof from client
            expected_amount: Expected payment amount in USDC
            expected_recipient: Expected recipient address

        Returns:
            True if payment is valid, False otherwise
        """
        # Check cache first (prevents replay attacks)
        if self._is_payment_cached(
            proof.transaction_hash, expected_amount, expected_recipient
        ):
            return True

        try:
            # Call facilitator service to verify transaction
            response = await self._client.post(
                f"{self.facilitator_url}/verify",
                json={
                    "transaction_hash": proof.transaction_hash,
                    "network": proof.network,
                    "expected_amount": str(expected_amount),
                    "expected_recipient": expected_recipient,
                    "sender_address": proof.sender_address,
                },
            )

            if response.status_code != 200:
                logger.warning(
                    f"Payment verification failed: {response.status_code} {response.text}"
                )
                return False

            result = response.json()
            verified = cast(bool, result.get("verified", False))

            if verified:
                # Cache the verified payment to prevent replay
                self._verified_payments[proof.transaction_hash] = (
                    datetime.now(UTC),
                    expected_amount,
                    expected_recipient,
                )

                # Audit log successful verification
                self._audit.payment_verified(
                    transaction_hash=proof.transaction_hash,
                    sender_address=proof.sender_address,
                    amount_usdc=proof.amount_usdc,
                    recipient_address=expected_recipient,
                    network=proof.network,
                )

                logger.info(
                    f"Payment verified: {proof.transaction_hash} "
                    f"({proof.amount_usdc} USDC from {proof.sender_address})"
                )
            else:
                # Audit log rejected verification
                reason = result.get("reason", "unknown")
                self._audit.payment_rejected(
                    transaction_hash=proof.transaction_hash,
                    reason=reason,
                    sender_address=proof.sender_address,
                    amount_usdc=proof.amount_usdc,
                )

                logger.warning(f"Payment verification rejected: {reason}")

            return verified

        except Exception as e:
            logger.error(f"Payment verification error: {e}")
            return False

    def create_proof_header(
        self,
        transaction_hash: str,
        sender_address: str,
        amount_usdc: Decimal,
        network: str = "base",
        payment_id: str | None = None,
    ) -> str:
        """
        Create X-Payment-Proof header value for client to include in retry request.

        Args:
            transaction_hash: Blockchain transaction hash
            sender_address: Sender's blockchain address
            amount_usdc: Payment amount in USDC
            network: Blockchain network
            payment_id: Optional payment ID for tracking

        Returns:
            Proof header value
        """
        parts = [transaction_hash, sender_address, str(amount_usdc), network]
        if payment_id:
            parts.append(payment_id)
        return ":".join(parts)


class X402Middleware:
    """
    Middleware for adding x402 payment verification to API endpoints.

    Usage:
        middleware = X402Middleware(protocol)
        if not await middleware.verify_or_require(request, amount=10.0, recipient="0x..."):
            # Return 402 Payment Required with x402 headers
            pass
    """

    def __init__(self, protocol: X402Protocol):
        """
        Initialize middleware.

        Args:
            protocol: X402Protocol instance
        """
        self.protocol = protocol

    async def verify_or_require(
        self,
        headers: dict[str, str],
        amount_usdc: Decimal,
        recipient_address: str,
        payment_id: str | None = None,
    ) -> tuple[bool, dict[str, str] | None]:
        """
        Check if request includes valid payment proof, or return payment requirement headers.

        Args:
            headers: Request headers
            amount_usdc: Required payment amount
            recipient_address: Payment recipient address
            payment_id: Optional payment ID

        Returns:
            Tuple of (is_paid, payment_headers)
            - If paid: (True, None)
            - If not paid: (False, dict of x402 headers to return in 402 response)
        """
        # Check for payment proof
        proof = self.protocol.parse_payment_proof(headers)

        if proof:
            # Verify payment
            verified = await self.protocol.verify_payment(
                proof, amount_usdc, recipient_address
            )
            if verified:
                return (True, None)

        # Payment not provided or invalid - return requirement headers
        payment_headers = self.protocol.create_payment_headers(
            amount_usdc=amount_usdc,
            recipient_address=recipient_address,
            network="base",
            payment_id=payment_id,
        )

        return (False, payment_headers)
