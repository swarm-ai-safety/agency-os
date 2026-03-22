"""Core data models for the payment benchmark suite."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Failure severity hierarchy.

    soft   – inefficiency, no real harm
    medium – policy violation with no financial loss
    hard   – actual financial loss
    critical – self-amplifying or hidden loss
    """

    SOFT = "soft"
    MEDIUM = "medium"
    HARD = "hard"
    CRITICAL = "critical"


class DifficultyTier(str, Enum):
    """Graded adversarial pressure tiers."""

    EASY = "easy"
    REALISTIC = "realistic"
    ADVERSARIAL = "adversarial"
    RED_TEAM = "red_team"


class BaselineType(str, Enum):
    """Mirrored baseline configurations."""

    SINGLE_AGENT = "single_agent"
    MULTI_AGENT_VERIFIER = "multi_agent_verifier"
    MULTI_AGENT_GOVERNANCE = "multi_agent_governance"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    SCRIPTED_POLICY_ENGINE = "scripted_policy_engine"


class PaymentRail(str, Enum):
    """Available payment rails."""

    CARD = "card"
    ACH = "ach"
    STABLECOIN = "stablecoin"
    ONCHAIN_ESCROW = "onchain_escrow"


@dataclass
class Vendor:
    """A merchant option in the benchmark environment."""

    vendor_id: str
    name: str
    price: float
    quality: float  # 0.0–1.0
    approved: bool = True
    has_subscription_trap: bool = False
    has_upsell: bool = False
    injection_payload: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Policy:
    """Spending policy constraints for an agent."""

    max_spend: float
    approved_vendors: list[str] = field(default_factory=list)
    no_subscriptions: bool = True
    human_approval_threshold: float = float("inf")
    max_single_transaction: float = float("inf")
    allowed_rails: list[PaymentRail] = field(default_factory=list)


@dataclass
class Transaction:
    """Record of a single payment action."""

    tx_id: str = field(default_factory=lambda: f"tx-{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    vendor_id: str = ""
    amount: float = 0.0
    rail: PaymentRail = PaymentRail.CARD
    is_subscription: bool = False
    timestamp: float = field(default_factory=time.time)
    approved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEntry:
    """Single entry in the full audit trace."""

    timestamp: float = field(default_factory=time.time)
    stage: str = ""  # planner, verifier, treasury, execution, auditor
    agent_id: str = ""
    action: str = ""  # proposed_action, policy_check, budget_check, execute, record
    rationale: str = ""
    tool_calls: list[str] = field(default_factory=list)
    policy_checks: list[str] = field(default_factory=list)
    approval_path: list[str] = field(default_factory=list)
    outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Failure:
    """A recorded failure event with severity classification."""

    failure_id: str = field(default_factory=lambda: f"fail-{uuid.uuid4().hex[:8]}")
    severity: Severity = Severity.SOFT
    category: str = ""  # budget_violation, policy_violation, injection_success, etc.
    description: str = ""
    financial_loss: float = 0.0
    reversible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentAuthority:
    """Delegated authority scope for an agent."""

    agent_id: str
    can_view_balances: bool = False
    can_propose_payments: bool = False
    max_execute_amount: float = 0.0
    requires_approval: bool = True
    allowed_actions: list[str] = field(default_factory=list)


@dataclass
class Milestone:
    """A milestone in an escrow-based payment flow."""

    milestone_id: str
    name: str
    amount: float
    conditions: list[str] = field(default_factory=list)
    met: bool = False
    released: bool = False
    verified_at: float | None = None


@dataclass
class RailOption:
    """A payment rail option with its tradeoffs."""

    rail: PaymentRail
    fee_rate: float  # 0.0–1.0
    settlement_seconds: int
    reversible: bool
    compliance_score: float  # 0.0–1.0 (policy fit)
    metadata: dict[str, Any] = field(default_factory=dict)
