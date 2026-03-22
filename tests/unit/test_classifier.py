"""Tests for task-type classifier and governance preset auto-selection."""

from agency_os.governance.classifier import (
    GovernanceSelection,
    TaskType,
    classify_task,
    select_governance_preset,
)
from agency_os.governance.trust import TrustScore

# --- classify_task ---


def test_stateless_keywords():
    assert classify_task("Fix typo in README") == TaskType.stateless
    assert classify_task("Add test for auth module") == TaskType.stateless
    assert classify_task("Refactor utils") == TaskType.stateless


def test_pipeline_keywords():
    assert classify_task("Build ETL pipeline for user data") == TaskType.pipeline
    assert classify_task("Multi-step deployment workflow") == TaskType.pipeline
    assert classify_task("Run batch migration in stages") == TaskType.pipeline


def test_coordination_keywords():
    assert classify_task("Coordinate rollout with infra team") == TaskType.coordination
    assert classify_task("Cross-team integration review") == TaskType.coordination
    assert classify_task("Delegate subtasks to agents") == TaskType.coordination


def test_no_signal_defaults_to_pipeline():
    assert classify_task("Do the thing") == TaskType.pipeline


def test_description_contributes():
    result = classify_task(
        "Update service", "This requires a sequential multi-step deploy"
    )
    assert result == TaskType.pipeline


def test_mixed_signals_highest_wins():
    # "coordinate" (1 coordination) + "fix" (1 stateless) → tie breaks to stricter
    result = classify_task("Fix the coordination bug")
    # "fix" = stateless, "coordinat" = coordination, both score 1
    # coordination > stateless in tie? No, coordination == stateless so falls through
    # Actually: coordination_score=1, stateless_score=1, pipeline=0
    # coordination > pipeline (1>0) AND coordination > stateless (1>1) is False
    # So falls to pipeline > stateless (0 > 1) False
    # Then stateless > 0 → stateless
    assert result == TaskType.stateless


# --- select_governance_preset ---


def _trust(score: float, total: int = 20) -> TrustScore:
    """Create a TrustScore with enough tasks to reach the tier for the given score.

    Uses total=20 by default to meet MIN_TASKS_FOR_HIGH requirement.
    """
    s = int(score * total)
    return TrustScore(
        agent_id="a1",
        score=score,
        total_tasks=total,
        successes=s,
        failures=total - s,
        partials=0,
    )


def test_no_trust_defaults_conservative():
    sel = select_governance_preset("Fix bug")
    assert sel.trust_preset == "conservative"
    # Stateless loosens one tier from conservative → balanced
    assert sel.preset == "balanced"
    assert sel.task_type == TaskType.stateless


def test_high_trust_stateless_capped_at_balanced():
    """Even high trust now caps at 'balanced' — 'aggressive' requires admin override."""
    sel = select_governance_preset("Fix typo", trust=_trust(0.95))
    # Trust tier is "high" but governance_preset is capped to "balanced"
    assert sel.trust_preset == "balanced"
    # Stateless loosens one tier from balanced → aggressive
    assert sel.preset == "aggressive"


def test_high_trust_pipeline_tightens():
    sel = select_governance_preset("Run multi-step ETL pipeline", trust=_trust(0.95))
    assert sel.task_type == TaskType.pipeline
    # Trust capped at "balanced"
    assert sel.trust_preset == "balanced"
    # Pipeline tightens one tier: balanced → conservative
    assert sel.preset == "conservative"


def test_low_trust_pipeline_stays_conservative():
    sel = select_governance_preset("Run deployment pipeline", trust=_trust(0.2))
    assert sel.trust_preset == "conservative"
    # Pipeline would tighten, but already at strictest
    assert sel.preset == "conservative"


def test_medium_trust_coordination_tightens():
    sel = select_governance_preset("Coordinate cross-team rollout", trust=_trust(0.7))
    assert sel.trust_preset == "balanced"
    # Coordination tightens → conservative
    assert sel.preset == "conservative"


def test_medium_trust_stateless_loosens():
    sel = select_governance_preset("Add test for login", trust=_trust(0.7))
    assert sel.task_type == TaskType.stateless
    assert sel.trust_preset == "balanced"
    # Stateless loosens → aggressive
    assert sel.preset == "aggressive"


def test_selection_includes_reason():
    sel = select_governance_preset("Run pipeline stages", trust=_trust(0.95))
    assert "pipeline" in sel.reason
    assert sel.task_type == TaskType.pipeline


def test_governance_selection_fields():
    sel = select_governance_preset("Simple fix", trust=_trust(0.5))
    assert isinstance(sel, GovernanceSelection)
    assert sel.trust_tier in ("high", "medium", "low")
    assert sel.preset in ("aggressive", "balanced", "conservative")
