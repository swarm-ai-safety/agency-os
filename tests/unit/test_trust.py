"""Tests for agent trust score computation."""

import time
from functools import partial

from agency_os.governance.trust import (
    MIN_TASKS_FOR_HIGH,
    MIN_TASKS_FOR_MEDIUM,
    TIER_HIGH,
    TIER_LOW,
    TrustScore,
    _filter_rapid_outcomes,
    compute_trust_score,
)
from agency_os.metering.collector import MeteringCollector, TaskOutcome, UsageEvent


def _record_outcomes(mc, agent_id, outcomes):
    """Helper to record a sequence of outcomes for an agent."""
    for outcome in outcomes:
        mc.record_task_outcome("t1", "o1", agent_id, outcome)


# Use min_outcome_interval=0 in tests since outcomes are recorded instantly
_compute = partial(compute_trust_score, min_outcome_interval=0)


def test_no_history_returns_zero_score():
    mc = MeteringCollector()
    ts = _compute(mc, "agent-new", "t1")
    assert ts.score == 0.0
    assert ts.total_tasks == 0
    assert ts.tier == "low"
    assert ts.governance_preset == "conservative"


def test_all_successes_needs_min_tasks_for_high():
    mc = MeteringCollector()
    # 10 successes is not enough for "high" tier (requires MIN_TASKS_FOR_HIGH=20)
    _record_outcomes(mc, "a1", [TaskOutcome.success] * 10)
    ts = _compute(mc, "a1", "t1")
    assert ts.score == 1.0
    assert ts.successes == 10
    # With only 10 tasks, "high" is unreachable — falls to "medium"
    assert ts.tier == "medium"
    # governance_preset is capped at "balanced" (never auto-returns "aggressive")
    assert ts.governance_preset == "balanced"


def test_all_failures():
    mc = MeteringCollector()
    _record_outcomes(mc, "a1", [TaskOutcome.failure] * 5)
    ts = _compute(mc, "a1", "t1")
    assert ts.score == 0.0
    assert ts.failures == 5
    assert ts.tier == "low"
    assert ts.governance_preset == "conservative"


def test_mixed_outcomes():
    mc = MeteringCollector()
    # 7 success, 2 partial, 1 failure = (7 + 1.0) / 10 = 0.8
    _record_outcomes(mc, "a1", [TaskOutcome.success] * 7)
    _record_outcomes(mc, "a1", [TaskOutcome.partial] * 2)
    _record_outcomes(mc, "a1", [TaskOutcome.failure] * 1)
    ts = _compute(mc, "a1", "t1")
    assert ts.score == 0.8
    assert ts.total_tasks == 10
    assert ts.tier == "medium"
    assert ts.governance_preset == "balanced"


def test_partial_only():
    mc = MeteringCollector()
    _record_outcomes(mc, "a1", [TaskOutcome.partial] * 4)
    ts = _compute(mc, "a1", "t1")
    assert ts.score == 0.5
    assert ts.partials == 4
    # Only 4 tasks — below MIN_TASKS_FOR_MEDIUM, so tier is "low"
    assert ts.tier == "low"


def test_window_limits_events():
    mc = MeteringCollector()
    # 30 events: first 20 successes, then 10 failures
    _record_outcomes(mc, "a1", [TaskOutcome.success] * 20)
    _record_outcomes(mc, "a1", [TaskOutcome.failure] * 10)
    # Window=10 should only see the 10 most recent (all failures)
    ts = _compute(mc, "a1", "t1", window=10)
    assert ts.failures == 10
    assert ts.score == 0.0


def test_agents_isolated():
    mc = MeteringCollector()
    _record_outcomes(mc, "a1", [TaskOutcome.success] * 5)
    _record_outcomes(mc, "a2", [TaskOutcome.failure] * 5)
    assert _compute(mc, "a1", "t1").score == 1.0
    assert _compute(mc, "a2", "t1").score == 0.0


