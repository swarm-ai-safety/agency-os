"""Pluggable bid strategy classes for agent task competition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agency_os.agents.business_agent import BusinessAgent


class BidStrategyBase(ABC):
    """Base class for bid strategies."""

    @abstractmethod
    def compute_bid(self, agent: BusinessAgent, task_description: str) -> float:
        """Compute a bid amount for a task."""
        ...


class DefaultBid(BidStrategyBase):
    """Simple 10% of balance bid."""

    def compute_bid(self, agent: BusinessAgent, task_description: str) -> float:
        return agent.balance * 0.1


class QualityWeightedBid(BidStrategyBase):
    """Bid scaled by reputation — higher reputation agents bid more confidently."""

    def compute_bid(self, agent: BusinessAgent, task_description: str) -> float:
        return agent.balance * 0.1 * agent.reputation


class SpecializationBonusBid(BidStrategyBase):
    """Higher bid when task keywords match agent's division/expertise."""

    def compute_bid(self, agent: BusinessAgent, task_description: str) -> float:
        base = agent.balance * 0.1
        # Bonus if task mentions agent's division or name
        task_lower = task_description.lower()
        division_match = agent.spec.division.lower() in task_lower
        name_match = agent.spec.name.lower() in task_lower
        multiplier = 1.0
        if division_match:
            multiplier += 0.3
        if name_match:
            multiplier += 0.2
        return base * multiplier


class BudgetConsciousBid(BidStrategyBase):
    """Conservative bidding — preserves balance for many tasks."""

    def compute_bid(self, agent: BusinessAgent, task_description: str) -> float:
        return agent.balance * 0.05


# Registry of strategy instances
STRATEGIES: dict[str, BidStrategyBase] = {
    "default": DefaultBid(),
    "quality_weighted": QualityWeightedBid(),
    "specialization_bonus": SpecializationBonusBid(),
    "budget_conscious": BudgetConsciousBid(),
}


def get_strategy(name: str) -> BidStrategyBase:
    """Get a bid strategy by name."""
    strategy = STRATEGIES.get(name)
    if strategy is None:
        raise KeyError(
            f"Unknown bid strategy: {name!r}. Available: {list(STRATEGIES.keys())}"
        )
    return strategy
