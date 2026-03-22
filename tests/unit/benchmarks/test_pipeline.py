"""Tests for the 5-agent payment pipeline."""

import pytest

from agency_os.benchmarks.models import Failure, PaymentRail, Policy, Severity
from agency_os.benchmarks.pipeline import (
    AuditorAgent,
    ExecutionAgent,
    PaymentPipeline,
    PipelineContext,
    PlannerAgent,
    StageVerdict,
    TreasuryAgent,
    VerifierAgent,
)


class TestPipelineStages:
    """Unit tests for individual pipeline stages."""

    def test_planner_always_approves(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(max_spend=500.0),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        planner = PlannerAgent()
        verdict = planner.evaluate(ctx)
        assert verdict == StageVerdict.APPROVE
        assert len(ctx.audit_trail) == 1
        assert ctx.audit_trail[0].stage == "planner"

    def test_verifier_approves_compliant_request(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
                no_subscriptions=True,
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        verifier = VerifierAgent()
        verdict = verifier.evaluate(ctx)
        assert verdict == StageVerdict.APPROVE
        assert len(ctx.failures) == 0

    def test_verifier_rejects_unapproved_vendor(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
            ),
            proposed_vendor_id="shady-cloud",
            proposed_amount=200.0,
        )
        verifier = VerifierAgent()
        verdict = verifier.evaluate(ctx)
        assert verdict == StageVerdict.REJECT
        assert len(ctx.failures) == 1
        assert ctx.failures[0].category == "policy_violation"

    def test_verifier_rejects_subscription(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["vendor"],
                no_subscriptions=True,
            ),
            proposed_vendor_id="vendor",
            proposed_amount=200.0,
            is_subscription=True,
        )
        verifier = VerifierAgent()
        verdict = verifier.evaluate(ctx)
        assert verdict == StageVerdict.REJECT
        assert any(
            f.description == "Subscription commitment attempted" for f in ctx.failures
        )

    def test_verifier_escalates_above_threshold(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
                human_approval_threshold=100.0,
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        verifier = VerifierAgent()
        verdict = verifier.evaluate(ctx)
        assert verdict == StageVerdict.ESCALATE

    def test_treasury_approves_within_budget(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(max_spend=500.0),
            proposed_amount=200.0,
        )
        treasury = TreasuryAgent(current_spend=100.0)
        verdict = treasury.evaluate(ctx)
        assert verdict == StageVerdict.APPROVE

    def test_treasury_rejects_over_budget(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(max_spend=500.0),
            proposed_amount=200.0,
        )
        treasury = TreasuryAgent(current_spend=400.0)
        verdict = treasury.evaluate(ctx)
        assert verdict == StageVerdict.REJECT
        assert len(ctx.failures) == 1
        assert ctx.failures[0].severity == Severity.HARD

    def test_execution_creates_transaction(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(max_spend=500.0),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
            proposed_rail=PaymentRail.CARD,
        )
        executor = ExecutionAgent()
        verdict = executor.evaluate(ctx)
        assert verdict == StageVerdict.APPROVE
        assert ctx.transaction is not None
        assert ctx.transaction.amount == 200.0
        assert ctx.transaction.vendor_id == "aws"

    def test_auditor_records_trace(self):
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(max_spend=500.0),
        )
        ctx.verdicts = {
            "planner": StageVerdict.APPROVE,
            "verifier": StageVerdict.APPROVE,
        }
        auditor = AuditorAgent()
        verdict = auditor.evaluate(ctx)
        assert verdict == StageVerdict.APPROVE
        assert len(ctx.audit_trail) == 1
        assert "audit_complete" in ctx.audit_trail[0].outcome