def test_tier_boundaries_require_min_tasks():
    """Tier boundaries now require minimum task counts."""
    # High score but only 1 task → still "low" (need MIN_TASKS_FOR_MEDIUM)
    ts = TrustScore(
        agent_id="a",
        score=TIER_HIGH,
        total_tasks=1,
        successes=1,
        failures=0,
        partials=0,
    )
    assert ts.tier == "low"  # Not enough tasks

    # High score with enough tasks for medium but not high
    ts = TrustScore(
        agent_id="a",
        score=TIER_HIGH,
        total_tasks=MIN_TASKS_FOR_MEDIUM,
        successes=MIN_TASKS_FOR_MEDIUM,
        failures=0,
        partials=0,
    )
    assert ts.tier == "high" if MIN_TASKS_FOR_MEDIUM >= MIN_TASKS_FOR_HIGH else "medium"

    # High score with enough tasks for high
    ts = TrustScore(
        agent_id="a",
        score=TIER_HIGH,
        total_tasks=MIN_TASKS_FOR_HIGH,
        successes=MIN_TASKS_FOR_HIGH,
        failures=0,
        partials=0,
    )
    assert ts.tier == "high"

    # Below TIER_LOW with enough tasks → low
    ts = TrustScore(
        agent_id="a",
        score=TIER_LOW - 0.01,
        total_tasks=MIN_TASKS_FOR_HIGH,
        successes=0,
        failures=MIN_TASKS_FOR_HIGH,
        partials=0,
    )
    assert ts.tier == "low"


# -- Security: governance preset ceiling --


def test_governance_preset_never_returns_aggressive():
    """The 'aggressive' preset should never be returned by automated trust scoring."""
    ts = TrustScore(
        agent_id="a",
        score=1.0,
        total_tasks=MIN_TASKS_FOR_HIGH,
        successes=MIN_TASKS_FOR_HIGH,
        failures=0,
        partials=0,
    )
    assert ts.tier == "high"
    # Even "high" trust is capped at "balanced" for auto-selection
    assert ts.governance_preset == "balanced"


# -- Security: rapid outcome filtering --


def test_filter_rapid_outcomes_drops_close_timestamps():
    """Outcomes arriving too fast should be filtered out."""
    now = time.time()
    events = [
        UsageEvent(
            tenant_id="t",
            org_id="o",
            agent_id="a",
            event_type="task_outcome",
            timestamp=now,
        ),
        UsageEvent(
            tenant_id="t",
            org_id="o",
            agent_id="a",
            event_type="task_outcome",
            timestamp=now - 1,
        ),
        UsageEvent(
            tenant_id="t",
            org_id="o",
            agent_id="a",
            event_type="task_outcome",
            timestamp=now - 2,
        ),
        UsageEvent(
            tenant_id="t",
            org_id="o",
            agent_id="a",
            event_type="task_outcome",
            timestamp=now - 10,
        ),
        UsageEvent(
            tenant_id="t",
            org_id="o",
            agent_id="a",
            event_type="task_outcome",
            timestamp=now - 20,
        ),
    ]
    # Events at now, now-1, now-2 are within 5s of each other → only first kept
    # Then now-10 is 10s from now → kept; now-20 is 10s from now-10 → kept
    filtered = _filter_rapid_outcomes(events)
    assert len(filtered) == 3


# -- Effectiveness trend --


def test_trend_improving():
    import agency_os.service.api.routers.agents as agents_mod

    mc = MeteringCollector()
    agents_mod._metering = mc
    try:
        # Older outcomes: all failures, then recent: all successes
        _record_outcomes(mc, "trend-a", [TaskOutcome.failure] * 10)
        _record_outcomes(mc, "trend-a", [TaskOutcome.success] * 10)
        assert agents_mod._compute_trend("trend-a", "t1") == "improving"
    finally:
        agents_mod._metering = None


def test_trend_declining():
    import agency_os.service.api.routers.agents as agents_mod

    mc = MeteringCollector()
    agents_mod._metering = mc
    try:
        _record_outcomes(mc, "trend-b", [TaskOutcome.success] * 10)
        _record_outcomes(mc, "trend-b", [TaskOutcome.failure] * 10)
        assert agents_mod._compute_trend("trend-b", "t1") == "declining"
    finally:
        agents_mod._metering = None


def test_trend_stable_few_outcomes():
    import agency_os.service.api.routers.agents as agents_mod

    mc = MeteringCollector()
    agents_mod._metering = mc
    try:
        _record_outcomes(mc, "trend-c", [TaskOutcome.success] * 3)
        assert agents_mod._compute_trend("trend-c", "t1") == "stable"
    finally:
        agents_mod._metering = None
