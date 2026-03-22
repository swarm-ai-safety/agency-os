"""Rolling trust scores per agent based on task completion history."""

from __future__ import annotations

from dataclasses import dataclass

from agency_os.metering.collector import MeteringCollector, TaskOutcome

# Default rolling window size
DEFAULT_WINDOW = 20

# Trust tier thresholds (score >= threshold → tier)
TIER_HIGH = 0.85
TIER_LOW = 0.50

# Minimum number of tasks before trust can rise above "low" tier.
# Prevents rapid inflation via a small burst of fake successes.
MIN_TASKS_FOR_MEDIUM = 10
MIN_TASKS_FOR_HIGH = 20

# Maximum governance preset that trust alone can recommend.
# "aggressive" is only reachable via explicit admin override, never via
# automated trust scoring.  This caps the automatic ceiling at "balanced".
_MAX_AUTO_PRESET = "balanced"
_PRESET_CEILING = {
    "aggressive": _MAX_AUTO_PRESET,
    "balanced": "balanced",
    "conservative": "conservative",
}


@dataclass(frozen=True)
class TrustScore:
    """Trust score for an agent."""

    agent_id: str
    score: float  # 0.0–1.0
    total_tasks: int  # tasks in the window
    successes: int
    failures: int
    partials: int

    @property
    def tier(self) -> str:
        """Map score to a governance tier: 'high', 'medium', or 'low'.

        Requires minimum task counts to prevent rapid trust inflation:
        - 'high' requires at least MIN_TASKS_FOR_HIGH tasks in the window
        - 'medium' requires at least MIN_TASKS_FOR_MEDIUM tasks
        """
        if self.total_tasks == 0:
            return "low"  # No history → conservative default
        if self.score >= TIER_HIGH and self.total_tasks >= MIN_TASKS_FOR_HIGH:
            return "high"
        if self.score >= TIER_LOW and self.total_tasks >= MIN_TASKS_FOR_MEDIUM:
            return "medium"
        return "low"

    @property
    def governance_preset(self) -> str:
        """Suggested governance preset name based on trust tier.

        The 'aggressive' preset is never returned via automated trust
        scoring — it requires explicit admin configuration.  This prevents
        a compromised or gaming agent from disabling all governance controls.
        """
        raw = {
            "high": "aggressive",
            "medium": "balanced",
            "low": "conservative",
        }[self.tier]
        return _PRESET_CEILING.get(raw, raw)


# Minimum seconds between consecutive task outcomes for them to count.
# Outcomes arriving faster than this are suspicious (flooding).
MIN_OUTCOME_INTERVAL_SEC = 5.0


def compute_trust_score(
    collector: MeteringCollector,
    agent_id: str,
    tenant_id: str,
    window: int = DEFAULT_WINDOW,
    min_outcome_interval: float = MIN_OUTCOME_INTERVAL_SEC,
) -> TrustScore:
    """
    Compute a rolling trust score for an agent.

    Looks at the last `window` task_outcome events. Scores partial
    completions at 0.5 weight, successes at 1.0, failures at 0.0.

    Applies rate-limiting: outcomes that arrive faster than
    ``min_outcome_interval`` apart are discarded to prevent
    trust score inflation via rapid fake-success flooding.

    Args:
        collector: MeteringCollector with recorded events.
        agent_id: Agent to score.
        tenant_id: Tenant to scope query to.
        window: Number of recent outcomes to consider.
        min_outcome_interval: Minimum seconds between outcomes (0 to disable).

    Returns:
        TrustScore with the computed score and metadata.
    """
    raw_outcomes = collector.get_agent_outcomes(agent_id, tenant_id, limit=window * 2)

    # Filter out suspiciously rapid outcomes (rate-limiting)
    if min_outcome_interval > 0:
        outcomes = _filter_rapid_outcomes(raw_outcomes, min_outcome_interval)[:window]
    else:
        outcomes = raw_outcomes[:window]

    successes = 0
    failures = 0
    partials = 0

    for event in outcomes:
        outcome_val = event.metadata.get("outcome")
        if outcome_val == TaskOutcome.success.value:
            successes += 1
        elif outcome_val == TaskOutcome.failure.value:
            failures += 1
        elif outcome_val == TaskOutcome.partial.value:
            partials += 1

    total = successes + failures + partials
    if total == 0:
        score = 0.0
    else:
        # Partial completions count as half credit
        score = (successes + 0.5 * partials) / total

    return TrustScore(
        agent_id=agent_id,
        score=score,
        total_tasks=total,
        successes=successes,
        failures=failures,
        partials=partials,
    )


def _filter_rapid_outcomes(
    outcomes: list,
    min_interval: float = MIN_OUTCOME_INTERVAL_SEC,
) -> list:
    """Discard outcomes that arrive faster than the minimum interval.

    The input list is expected to be sorted most-recent-first.
    """
    if not outcomes:
        return []

    filtered = [outcomes[0]]
    for event in outcomes[1:]:
        prev_ts = filtered[-1].timestamp
        if abs(prev_ts - event.timestamp) >= min_interval:
            filtered.append(event)

    return filtered