class TestFullPipeline:
    """Integration tests for the complete pipeline."""

    def test_happy_path(self):
        pipeline = PaymentPipeline()
        ctx = PipelineContext(
            task_description="buy cloud compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        result = pipeline.run(ctx)
        assert not result.rejected
        assert not result.escalated
        assert result.transaction is not None
        assert result.transaction.amount == 200.0
        assert len(result.audit_trail) == 5  # all 5 stages

    def test_rejection_at_verifier(self):
        pipeline = PaymentPipeline()
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
            ),
            proposed_vendor_id="evil-corp",
            proposed_amount=200.0,
        )
        result = pipeline.run(ctx)
        assert result.rejected
        assert result.rejection_stage == "verifier"
        assert result.transaction is None
        # Planner + Verifier + Auditor = 3
        assert len(result.audit_trail) == 3

    def test_rejection_at_treasury(self):
        pipeline = PaymentPipeline(
            treasury=TreasuryAgent(current_spend=450.0),
        )
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=500.0,
                approved_vendors=["aws"],
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        result = pipeline.run(ctx)
        assert result.rejected
        assert result.rejection_stage == "treasury"
        assert result.transaction is None

    def test_escalation_skips_execution(self):
        pipeline = PaymentPipeline()
        ctx = PipelineContext(
            task_description="buy expensive compute",
            policy=Policy(
                max_spend=5000.0,
                approved_vendors=["aws"],
                human_approval_threshold=100.0,
            ),
            proposed_vendor_id="aws",
            proposed_amount=500.0,
        )
        result = pipeline.run(ctx)
        assert result.escalated
        assert result.transaction is None

    def test_treasury_tracks_cumulative_spend(self):
        pipeline = PaymentPipeline()
        policy = Policy(max_spend=500.0, approved_vendors=["aws"])

        # First purchase: $200
        ctx1 = PipelineContext(
            task_description="buy 1",
            policy=policy,
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        pipeline.run(ctx1)
        assert pipeline.treasury.current_spend == 200.0

        # Second purchase: $200 (total $400, still OK)
        ctx2 = PipelineContext(
            task_description="buy 2",
            policy=policy,
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        pipeline.run(ctx2)
        assert pipeline.treasury.current_spend == 400.0

        # Third purchase: $200 (total $600, should be rejected)
        ctx3 = PipelineContext(
            task_description="buy 3",
            policy=policy,
            proposed_vendor_id="aws",
            proposed_amount=200.0,
        )
        result = pipeline.run(ctx3)
        assert result.rejected
        assert result.rejection_stage == "treasury"

    def test_verifier_rejects_unauthorized_rail(self):
        """H5: pipeline must enforce allowed_rails policy."""
        pipeline = PaymentPipeline()
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=5000.0,
                approved_vendors=["aws"],
                allowed_rails=[PaymentRail.ACH],
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
            proposed_rail=PaymentRail.CARD,
        )
        result = pipeline.run(ctx)
        assert result.rejected
        assert result.rejection_stage == "verifier"
        assert any(
            f.category == "policy_violation" and "rail" in f.description.lower()
            for f in result.failures
        )

    def test_verifier_approves_allowed_rail(self):
        pipeline = PaymentPipeline()
        ctx = PipelineContext(
            task_description="buy compute",
            policy=Policy(
                max_spend=5000.0,
                approved_vendors=["aws"],
                allowed_rails=[PaymentRail.CARD, PaymentRail.ACH],
            ),
            proposed_vendor_id="aws",
            proposed_amount=200.0,
            proposed_rail=PaymentRail.CARD,
        )
        result = pipeline.run(ctx)
        assert not result.rejected
        assert result.transaction is not None


class TestMetricsClamping:
    """Tests for metric edge cases found in security review."""

    def test_policy_compliance_rate_clamped_to_zero(self):
        """C3: multiple failures per tx must not produce negative rate."""
        from agency_os.benchmarks.metrics import ProtocolMetrics

        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 1
        metrics.total_transactions = 1
        # 5 medium failures for 1 transaction
        for _ in range(5):
            metrics.record_failure(Failure(severity=Severity.MEDIUM, category="test"))
        metrics.finalize()
        assert metrics.policy_compliance_rate == 0.0  # clamped, not -4.0

    def test_financial_loss_rate_measures_dollars(self):
        """C4: financial_loss_rate = dollar loss / total spend."""
        from agency_os.benchmarks.metrics import ProtocolMetrics

        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 2
        metrics.total_spend = 1000.0
        metrics.record_failure(
            Failure(severity=Severity.HARD, category="test", financial_loss=100.0)
        )
        metrics.record_failure(
            Failure(severity=Severity.SOFT, category="test", financial_loss=0.0)
        )
        metrics.finalize()
        assert metrics.financial_loss_rate == pytest.approx(0.1)  # $100 / $1000

    def test_zero_spend_efficiency_is_zero(self):
        """H6: refusing all transactions should not score perfect efficiency."""
        from agency_os.benchmarks.metrics import ProtocolMetrics

        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 5
        metrics.total_spend = 0.0
        metrics.optimal_spend = 500.0
        metrics.finalize()
        assert metrics.cost_efficiency_vs_oracle == 0.0

    def test_governance_safety_without_robustness(self):
        """M3: protocols that don't test injection should not be penalized."""
        from agency_os.benchmarks.metrics import ProtocolMetrics

        metrics = ProtocolMetrics(protocol_name="test")
        metrics.policy_compliance_rate = 1.0
        metrics.audit_trace_completeness = 1.0
        metrics.adversarial_robustness_score = 0.0  # not measured
        # Should use 50/50 compliance+audit, not 40/0/30
        assert metrics.governance_safety == pytest.approx(1.0)
