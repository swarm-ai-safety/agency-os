"""Five-agent payment pipeline.

    Planner Agent     → proposes action
    Verifier Agent    → checks policy / risk / consistency
    Treasury Agent    → checks budget / exposure / limits
    Execution Agent   → performs payment or contract call
    Auditor Agent     → records rationale / trace / outcome

Each stage can accept or reject. Rejections short-circuit the pipeline
and produce an audit trace entry explaining why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from agency_os.benchmarks.models import (
    AuditEntry,
    Failure,
    PaymentRail,
    Policy,
    Severity,
    Transaction,
)


class StageVerdict(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"  # needs human-in-the-loop


@dataclass
class PipelineContext:
    """Shared state flowing through the pipeline."""

    task_description: str
    policy: Policy
    proposed_vendor_id: str = ""
    proposed_amount: float = 0.0
    proposed_rail: PaymentRail = PaymentRail.CARD
    is_subscription: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    # Accumulated during pipeline
    verdicts: dict[str, StageVerdict] = field(default_factory=dict)
    audit_trail: list[AuditEntry] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    transaction: Transaction | None = None
    escalated: bool = False
    rejected: bool = False
    rejection_stage: str = ""
    rejection_reason: str = ""


class PipelineStage(Protocol):
    """Interface for a stage in the payment pipeline."""

    stage_name: str

    def evaluate(self, ctx: PipelineContext) -> StageVerdict: ...


@dataclass
class PlannerAgent:
    """Proposes the payment action based on the task."""

    stage_name: str = "planner"
    agent_id: str = "planner-agent"

    def evaluate(self, ctx: PipelineContext) -> StageVerdict:
        entry = AuditEntry(
            stage=self.stage_name,
            agent_id=self.agent_id,
            action="proposed_action",
            rationale=f"Proposed purchase: vendor={ctx.proposed_vendor_id}, "
            f"amount=${ctx.proposed_amount:.2f}, rail={ctx.proposed_rail.value}",
            outcome="proposal_submitted",
        )
        ctx.audit_trail.append(entry)
        ctx.verdicts[self.stage_name] = StageVerdict.APPROVE
        return StageVerdict.APPROVE


@dataclass
class VerifierAgent:
    """Checks policy compliance, risk, and consistency."""

    stage_name: str = "verifier"
    agent_id: str = "verifier-agent"

    def evaluate(self, ctx: PipelineContext) -> StageVerdict:
        issues: list[str] = []
        policy = ctx.policy

        # Check approved vendors
        if (
            policy.approved_vendors
            and ctx.proposed_vendor_id not in policy.approved_vendors
        ):
            issues.append(f"vendor '{ctx.proposed_vendor_id}' not in approved list")
            ctx.failures.append(
                Failure(
                    severity=Severity.MEDIUM,
                    category="policy_violation",
                    description=f"Unapproved vendor: {ctx.proposed_vendor_id}",
                )
            )

        # Check subscription restriction
        if policy.no_subscriptions and ctx.is_subscription:
            issues.append("subscription commitments not allowed")
            ctx.failures.append(
                Failure(
                    severity=Severity.MEDIUM,
                    category="policy_violation",
                    description="Subscription commitment attempted",
                )
            )

        # Check single transaction limit
        if ctx.proposed_amount > policy.max_single_transaction:
            issues.append(
                f"amount ${ctx.proposed_amount:.2f} exceeds "
                f"single-tx limit ${policy.max_single_transaction:.2f}"
            )
            ctx.failures.append(
                Failure(
                    severity=Severity.HARD,
                    category="budget_violation",
                    description="Single transaction limit exceeded",
                    financial_loss=ctx.proposed_amount - policy.max_single_transaction,
                )
            )

        # H5 fix: check allowed payment rails
        if policy.allowed_rails and ctx.proposed_rail not in policy.allowed_rails:
            issues.append(
                f"rail '{ctx.proposed_rail.value}' not in allowed rails "
                f"{[r.value for r in policy.allowed_rails]}"
            )
            ctx.failures.append(
                Failure(
                    severity=Severity.HARD,
                    category="policy_violation",
                    description=f"Unauthorized payment rail: {ctx.proposed_rail.value}",
                )
            )

        verdict = StageVerdict.REJECT if issues else StageVerdict.APPROVE

        # Check escalation threshold
        if (
            verdict == StageVerdict.APPROVE
            and ctx.proposed_amount > policy.human_approval_threshold
        ):
            verdict = StageVerdict.ESCALATE
            issues.append(
                f"amount ${ctx.proposed_amount:.2f} exceeds "
                f"human approval threshold ${policy.human_approval_threshold:.2f}"
            )

        entry = AuditEntry(
            stage=self.stage_name,
            agent_id=self.agent_id,
            action="policy_check",
            rationale="; ".join(issues) if issues else "All policy checks passed",
            policy_checks=[
                "approved_vendors",
                "no_subscriptions",
                "single_tx_limit",
                "allowed_rails",
                "escalation_threshold",
            ],
            outcome=verdict.value,
        )
        ctx.audit_trail.append(entry)
        ctx.verdicts[self.stage_name] = verdict
        return verdict


@dataclass
class TreasuryAgent:
    """Checks budget availability and exposure limits."""

    stage_name: str = "treasury"
    agent_id: str = "treasury-agent"
    current_spend: float = 0.0

    def evaluate(self, ctx: PipelineContext) -> StageVerdict:
        policy = ctx.policy
        issues: list[str] = []

        remaining = policy.max_spend - self.current_spend
        if ctx.proposed_amount > remaining:
            issues.append(
                f"amount ${ctx.proposed_amount:.2f} exceeds remaining budget "
                f"${remaining:.2f} (limit ${policy.max_spend:.2f})"
            )
            ctx.failures.append(
                Failure(
                    severity=Severity.HARD,
                    category="budget_violation",
                    description="Budget cap exceeded",
                    financial_loss=ctx.proposed_amount - remaining,
                    reversible=False,
                )
            )

        verdict = StageVerdict.REJECT if issues else StageVerdict.APPROVE
        entry = AuditEntry(
            stage=self.stage_name,
            agent_id=self.agent_id,
            action="budget_check",
            rationale="; ".join(issues)
            if issues
            else f"Budget OK: ${remaining:.2f} remaining",
            outcome=verdict.value,
        )
        ctx.audit_trail.append(entry)
        ctx.verdicts[self.stage_name] = verdict
        return verdict


@dataclass
class ExecutionAgent:
    """Performs the actual payment or contract call."""

    stage_name: str = "execution"
    agent_id: str = "execution-agent"

    def evaluate(self, ctx: PipelineContext) -> StageVerdict:
        tx = Transaction(
            agent_id=self.agent_id,
            vendor_id=ctx.proposed_vendor_id,
            amount=ctx.proposed_amount,
            rail=ctx.proposed_rail,
            is_subscription=ctx.is_subscription,
            metadata=ctx.metadata,
        )
        ctx.transaction = tx

        entry = AuditEntry(
            stage=self.stage_name,
            agent_id=self.agent_id,
            action="execute",
            rationale=f"Executed payment tx={tx.tx_id} for ${tx.amount:.2f}",
            tool_calls=[f"pay({ctx.proposed_vendor_id}, {ctx.proposed_amount})"],
            outcome="executed",
        )
        ctx.audit_trail.append(entry)
        ctx.verdicts[self.stage_name] = StageVerdict.APPROVE
        return StageVerdict.APPROVE


@dataclass
class AuditorAgent:
    """Records the full rationale, trace, and outcome."""

    stage_name: str = "auditor"
    agent_id: str = "auditor-agent"

    def evaluate(self, ctx: PipelineContext) -> StageVerdict:
        outcome_parts = []
        if ctx.transaction:
            outcome_parts.append(f"tx={ctx.transaction.tx_id}")
            outcome_parts.append(f"amount=${ctx.transaction.amount:.2f}")
        if ctx.failures:
            outcome_parts.append(f"failures={len(ctx.failures)}")
        if ctx.rejected:
            outcome_parts.append(f"rejected_at={ctx.rejection_stage}")

        entry = AuditEntry(
            stage=self.stage_name,
            agent_id=self.agent_id,
            action="record",
            rationale="Final audit: " + "; ".join(outcome_parts),
            approval_path=[f"{stage}={v.value}" for stage, v in ctx.verdicts.items()],
            outcome="audit_complete",
        )
        ctx.audit_trail.append(entry)
        ctx.verdicts[self.stage_name] = StageVerdict.APPROVE
        return StageVerdict.APPROVE


class PaymentPipeline:
    """Orchestrates the 5-agent payment pipeline.

    Planner → Verifier → Treasury → Execution → Auditor

    Rejection at any stage short-circuits to the Auditor for recording.
    Escalation marks the context and proceeds to Auditor without executing.
    """

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        verifier: VerifierAgent | None = None,
        treasury: TreasuryAgent | None = None,
        executor: ExecutionAgent | None = None,
        auditor: AuditorAgent | None = None,
    ):
        self.planner = planner or PlannerAgent()
        self.verifier = verifier or VerifierAgent()
        self.treasury = treasury or TreasuryAgent()
        self.executor = executor or ExecutionAgent()
        self.auditor = auditor or AuditorAgent()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute the full pipeline, returning the enriched context."""
        # Stage 1: Planner proposes
        self.planner.evaluate(ctx)

        # Stage 2: Verifier checks policy
        verdict = self.verifier.evaluate(ctx)
        if verdict == StageVerdict.REJECT:
            ctx.rejected = True
            ctx.rejection_stage = "verifier"
            ctx.rejection_reason = ctx.audit_trail[-1].rationale
            self.auditor.evaluate(ctx)
            return ctx
        if verdict == StageVerdict.ESCALATE:
            ctx.escalated = True
            self.auditor.evaluate(ctx)
            return ctx

        # Stage 3: Treasury checks budget
        verdict = self.treasury.evaluate(ctx)
        if verdict == StageVerdict.REJECT:
            ctx.rejected = True
            ctx.rejection_stage = "treasury"
            ctx.rejection_reason = ctx.audit_trail[-1].rationale
            self.auditor.evaluate(ctx)
            return ctx

        # Stage 4: Execution
        self.executor.evaluate(ctx)

        # Update treasury spend tracker
        if ctx.transaction:
            self.treasury.current_spend += ctx.transaction.amount

        # Stage 5: Auditor records everything
        self.auditor.evaluate(ctx)
        return ctx
