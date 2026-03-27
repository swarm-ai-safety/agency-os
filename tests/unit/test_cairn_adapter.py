"""Tests for CAIRN protocol adapter (ZERA-371)."""

from agency_os.governance.cairn_adapter import (
    CairnFailureClassification,
    CairnFailureType,
    CairnMapping,
    CairnTaskType,
    classify_failure,
    map_task_type,
)
from agency_os.governance.classifier import TaskType

# --- map_task_type ---


def test_stateless_maps_to_single_action():
    result = map_task_type(TaskType.stateless)
    assert result.cairn_task_type == CairnTaskType.single_action
    assert result.requires_checkpoints is False


def test_pipeline_maps_to_multi_step():
    result = map_task_type(TaskType.pipeline)
    assert result.cairn_task_type == CairnTaskType.multi_step
    assert result.requires_checkpoints is True


def test_coordination_maps_to_multi_agent():
    result = map_task_type(TaskType.coordination)
    assert result.cairn_task_type == CairnTaskType.multi_agent
    assert result.requires_checkpoints is True


def test_mapping_preserves_original_type():
    result = map_task_type(TaskType.pipeline)
    assert result.agency_os_task_type == TaskType.pipeline


def test_mapping_returns_frozen_dataclass():
    result = map_task_type(TaskType.stateless)
    assert isinstance(result, CairnMapping)


# --- classify_failure: LIVENESS ---


def test_liveness_timeout():
    result = classify_failure("Agent timed out after 30s")
    assert result.failure_type == CairnFailureType.LIVENESS


def test_liveness_connection_refused():
    result = classify_failure("Connection refused to downstream service")
    assert result.failure_type == CairnFailureType.LIVENESS


def test_liveness_unresponsive():
    result = classify_failure("Agent unresponsive, heartbeat missed")
    assert result.failure_type == CairnFailureType.LIVENESS


def test_liveness_deadlock():
    result = classify_failure("Deadlock detected in task executor")
    assert result.failure_type == CairnFailureType.LIVENESS


# --- classify_failure: RESOURCE ---


def test_resource_budget():
    result = classify_failure("Budget exceeded for this agent")
    assert result.failure_type == CairnFailureType.RESOURCE


def test_resource_rate_limit():
    result = classify_failure("Rate limit hit: 429 Too Many Requests")
    assert result.failure_type == CairnFailureType.RESOURCE


def test_resource_oom():
    result = classify_failure("Process killed: out of memory")
    assert result.failure_type == CairnFailureType.RESOURCE


def test_resource_quota():
    result = classify_failure("API quota exhausted for the month")
    assert result.failure_type == CairnFailureType.RESOURCE


# --- classify_failure: LOGIC ---


def test_logic_validation():
    result = classify_failure("Validation failed: expected string, got int")
    assert result.failure_type == CairnFailureType.LOGIC


def test_logic_wrong_output():
    result = classify_failure("Wrong output format returned by agent")
    assert result.failure_type == CairnFailureType.LOGIC


def test_logic_assertion():
    result = classify_failure("Assertion error: mismatch in response schema")
    assert result.failure_type == CairnFailureType.LOGIC


def test_logic_hallucination():
    result = classify_failure("Agent produced hallucinated data")
    assert result.failure_type == CairnFailureType.LOGIC


# --- classify_failure: edge cases ---


def test_no_signal_defaults_to_logic():
    result = classify_failure("Task did not complete")
    assert result.failure_type == CairnFailureType.LOGIC
    assert result.confidence == 0.0
    assert result.matched_signals == 0


def test_mixed_signals_highest_wins():
    # "timeout" (liveness) + "budget exceeded" (resource x2)
    result = classify_failure("Timeout while checking budget exceeded limit")
    assert result.failure_type == CairnFailureType.RESOURCE


def test_confidence_increases_with_signals():
    weak = classify_failure("Agent timed out")
    strong = classify_failure(
        "Agent timed out, unresponsive, heartbeat missed, connection refused"
    )
    assert strong.confidence >= weak.confidence
    assert strong.matched_signals > weak.matched_signals


def test_classification_returns_frozen_dataclass():
    result = classify_failure("timeout")
    assert isinstance(result, CairnFailureClassification)
