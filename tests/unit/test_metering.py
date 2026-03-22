"""Tests for MeteringCollector task_outcome tracking."""

from agency_os.metering.collector import MeteringCollector, TaskOutcome


def test_task_outcome_enum_values():
    assert TaskOutcome.success.value == "success"
    assert TaskOutcome.failure.value == "failure"
    assert TaskOutcome.partial.value == "partial"


def test_record_task_outcome():
    mc = MeteringCollector()
    mc.record_task_outcome(
        tenant_id="t1",
        org_id="o1",
        agent_id="a1",
        outcome=TaskOutcome.success,
        task_id="task-123",
        duration_sec=42.5,
    )
    assert mc.total_events == 1
    events = mc.get_tenant_events("t1")
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "task_outcome"
    assert e.metadata["outcome"] == "success"
    assert e.metadata["task_id"] == "task-123"
    assert e.metadata["duration_sec"] == 42.5


def test_record_task_outcome_minimal():
    mc = MeteringCollector()
    mc.record_task_outcome(
        tenant_id="t1", org_id="o1", agent_id="a1", outcome=TaskOutcome.failure
    )
    e = mc.get_tenant_events("t1")[0]
    assert e.metadata["outcome"] == "failure"
    assert "task_id" not in e.metadata
    assert "duration_sec" not in e.metadata


def test_get_agent_outcomes():
    mc = MeteringCollector()
    # Record mixed events for same agent
    mc.record_llm_call("t1", "o1", "a1", 100, 50)
    mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.success, task_id="t1")
    mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.failure, task_id="t2")
    mc.record_task_outcome("t1", "o1", "a2", TaskOutcome.success, task_id="t3")

    outcomes = mc.get_agent_outcomes("a1", "t1")
    assert len(outcomes) == 2
    # Most recent first
    assert outcomes[0].metadata["task_id"] == "t2"
    assert outcomes[1].metadata["task_id"] == "t1"

    # Other agent
    assert len(mc.get_agent_outcomes("a2", "t1")) == 1


def test_get_agent_outcomes_with_limit():
    mc = MeteringCollector()
    for i in range(5):
        mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.success, task_id=f"t{i}")
    outcomes = mc.get_agent_outcomes("a1", "t1", limit=3)
    assert len(outcomes) == 3
    # Most recent first
    assert outcomes[0].metadata["task_id"] == "t4"


def test_get_agent_outcomes_empty():
    mc = MeteringCollector()
    assert mc.get_agent_outcomes("nonexistent", "t1") == []


# --- Percentile aggregation ---


def _record_durations(mc, agent_id, durations):
    for d in durations:
        mc.record_task_outcome(
            "t1", "o1", agent_id, TaskOutcome.success, duration_sec=d
        )


def test_percentiles_basic():
    mc = MeteringCollector()
    # 1..100 gives clean percentile values
    _record_durations(mc, "a1", list(range(1, 101)))
    p = mc.get_agent_percentiles("a1", "t1")
    assert p["p5"] is not None
    assert p["p50"] is not None
    assert p["p95"] is not None
    # p50 of 1..100 should be ~50.5
    assert 49 <= p["p50"] <= 52
    # p5 should be low, p95 should be high
    assert p["p5"] < p["p50"] < p["p95"]


def test_percentiles_no_data():
    mc = MeteringCollector()
    p = mc.get_agent_percentiles("a1", "t1")
    assert p == {"p5": None, "p50": None, "p95": None}


def test_percentiles_single_value():
    mc = MeteringCollector()
    _record_durations(mc, "a1", [42.0])
    p = mc.get_agent_percentiles("a1", "t1")
    assert p["p5"] == 42.0
    assert p["p50"] == 42.0
    assert p["p95"] == 42.0


def test_percentiles_skips_missing_duration():
    mc = MeteringCollector()
    # Record some with duration, some without
    mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.success, duration_sec=10.0)
    mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.failure)  # no duration
    mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.success, duration_sec=20.0)
    p = mc.get_agent_percentiles("a1", "t1")
    # Only 2 values: 10, 20
    assert p["p50"] == 15.0  # midpoint


