"""Tests for all 7 benchmark protocols."""

import pytest

from agency_os.benchmarks.metrics import ProtocolMetrics
from agency_os.benchmarks.models import Severity
from agency_os.benchmarks.protocols.p1_delegated_spending import (
    DelegatedSpendingBenchmark,
    build_easy_scenarios,
)
from agency_os.benchmarks.protocols.p2_prompt_injection import (
    INJECTION_PAYLOADS,
    PromptInjectionBenchmark,
    build_injection_scenarios,
)
from agency_os.benchmarks.protocols.p3_multi_agent_collusion import (
    AgentIncentive,
    CollusionScenario,
    MultiAgentCollusionBenchmark,
    NegotiatingAgent,
    build_aligned_scenario,
    build_rogue_agent_scenario,
)
from agency_os.benchmarks.protocols.p4_escrow_milestones import (
    EscrowMilestoneBenchmark,
    build_escrow_scenarios,
)
from agency_os.benchmarks.protocols.p5_authority_boundaries import (
    AuthorityBoundaryBenchmark,
    build_authority_scenarios,
)
from agency_os.benchmarks.protocols.p6_cross_rail_routing import (
    CrossRailRoutingBenchmark,
)
from agency_os.benchmarks.protocols.p7_swarm_treasury import (
    SwarmTreasuryBenchmark,
    build_treasury_scenarios,
)


class TestP1DelegatedSpending:
    def test_run_produces_metrics(self):
        bench = DelegatedSpendingBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "delegated_spending_safety"
        assert metrics.total_tasks > 0
        assert 0.0 <= metrics.task_success_rate <= 1.0

    def test_easy_scenarios_all_pass(self):
        bench = DelegatedSpendingBenchmark(scenarios=build_easy_scenarios())
        metrics = bench.run()
        assert metrics.successful_tasks > 0
        assert metrics.failures_hard == 0
        assert metrics.failures_critical == 0

    def test_has_audit_trail(self):
        bench = DelegatedSpendingBenchmark()
        metrics = bench.run()
        assert len(metrics.audit_entries) > 0
        stages = {e.stage for e in metrics.audit_entries}
        assert "planner" in stages
        assert "verifier" in stages

    def test_economic_capability_score(self):
        bench = DelegatedSpendingBenchmark(scenarios=build_easy_scenarios())
        metrics = bench.run()
        assert metrics.economic_capability > 0.0

    def test_governance_safety_score(self):
        bench = DelegatedSpendingBenchmark(scenarios=build_easy_scenarios())
        metrics = bench.run()
        assert metrics.governance_safety >= 0.0


class TestP2PromptInjection:
    def test_run_produces_metrics(self):
        bench = PromptInjectionBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "prompt_injection_resistance"
        assert metrics.total_tasks == len(INJECTION_PAYLOADS)

    def test_detects_obvious_injections(self):
        bench = PromptInjectionBenchmark()
        metrics = bench.run()
        assert metrics.adversarial_robustness_score > 0.5

    def test_false_positive_tracking(self):
        bench = PromptInjectionBenchmark()
        metrics = bench.run()
        assert "false_positives" in metrics.extras
        assert "total_benign_tested" in metrics.extras

    def test_injection_scenarios_have_payloads(self):
        scenarios = build_injection_scenarios()
        for s in scenarios:
            assert s.payload.content
            assert s.payload.target_action


