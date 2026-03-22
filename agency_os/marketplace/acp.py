"""Agent Commerce Protocol (ACP) integration layer.

Implements the Virtuals Protocol ACP pattern for agent-to-agent commerce:
- Service registration in the ACP marketplace
- Smart-contract-based escrow for payment settlement
- Evaluator-phase verification of service delivery
- On-chain payment settlement (USDC on Base)

Security:
    - Full SHA-256 for agreement hashes (M1)
    - Fund balance verification before escrow creation (H4)
    - Bounded in-memory stores with eviction (M3)
    - Thread-safe state management (L1)
    - Evaluation score clamped to [0.0, 1.0]
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# M3: Maximum in-memory records
MAX_ESCROWS = 50000
MAX_REGISTRATIONS = 10000


class EscrowState(str, Enum):
    """State machine for ACP escrow lifecycle."""

    CREATED = "created"  # Escrow opened, funds locked
    EXECUTING = "executing"  # Service is running
    EVALUATING = "evaluating"  # Evaluator agent verifying delivery
    SETTLED = "settled"  # Payment released to provider
    DISPUTED = "disputed"  # Evaluator flagged issue
    REFUNDED = "refunded"  # Funds returned to client
    EXPIRED = "expired"  # TTL exceeded without settlement


@dataclass
class EscrowRecord:
    """Tracks a single ACP escrow for a service transaction."""

    escrow_id: str
    client_agent_id: str
    provider_agent_id: str
    service_id: str
    amount_usd: float
    state: EscrowState = EscrowState.CREATED
    created_at: float = field(default_factory=time.time)
    settled_at: float | None = None
    tx_hash: str | None = None
    evaluation_score: float | None = None
    ttl_seconds: float = 600.0

    @property
    def is_expired(self) -> bool:
        if self.state in (EscrowState.SETTLED, EscrowState.REFUNDED):
            return False
        return (time.time() - self.created_at) > self.ttl_seconds


@dataclass
class ACPRegistration:
    """Registration record for a SWARM service in the ACP marketplace."""

    agent_id: str
    service_manifest: dict[str, Any]
    registered_at: float = field(default_factory=time.time)
    active: bool = True
    total_earnings_usd: float = 0.0
    total_jobs_completed: int = 0
    reputation_score: float = 1.0


class ACPClient:
    """Client for the Agent Commerce Protocol marketplace.

    Handles:
    - Registering SWARM services for discovery by autonomous agents
    - Managing escrow lifecycle for service transactions
    - Settlement of payments (on-chain via wallet integration, or internal)
    - Reputation tracking for service providers

    Buyer flow (autonomous agents purchasing SWARM services):
        1. discover() — find services by capability
        2. request_service() — create escrow + submit job
        3. evaluate() — evaluator agent verifies delivery
        4. settle() — release payment to provider

    Provider flow (SWARM worker agents selling services):
        1. register_service() — publish to marketplace
        2. (await job via worker agent)
        3. (return result)
        4. collect_settlement() — receive payment
    """

    def __init__(
        self,
        platform_fee_rate: float = 0.05,
        escrow_ttl_seconds: float = 600.0,
        balance_checker: Any | None = None,
    ) -> None:
        # Validate fee rate
        if not (0.0 <= platform_fee_rate <= 1.0):
            raise ValueError(
                f"platform_fee_rate must be in [0, 1], got {platform_fee_rate}"
            )
        self._registrations: OrderedDict[str, ACPRegistration] = OrderedDict()
        self._escrows: OrderedDict[str, EscrowRecord] = OrderedDict()
        self._platform_fee_rate = platform_fee_rate
        self._escrow_ttl = escrow_ttl_seconds
        self._platform_revenue_usd: float = 0.0
        # H4: Optional balance checker for fund verification
        self._balance_checker = balance_checker
        # L1: Thread safety
        self._lock = threading.Lock()

    # -- Provider operations --

    def register_service(
        self, agent_id: str, service_manifest: dict[str, Any]
    ) -> ACPRegistration:
        """Register a SWARM service in the ACP marketplace."""
        reg = ACPRegistration(
            agent_id=agent_id,
            service_manifest=service_manifest,
        )
        with self._lock:
            # M3: Evict oldest inactive registration if at capacity
            if len(self._registrations) >= MAX_REGISTRATIONS:
                self._evict_inactive_registrations()
            self._registrations[agent_id] = reg
        logger.info(
            "ACP: Registered agent %s with capabilities: %s",
            agent_id,
            service_manifest.get("capabilities", []),
        )
        return reg

    def unregister_service(self, agent_id: str) -> bool:
        """Remove a service from the marketplace."""
        with self._lock:
            reg = self._registrations.get(agent_id)
            if reg:
                reg.active = False
                return True
        return False

    # -- Buyer operations --

    def discover(
        self,
        capability: str | None = None,
        category: str | None = None,
        max_price_usd: float | None = None,
    ) -> list[dict[str, Any]]:
        """Discover available SWARM services in the marketplace."""
        with self._lock:
            registrations = list(self._registrations.values())

        results = []
        for reg in registrations:
            if not reg.active:
                continue
            manifest = reg.service_manifest
            if capability:
                caps = [c.lower() for c in manifest.get("capabilities", [])]
                if not any(capability.lower() in c for c in caps):
                    continue
            if category and manifest.get("category") != category:
                continue
            if max_price_usd is not None:
                price = manifest.get("pricing", {}).get("base", 0)
                if price > max_price_usd:
                    continue
            results.append(
                {
                    **manifest,
                    "provider_agent_id": reg.agent_id,
                    "reputation": reg.reputation_score,
                    "jobs_completed": reg.total_jobs_completed,
                }
            )
        return results

    def create_escrow(
        self,
        client_agent_id: str,
        provider_agent_id: str,
        service_id: str,
        amount_usd: float,
    ) -> EscrowRecord:
        """Create an escrow for a service transaction.

        H4: If a balance_checker is configured, verifies the client has
        sufficient funds before creating the escrow.

        Raises:
            ValueError: If amount is invalid or client has insufficient funds.
        """
        if amount_usd <= 0:
            raise ValueError(f"Escrow amount must be positive, got {amount_usd}")
        if amount_usd > 10000:
            raise ValueError(
                f"Escrow amount exceeds maximum ($10,000), got {amount_usd}"
            )

        # H4: Verify client funds if balance checker is available
        if self._balance_checker is not None:
            balance = self._balance_checker.get_balance(client_agent_id)
            if balance < amount_usd:
                raise ValueError(
                    f"Insufficient funds: client {client_agent_id} has "
                    f"${balance:.2f}, needs ${amount_usd:.2f}"
                )

        escrow = EscrowRecord(
            escrow_id=f"escrow-{uuid.uuid4().hex[:16]}",
            client_agent_id=client_agent_id,
            provider_agent_id=provider_agent_id,
            service_id=service_id,
            amount_usd=amount_usd,
            ttl_seconds=self._escrow_ttl,
        )
        with self._lock:
            # M3: Evict settled/expired escrows if at capacity
            if len(self._escrows) >= MAX_ESCROWS:
                self._evict_terminal_escrows()
            self._escrows[escrow.escrow_id] = escrow
        logger.info(
            "ACP: Escrow %s created: %s -> %s for $%.2f",
            escrow.escrow_id,
            client_agent_id,
            provider_agent_id,
            amount_usd,
        )
        return escrow

    def mark_executing(self, escrow_id: str) -> bool:
        """Mark escrow as executing (service is running)."""
        with self._lock:
            escrow = self._escrows.get(escrow_id)
            if escrow and escrow.state == EscrowState.CREATED:
                escrow.state = EscrowState.EXECUTING
                return True
        return False

    def submit_evaluation(
        self, escrow_id: str, score: float, evaluator_notes: str = ""
    ) -> bool:
        """Submit evaluation of service delivery.

        Args:
            escrow_id: The escrow to evaluate.
            score: Quality score 0.0-1.0 (>0.5 = acceptable). Clamped to range.
            evaluator_notes: Optional notes from the evaluator.

        Returns:
            True if evaluation was recorded.
        """
        # Clamp score to valid range
        score = max(0.0, min(1.0, score))
        with self._lock:
            escrow = self._escrows.get(escrow_id)
            if escrow is None or escrow.state != EscrowState.EXECUTING:
                return False
            escrow.evaluation_score = score
            escrow.state = EscrowState.EVALUATING
        logger.info(
            "ACP: Escrow %s evaluated: score=%.2f",
            escrow_id,
            score,
        )
        return True

    def settle(self, escrow_id: str, tx_hash: str | None = None) -> dict[str, Any]:
        """Settle an escrow — release payment or refund.

        If evaluation score >= 0.5, payment goes to the provider (minus platform fee).
        If score < 0.5, funds are refunded to the client.
        """
        with self._lock:
            escrow = self._escrows.get(escrow_id)
            if escrow is None:
                return {"error": "Escrow not found"}
            if escrow.state not in (EscrowState.EVALUATING, EscrowState.EXECUTING):
                return {"error": f"Cannot settle escrow in state: {escrow.state.value}"}

            score = escrow.evaluation_score or 0.0
            if score >= 0.5:
                platform_fee = escrow.amount_usd * self._platform_fee_rate
                provider_payout = escrow.amount_usd - platform_fee
                escrow.state = EscrowState.SETTLED
                escrow.settled_at = time.time()
                escrow.tx_hash = tx_hash
                self._platform_revenue_usd += platform_fee

                reg = self._registrations.get(escrow.provider_agent_id)
                if reg:
                    reg.total_earnings_usd += provider_payout
                    reg.total_jobs_completed += 1
                    n = reg.total_jobs_completed
                    reg.reputation_score = (reg.reputation_score * (n - 1) + score) / n

                logger.info(
                    "ACP: Escrow %s settled: provider=$%.2f, platform=$%.2f",
                    escrow_id,
                    provider_payout,
                    platform_fee,
                )
                return {
                    "escrow_id": escrow_id,
                    "state": "settled",
                    "provider_payout_usd": provider_payout,
                    "platform_fee_usd": platform_fee,
                    "evaluation_score": score,
                    "tx_hash": tx_hash,
                }
            else:
                escrow.state = EscrowState.REFUNDED
                escrow.settled_at = time.time()
                logger.info(
                    "ACP: Escrow %s refunded: score=%.2f below threshold",
                    escrow_id,
                    score,
                )
                return {
                    "escrow_id": escrow_id,
                    "state": "refunded",
                    "refund_amount_usd": escrow.amount_usd,
                    "evaluation_score": score,
                }

    def expire_stale_escrows(self) -> list[str]:
        """Expire escrows that exceeded their TTL."""
        expired = []
        with self._lock:
            for escrow in self._escrows.values():
                if escrow.is_expired and escrow.state not in (
                    EscrowState.SETTLED,
                    EscrowState.REFUNDED,
                    EscrowState.EXPIRED,
                ):
                    escrow.state = EscrowState.EXPIRED
                    expired.append(escrow.escrow_id)
                    logger.warning("ACP: Escrow %s expired", escrow.escrow_id)
        return expired

    def get_escrow(self, escrow_id: str) -> EscrowRecord | None:
        return self._escrows.get(escrow_id)

    def platform_stats(self) -> dict[str, Any]:
        """Return platform-level marketplace statistics."""
        with self._lock:
            active_providers = sum(1 for r in self._registrations.values() if r.active)
            return {
                "active_providers": active_providers,
                "total_registrations": len(self._registrations),
                "total_escrows": len(self._escrows),
                "settled_escrows": sum(
                    1 for e in self._escrows.values() if e.state == EscrowState.SETTLED
                ),
                "platform_revenue_usd": self._platform_revenue_usd,
                "platform_fee_rate": self._platform_fee_rate,
            }

    def _evict_terminal_escrows(self) -> None:
        """M3: Remove settled/expired/refunded escrows to bound memory."""
        terminal = {EscrowState.SETTLED, EscrowState.REFUNDED, EscrowState.EXPIRED}
        to_remove = [eid for eid, e in self._escrows.items() if e.state in terminal]
        # Remove oldest first (OrderedDict preserves insertion order)
        for eid in to_remove[: len(to_remove) // 2 + 1]:
            del self._escrows[eid]

    def _evict_inactive_registrations(self) -> None:
        """M3: Remove inactive registrations to bound memory."""
        to_remove = [aid for aid, r in self._registrations.items() if not r.active]
        for aid in to_remove[: len(to_remove) // 2 + 1]:
            del self._registrations[aid]


def generate_agreement_hash(
    client_id: str, provider_id: str, service_id: str, amount: float
) -> str:
    """Generate a deterministic hash for an ACP service agreement.

    M1: Uses full SHA-256 (256 bits) instead of truncated hash.
    """
    payload = f"{client_id}:{provider_id}:{service_id}:{amount:.6f}"
    return hashlib.sha256(payload.encode()).hexdigest()