def test_percentiles_with_limit():
    mc = MeteringCollector()
    # Old slow tasks, then recent fast tasks
    _record_durations(mc, "a1", [100.0] * 10)
    _record_durations(mc, "a1", [5.0] * 10)
    p = mc.get_agent_percentiles("a1", "t1", limit=10)
    # Only recent 10 (all 5.0)
    assert p["p50"] == 5.0
    assert p["p95"] == 5.0


def test_percentiles_custom_metric():
    mc = MeteringCollector()
    for tokens in [100, 200, 300]:
        mc.record_task_outcome("t1", "o1", "a1", TaskOutcome.success, duration_sec=1.0)
        # Manually add a custom metric
        mc.get_agent_outcomes("a1", "t1", limit=1)[0].metadata["tokens_used"] = tokens
    p = mc.get_agent_percentiles("a1", "t1", metric="tokens_used")
    assert p["p50"] == 200.0


def test_percentiles_agents_isolated():
    mc = MeteringCollector()
    _record_durations(mc, "a1", [10.0, 20.0, 30.0])
    _record_durations(mc, "a2", [100.0, 200.0, 300.0])
    p1 = mc.get_agent_percentiles("a1", "t1")
    p2 = mc.get_agent_percentiles("a2", "t1")
    assert p1["p50"] == 20.0
    assert p2["p50"] == 200.0


def test_cross_tenant_metering_isolation():
    """Regression test for ZERA-138: cross-tenant information disclosure.

    Verifies that agent metering is scoped by tenant_id, preventing
    one tenant from seeing another tenant's metrics even when they
    use the same agent IDs (from shared packages).
    """
    mc = MeteringCollector()

    # Both tenants use the same agent ID (e.g., from "agency-basic" package)
    # Tenant A records success
    mc.record_task_outcome(
        tenant_id="tenant-a",
        org_id="org-a",
        agent_id="base-ceo",
        outcome=TaskOutcome.success,
        task_id="task-a1",
        duration_sec=10.0,
    )
    mc.record_task_outcome(
        tenant_id="tenant-a",
        org_id="org-a",
        agent_id="base-ceo",
        outcome=TaskOutcome.success,
        task_id="task-a2",
        duration_sec=20.0,
    )

    # Tenant B records failure
    mc.record_task_outcome(
        tenant_id="tenant-b",
        org_id="org-b",
        agent_id="base-ceo",
        outcome=TaskOutcome.failure,
        task_id="task-b1",
        duration_sec=100.0,
    )

    # Verify Tenant A only sees their own outcomes
    outcomes_a = mc.get_agent_outcomes("base-ceo", "tenant-a")
    assert len(outcomes_a) == 2
    assert all(e.tenant_id == "tenant-a" for e in outcomes_a)
    assert all(e.metadata.get("outcome") == "success" for e in outcomes_a)
    assert outcomes_a[0].metadata["task_id"] == "task-a2"  # Most recent first
    assert outcomes_a[1].metadata["task_id"] == "task-a1"

    # Verify Tenant B only sees their own outcomes
    outcomes_b = mc.get_agent_outcomes("base-ceo", "tenant-b")
    assert len(outcomes_b) == 1
    assert outcomes_b[0].tenant_id == "tenant-b"
    assert outcomes_b[0].metadata.get("outcome") == "failure"
    assert outcomes_b[0].metadata["task_id"] == "task-b1"

    # Verify percentiles are also isolated
    p_a = mc.get_agent_percentiles("base-ceo", "tenant-a")
    p_b = mc.get_agent_percentiles("base-ceo", "tenant-b")
    # Tenant A: durations [10.0, 20.0] → p50 = 15.0
    assert p_a["p50"] == 15.0
    # Tenant B: durations [100.0] → p50 = 100.0
    assert p_b["p50"] == 100.0
