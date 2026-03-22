"""Bid-based task routing — agents compete for tasks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agency_os.agents.bid_strategies import get_strategy
from agency_os.agents.business_agent import BusinessAgent

logger = logging.getLogger(__name__)


@dataclass
class Bid:
    agent_id: str
    amount: float
    reputation: float
    score: float  # Final ranking score


@dataclass
class TaskAssignment:
    task_id: str
    description: str
    assigned_to: str
    winning_bid: float
    bids: list[Bid]
    status: str = "assigned"
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskRouter:
    """
    Routes tasks to agents via competitive bidding.

    Eligible agents submit bids based on their strategy. The router
    ranks bids by a composite score (bid amount * reputation * expertise match)
    and assigns the task to the highest-scoring agent.
    """

    def __init__(self, agents: list[BusinessAgent]):
        self._agents = {a.agent_id: a for a in agents}

    def route(
        self,
        description: str,
        eligible_agents: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskAssignment:
        """
        Route a task to the best agent via bidding.

        Args:
            description: Task description.
            eligible_agents: Optional list of agent IDs to restrict bidding to.
            metadata: Optional task metadata.

        Returns:
            TaskAssignment with winner and all bids.

        Raises:
            RuntimeError: If no agents are eligible or all bids are zero.
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # Determine eligible agents
        if eligible_agents:
            candidates = [
                self._agents[aid] for aid in eligible_agents if aid in self._agents
            ]
        else:
            candidates = list(self._agents.values())

        if not candidates:
            raise RuntimeError("No eligible agents for task routing")

        # Collect bids
        bids: list[Bid] = []
        for agent in candidates:
            strategy = get_strategy(agent.economic.bid_strategy.value)
            amount = strategy.compute_bid(agent, description)

            # Composite score: bid * reputation * specialization match
            task_lower = description.lower()

            # Fine-grained: domain_tags give 15% per matching tag (max 2 tags)
            tag_hits = sum(1 for tag in agent.domain_tags if tag.lower() in task_lower)
            tag_bonus = 1.0 + 0.15 * min(tag_hits, 2)

            # Coarse: division match gives 10% boost as fallback
            division_bonus = 1.1 if agent.spec.division.lower() in task_lower else 1.0

            score = amount * agent.reputation * max(tag_bonus, division_bonus)

            bids.append(
                Bid(
                    agent_id=agent.agent_id,
                    amount=amount,
                    reputation=agent.reputation,
                    score=score,
                )
            )

        # Rank by score descending
        bids.sort(key=lambda b: b.score, reverse=True)

        if not bids or bids[0].score <= 0:
            raise RuntimeError("All bids are zero — no agent can accept this task")

        winner = bids[0]
        logger.info(
            f"Task {task_id} routed to {winner.agent_id} "
            f"(score: {winner.score:.2f}, bid: {winner.amount:.2f})"
        )

        return TaskAssignment(
            task_id=task_id,
            description=description,
            assigned_to=winner.agent_id,
            winning_bid=winner.amount,
            bids=bids,
            metadata=metadata or {},
        )