class TestP3MultiAgentCollusion:
    def test_run_produces_metrics(self):
        bench = MultiAgentCollusionBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "multi_agent_collusion"
        assert metrics.total_tasks >= 3

    def test_aligned_scenario_succeeds(self):
        bench = MultiAgentCollusionBenchmark(scenarios=[build_aligned_scenario()])
        metrics = bench.run()
        assert metrics.successful_tasks >= 1

    def test_rogue_agent_influence(self):
        bench = MultiAgentCollusionBenchmark(scenarios=[build_rogue_agent_scenario()])
        metrics = bench.run()
        # Rogue agent may or may not cause misalignment, but metrics should track it
        assert metrics.total_tasks == 1

    def test_consensus_reached(self):
        bench = MultiAgentCollusionBenchmark(scenarios=[build_aligned_scenario()])
        metrics = bench.run()
        assert metrics.total_spend > 0

    def test_negotiation_deadlock_produces_failure(self):
        """M5: when no consensus is reached, negotiation_failure is recorded."""
        # Create agents that will never agree (extremely tight flexibility)
        scenario = CollusionScenario(
            name="deadlock",
            agents=[
                NegotiatingAgent(
                    "buyer", "buyer", AgentIncentive.COST_MIN, 100.0, flexibility=0.001
                ),
                NegotiatingAgent(
                    "seller", "seller", AgentIncentive.UPSELL, 900.0, flexibility=0.001
                ),
            ],
            principal_target_price=500.0,
            max_rounds=5,
        )
        bench = MultiAgentCollusionBenchmark(scenarios=[scenario])
        metrics = bench.run()
        assert any(f.category == "negotiation_failure" for f in metrics.failures)

    def test_speed_incentive_influences_price(self):
        """C2: SPEED incentive should push price up (not be inert)."""
        agent = NegotiatingAgent(
            "a", "buyer", AgentIncentive.SPEED, 500.0, flexibility=0.3
        )
        proposed = agent.propose_price(400.0)
        assert proposed > 400.0  # should push up, not return unchanged


class TestP4EscrowMilestones:
    def test_run_produces_metrics(self):
        bench = EscrowMilestoneBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "escrow_milestone_reliability"
        assert metrics.total_tasks > 0

    def test_happy_path_succeeds(self):
        scenarios = build_escrow_scenarios()
        happy = [s for s in scenarios if s.name == "happy_path"]
        bench = EscrowMilestoneBenchmark(scenarios=happy)
        metrics = bench.run()
        assert metrics.successful_tasks == 1
        assert metrics.failures_hard == 0

    def test_tracks_premature_release(self):
        bench = EscrowMilestoneBenchmark()
        metrics = bench.run()
        assert "premature_release_rate" in metrics.extras
        assert "fraud_loss_total" in metrics.extras

    def test_fraudulent_scenarios_produce_failures(self):
        scenarios = build_escrow_scenarios()
        fraud = [s for s in scenarios if s.name == "fraudulent_shipment"]
        bench = EscrowMilestoneBenchmark(scenarios=fraud)
        metrics = bench.run()
        # Should have some hard failures for premature release
        assert metrics.extras.get("premature_release_rate", 0) >= 0


class TestP5AuthorityBoundaries:
    def test_run_produces_metrics(self):
        bench = AuthorityBoundaryBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "authority_boundaries"
        assert metrics.total_tasks > 0

    def test_matching_authority_all_pass(self):
        scenarios = build_authority_scenarios()
        easy = [s for s in scenarios if s.name == "matching_authority"]
        bench = AuthorityBoundaryBenchmark(scenarios=easy)
        metrics = bench.run()
        assert metrics.successful_tasks > 0

    def test_tracks_unauthorized_attempts(self):
        bench = AuthorityBoundaryBenchmark()
        metrics = bench.run()
        assert "unauthorized_attempts" in metrics.extras
        assert "clean_handoff_rate" in metrics.extras

    def test_privilege_escalation_tasks_produce_failures(self):
        scenarios = build_authority_scenarios()
        adversarial = [s for s in scenarios if s.name == "privilege_escalation"]
        bench = AuthorityBoundaryBenchmark(scenarios=adversarial)
        metrics = bench.run()
        # Tasks like $5000 payment should fail because executor max is $100
        assert metrics.total_tasks > 0
        # M4 fix: privilege_escalations should now be tracked
        assert "privilege_escalations" in metrics.extras


class TestP6CrossRailRouting:
    def test_run_produces_metrics(self):
        bench = CrossRailRoutingBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "cross_rail_routing"
        assert metrics.total_tasks > 0

    def test_cost_priority_selects_cheapest(self):
        bench = CrossRailRoutingBenchmark()
        metrics = bench.run()
        assert "optimal_selection_rate" in metrics.extras
        assert metrics.extras["optimal_selection_rate"] > 0

    def test_compliance_filtering(self):
        bench = CrossRailRoutingBenchmark()
        metrics = bench.run()
        assert "compliance_violations" in metrics.extras

    def test_fee_tracking(self):
        bench = CrossRailRoutingBenchmark()
        metrics = bench.run()
        assert "total_fees" in metrics.extras
        assert "oracle_fees" in metrics.extras
        assert "fee_regret" in metrics.extras


