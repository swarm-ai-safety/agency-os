"""Data models for the AutoHarness evaluation system."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class EvalVerdict(str, enum.Enum):
    """Outcome of evaluating a single challenge response."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class ChallengeDifficulty(str, enum.Enum):
    """Difficulty tier for generated challenges."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class EvalRubric:
    """Scoring rubric for a challenge.

    Each criterion maps a name to a weight (0–1). The evaluator scores
    each criterion independently, then computes a weighted average.
    """

    criteria: dict[str, float]  # name → weight (must sum to 1.0)
    pass_threshold: float = 0.7  # weighted score >= this → PASS
    partial_threshold: float = 0.4  # weighted score >= this → PARTIAL

    def __post_init__(self) -> None:
        total = sum(self.criteria.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Rubric criteria weights must sum to 1.0, got {total:.3f}"
            )


@dataclass
class Challenge:
    """A single evaluation challenge for an agent.

    Generated from agent specs and domain knowledge, each challenge
    contains a task description, expected behavior criteria, and a
    scoring rubric.
    """

    challenge_id: str = field(default_factory=lambda: f"ch-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""  # The task prompt sent to the agent
    domain: str = ""  # Division/domain this targets (e.g. "engineering")
    difficulty: ChallengeDifficulty = ChallengeDifficulty.MEDIUM
    rubric: EvalRubric = field(
        default_factory=lambda: EvalRubric(criteria={"completeness": 1.0})
    )
    expected_signals: list[str] = field(default_factory=list)  # Keywords/patterns
    anti_signals: list[str] = field(default_factory=list)  # Should NOT appear
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class ChallengeResult:
    """Result of an agent attempting a challenge."""

    challenge_id: str
    agent_id: str
    verdict: EvalVerdict
    weighted_score: float  # 0.0–1.0
    criterion_scores: dict[str, float]  # criterion name → score (0.0–1.0)
    response: str = ""  # The agent's raw response
    reasoning: str = ""  # Why the evaluator scored it this way
    duration_sec: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaderboardEntry:
    """Aggregated performance for an agent across challenges."""

    agent_id: str
    agent_name: str
    division: str
    challenges_attempted: int = 0
    challenges_passed: int = 0
    challenges_partial: int = 0
    challenges_failed: int = 0
    avg_score: float = 0.0
    pass_rate: float = 0.0
    trend: str = "stable"  # "improving" | "declining" | "stable"
    reputation_before: float = 1.0
    reputation_after: float = 1.0
    reputation_delta: float = 0.0


@dataclass
class HarnessConfig:
    """Configuration for an AutoHarness run."""

    challenges_per_agent: int = 5
    difficulty_distribution: dict[str, float] = field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    )
    reputation_reward: float = 0.03  # Rep gain per PASS
    reputation_penalty: float = -0.06  # Rep loss per FAIL
    reputation_partial: float = 0.01  # Rep gain per PARTIAL
    freeze_on_consecutive_fails: int = 3  # Circuit-breaker threshold
    record_to_metering: bool = True  # Push results to MeteringCollector


@dataclass
class HarnessReport:
    """Full report from an AutoHarness run."""

    run_id: str = field(default_factory=lambda: f"harness-{uuid.uuid4().hex[:8]}")
    results: list[ChallengeResult] = field(default_factory=list)
    leaderboard: list[LeaderboardEntry] = field(default_factory=list)
    challenges_generated: int = 0
    challenges_executed: int = 0
    total_duration_sec: float = 0.0
    timestamp: float = field(default_factory=time.time)
    config: HarnessConfig = field(default_factory=HarnessConfig)

    def summary(self) -> dict[str, Any]:
        """Return a serializable summary."""
        return {
            "run_id": self.run_id,
            "challenges_generated": self.challenges_generated,
            "challenges_executed": self.challenges_executed,
            "total_duration_sec": round(self.total_duration_sec, 2),
            "agents_evaluated": len(self.leaderboard),
            "avg_pass_rate": (
                sum(e.pass_rate for e in self.leaderboard) / len(self.leaderboard)
                if self.leaderboard
                else 0.0
            ),
            "top_agent": (
                max(self.leaderboard, key=lambda e: e.avg_score).agent_id
                if self.leaderboard
                else None
            ),
            "timestamp": self.timestamp,
        }
