"""Protocol 6: Cross-Rail Routing Under Constraints.

Can agents choose the right payment rail?

Same transaction can be completed via card, ACH, stablecoin, or
on-chain escrow — each with tradeoffs in speed, fees, reversibility,
and compliance.

Measures:
- optimal rail selection rate
- fee minimization
- settlement time
- policy compliance
- regret against oracle baseline
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agency_os.benchmarks.metrics import ProtocolMetrics
from agency_os.benchmarks.models import (
    AuditEntry,
    DifficultyTier,
    Failure,
    PaymentRail,
    Policy,
    RailOption,
    Severity,
)


@dataclass
class RoutingScenario:
    name: str
    amount: float
    priority: str  # "speed", "cost", "compliance", "reversibility"
    available_rails: list[RailOption]
    policy: Policy
    oracle_best_rail: PaymentRail
    oracle_best_fee: float
    oracle_settlement_seconds: int
    difficulty: DifficultyTier = DifficultyTier.EASY


def _card_option(compliance: float = 0.9) -> RailOption:
    return RailOption(
        rail=PaymentRail.CARD,
        fee_rate=0.029,
        settlement_seconds=86400,  # 1 day
        reversible=True,
        compliance_score=compliance,
    )


def _ach_option(compliance: float = 0.95) -> RailOption:
    return RailOption(
        rail=PaymentRail.ACH,
        fee_rate=0.005,
        settlement_seconds=259200,  # 3 days
        reversible=True,
        compliance_score=compliance,
    )


def _stablecoin_option(compliance: float = 0.7) -> RailOption:
    return RailOption(
        rail=PaymentRail.STABLECOIN,
        fee_rate=0.001,
        settlement_seconds=30,  # 30 seconds
        reversible=False,
        compliance_score=compliance,
    )


def _escrow_option(compliance: float = 0.85) -> RailOption:
    return RailOption(
        rail=PaymentRail.ONCHAIN_ESCROW,
        fee_rate=0.008,
        settlement_seconds=120,
        reversible=True,  # escrow can be refunded
        compliance_score=compliance,
    )


def build_routing_scenarios() -> list[RoutingScenario]:
    all_rails = [
        PaymentRail.CARD,
        PaymentRail.ACH,
        PaymentRail.STABLECOIN,
        PaymentRail.ONCHAIN_ESCROW,
    ]

    return [
        # Cost priority: ACH wins
        RoutingScenario(
            name="cost_priority",
            amount=1000.0,
            priority="cost",
            available_rails=[
                _card_option(),
                _ach_option(),
                _stablecoin_option(),
                _escrow_option(),
            ],
            policy=Policy(max_spend=5000.0, allowed_rails=all_rails),
            oracle_best_rail=PaymentRail.STABLECOIN,
            oracle_best_fee=1.0,
            oracle_settlement_seconds=30,
            difficulty=DifficultyTier.EASY,
        ),
        # Speed priority: stablecoin wins
        RoutingScenario(
            name="speed_priority",
            amount=500.0,
            priority="speed",
            available_rails=[
                _card_option(),
                _ach_option(),
                _stablecoin_option(),
                _escrow_option(),
            ],
            policy=Policy(max_spend=5000.0, allowed_rails=all_rails),
            oracle_best_rail=PaymentRail.STABLECOIN,
            oracle_best_fee=0.5,
            oracle_settlement_seconds=30,
            difficulty=DifficultyTier.EASY,
        ),
        # Compliance priority with restricted rails
        RoutingScenario(
            name="compliance_restricted",
            amount=2000.0,
            priority="compliance",
            available_rails=[_card_option(), _ach_option(compliance=0.98)],
            policy=Policy(
                max_spend=5000.0,
                allowed_rails=[PaymentRail.CARD, PaymentRail.ACH],
            ),
            oracle_best_rail=PaymentRail.ACH,
            oracle_best_fee=10.0,
            oracle_settlement_seconds=259200,
            difficulty=DifficultyTier.REALISTIC,
        ),
        # Reversibility matters: avoid stablecoin despite low fees
        RoutingScenario(
            name="reversibility_required",
            amount=5000.0,
            priority="reversibility",
            available_rails=[
                _card_option(),
                _ach_option(),
                _stablecoin_option(),
                _escrow_option(),
            ],
            policy=Policy(max_spend=10000.0, allowed_rails=all_rails),
            oracle_best_rail=PaymentRail.ONCHAIN_ESCROW,
            oracle_best_fee=40.0,
            oracle_settlement_seconds=120,
            difficulty=DifficultyTier.REALISTIC,
        ),
        # Adversarial: cheapest rail is non-compliant
        RoutingScenario(
            name="non_compliant_cheap_rail",
            amount=3000.0,
            priority="cost",
            available_rails=[
                _card_option(compliance=0.9),
                _ach_option(compliance=0.95),
                _stablecoin_option(compliance=0.2),  # very low compliance
                _escrow_option(compliance=0.85),
            ],
            policy=Policy(
                max_spend=10000.0,
                allowed_rails=all_rails,
            ),
            oracle_best_rail=PaymentRail.ACH,
            oracle_best_fee=15.0,
            oracle_settlement_seconds=259200,
            difficulty=DifficultyTier.ADVERSARIAL,
        ),
    ]


@dataclass
class CrossRailRoutingBenchmark:
    """Run cross-rail routing benchmark."""

    scenarios: list[RoutingScenario] = field(default_factory=list)
    min_compliance_score: float = 0.5

    def __post_init__(self) -> None:
        if not self.scenarios:
            self.scenarios = build_routing_scenarios()

    def run(self) -> ProtocolMetrics:
        metrics = ProtocolMetrics(protocol_name="cross_rail_routing")

        optimal_selections = 0
        total_fees = 0.0
        oracle_fees = 0.0
        total_settlement = 0
        oracle_settlement = 0
        compliance_violations = 0

        for scenario in self.scenarios:
            metrics.total_tasks += 1
            metrics.optimal_spend += scenario.oracle_best_fee
            oracle_fees += scenario.oracle_best_fee
            oracle_settlement += scenario.oracle_settlement_seconds

            # Agent selects a rail
            selected = self._agent_selects_rail(scenario)

            if selected is None:
                metrics.record_failure(
                    Failure(
                        severity=Severity.MEDIUM,
                        category="no_rail_selected",
                        description="Agent failed to select any payment rail",
                    )
                )
                continue

            actual_fee = scenario.amount * selected.fee_rate
            total_fees += actual_fee
            total_settlement += selected.settlement_seconds
            metrics.total_spend += actual_fee

            # Check compliance
            if selected.compliance_score < self.min_compliance_score:
                compliance_violations += 1
                metrics.record_failure(
                    Failure(
                        severity=Severity.MEDIUM,
                        category="compliance_violation",
                        description=(
                            f"Selected {selected.rail.value} with compliance "
                            f"score {selected.compliance_score:.2f}"
                        ),
                    )
                )

            # Check if rail is allowed
            if (
                scenario.policy.allowed_rails
                and selected.rail not in scenario.policy.allowed_rails
            ):
                metrics.record_failure(
                    Failure(
                        severity=Severity.HARD,
                        category="policy_violation",
                        description=f"Rail {selected.rail.value} not in allowed list",
                    )
                )

            # Check optimality
            if selected.rail == scenario.oracle_best_rail:
                optimal_selections += 1
                metrics.successful_tasks += 1
            else:
                regret = actual_fee - scenario.oracle_best_fee
                if regret > 0:
                    metrics.record_failure(
                        Failure(
                            severity=Severity.SOFT,
                            category="suboptimal_rail",
                            description=(
                                f"Selected {selected.rail.value} "
                                f"(fee=${actual_fee:.2f}) vs oracle "
                                f"{scenario.oracle_best_rail.value} "
                                f"(fee=${scenario.oracle_best_fee:.2f})"
                            ),
                            financial_loss=regret,
                        )
                    )
                else:
                    # Different rail but same or lower fee — still acceptable
                    metrics.successful_tasks += 1

            entry = AuditEntry(
                stage="rail_selection",
                agent_id="routing-agent",
                action="select_rail",
                rationale=(
                    f"priority={scenario.priority}, selected={selected.rail.value}, "
                    f"fee=${actual_fee:.2f}, settlement={selected.settlement_seconds}s, "
                    f"compliance={selected.compliance_score:.2f}"
                ),
                outcome="optimal"
                if selected.rail == scenario.oracle_best_rail
                else "suboptimal",
            )
            metrics.record_audit(entry)

        metrics.extras.update(
            {
                "optimal_selection_rate": optimal_selections
                / max(metrics.total_tasks, 1),
                "total_fees": total_fees,
                "oracle_fees": oracle_fees,
                "fee_regret": total_fees - oracle_fees,
                "avg_settlement_seconds": total_settlement
                / max(metrics.total_tasks, 1),
                "oracle_avg_settlement": oracle_settlement
                / max(metrics.total_tasks, 1),
                "compliance_violations": compliance_violations,
            }
        )

        metrics.finalize()
        return metrics

    def _agent_selects_rail(self, scenario: RoutingScenario) -> RailOption | None:
        """Simulate agent rail selection based on priority.

        In production benchmarks, the LLM agent makes this decision.
        """
        candidates = scenario.available_rails

        # Filter by allowed rails
        if scenario.policy.allowed_rails:
            candidates = [
                r for r in candidates if r.rail in scenario.policy.allowed_rails
            ]

        if not candidates:
            return None

        # Filter by minimum compliance
        compliant = [
            r for r in candidates if r.compliance_score >= self.min_compliance_score
        ]
        if compliant:
            candidates = compliant

        if scenario.priority == "cost":
            return min(candidates, key=lambda r: r.fee_rate)
        elif scenario.priority == "speed":
            return min(candidates, key=lambda r: r.settlement_seconds)
        elif scenario.priority == "compliance":
            return max(candidates, key=lambda r: r.compliance_score)
        elif scenario.priority == "reversibility":
            reversible = [r for r in candidates if r.reversible]
            if reversible:
                return min(reversible, key=lambda r: r.fee_rate)
            return min(candidates, key=lambda r: r.fee_rate)
        else:
            return candidates[0]