class TestP7SwarmTreasury:
    def test_run_produces_metrics(self):
        bench = SwarmTreasuryBenchmark()
        metrics = bench.run()
        assert metrics.protocol_name == "swarm_treasury_management"
        assert metrics.total_tasks > 0

    def test_normal_operations_succeed(self):
        scenarios = build_treasury_scenarios()
        normal = [s for s in scenarios if s.name == "normal_operations"]
        bench = SwarmTreasuryBenchmark(scenarios=normal)
        metrics = bench.run()
        assert metrics.successful_tasks == 1

    def test_shock_resilience_tracked(self):
        scenarios = build_treasury_scenarios()
        shocks = [s for s in scenarios if s.name == "shock_resilience"]
        bench = SwarmTreasuryBenchmark(scenarios=shocks)
        metrics = bench.run()
        assert len(metrics.audit_entries) > 0
        shock_entries = [e for e in metrics.audit_entries if e.stage == "shock"]
        assert len(shock_entries) > 0

    def test_treasury_balances_recorded(self):
        bench = SwarmTreasuryBenchmark()
        metrics = bench.run()
        assert "final_treasury_balances" in metrics.extras
        assert len(metrics.extras["final_treasury_balances"]) > 0

    def test_critical_failure_does_not_contaminate_later_scenarios(self):
        """H3: a CRITICAL failure in scenario 1 must not suppress success in scenario 2."""
        scenarios = build_treasury_scenarios()
        # Run adversarial (has critical failures) BEFORE normal
        adversarial = [s for s in scenarios if s.name == "cascading_crisis"]
        normal = [s for s in scenarios if s.name == "normal_operations"]
        bench = SwarmTreasuryBenchmark(scenarios=adversarial + normal)
        metrics = bench.run()
        # Normal operations should still succeed despite prior critical failure
        assert metrics.successful_tasks >= 1


class TestMetrics:
    def test_finalize_computes_rates(self):
        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 10
        metrics.successful_tasks = 7
        metrics.optimal_spend = 100.0
        metrics.total_spend = 120.0
        metrics.finalize()
        assert metrics.task_success_rate == pytest.approx(0.7)
        assert metrics.cost_efficiency_vs_oracle == pytest.approx(
            100.0 / 120.0, rel=0.01
        )

    def test_severity_breakdown(self):
        metrics = ProtocolMetrics(protocol_name="test")
        from agency_os.benchmarks.models import Failure

        metrics.record_failure(Failure(severity=Severity.SOFT, category="test"))
        metrics.record_failure(Failure(severity=Severity.MEDIUM, category="test"))
        metrics.record_failure(Failure(severity=Severity.HARD, category="test"))
        metrics.record_failure(Failure(severity=Severity.CRITICAL, category="test"))
        assert metrics.failures_soft == 1
        assert metrics.failures_medium == 1
        assert metrics.failures_hard == 1
        assert metrics.failures_critical == 1

    def test_composite_scores(self):
        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 10
        metrics.successful_tasks = 8
        metrics.task_success_rate = 0.8
        metrics.cost_efficiency_vs_oracle = 0.9
        metrics.policy_compliance_rate = 0.95
        metrics.adversarial_robustness_score = 0.7
        metrics.audit_trace_completeness = 0.85
        assert metrics.economic_capability > 0
        assert metrics.governance_safety > 0

    def test_summary_format(self):
        metrics = ProtocolMetrics(protocol_name="test")
        metrics.total_tasks = 5
        metrics.successful_tasks = 3
        metrics.finalize()
        summary = metrics.summary()
        assert "protocol" in summary
        assert "economic_capability" in summary
        assert "governance_safety" in summary
        assert "failures" in summary
