"""Tests for ATIF trajectory recorder."""

import json

import pytest

from agency_os.observability.trajectory import (
    HARNESS_NAME,
    HARNESS_VERSION,
    SCHEMA_VERSION,
    TrajectoryRecorder,
)


@pytest.fixture
def recorder():
    return TrajectoryRecorder(
        agent_id="agent-001",
        agent_name="DevOps Engineer",
        model_name="claude-sonnet-4-20250514",
        task_id="task-xyz",
        tenant_id="tenant-abc",
        org_id="org-123",
    )


class TestTrajectoryRecorderInit:
    def test_creates_session_id(self, recorder):
        assert recorder._session_id.startswith("task-")

    def test_custom_session_id(self):
        r = TrajectoryRecorder(
            agent_id="a", agent_name="Test", session_id="custom-session"
        )
        assert r._session_id == "custom-session"

    def test_extra_metadata(self, recorder):
        assert recorder._extra["agent_id"] == "agent-001"
        assert recorder._extra["task_id"] == "task-xyz"
        assert recorder._extra["tenant_id"] == "tenant-abc"
        assert recorder._extra["org_id"] == "org-123"
        assert recorder._extra["harness"] == HARNESS_NAME


class TestStepRecording:
    def test_system_step(self, recorder):
        recorder.record_system_step("You are a DevOps agent.")
        assert len(recorder._steps) == 1
        step = recorder._steps[0]
        assert step.step_id == 1
        assert step.source == "system"
        assert step.message == "You are a DevOps agent."
        assert step.timestamp is not None

    def test_user_step(self, recorder):
        recorder.record_user_step("Deploy the app")
        step = recorder._steps[0]
        assert step.source == "user"
        assert step.message == "Deploy the app"

    def test_agent_step_basic(self, recorder):
        recorder.record_agent_step(
            response_text="Deploying now...",
            tokens_in=100,
            tokens_out=50,
        )
        step = recorder._steps[0]
        assert step.source == "agent"
        assert step.message == "Deploying now..."
        assert step.model_name == "claude-sonnet-4-20250514"
        assert recorder._total_tokens_in == 100
        assert recorder._total_tokens_out == 50

    def test_agent_step_with_reasoning(self, recorder):
        recorder.record_agent_step(
            response_text="Done",
            reasoning="I should check the config first",
        )
        step = recorder._steps[0]
        assert step.reasoning_content == "I should check the config first"

    def test_agent_step_with_tool_calls(self, recorder):
        recorder.record_agent_step(
            response_text="",
            tool_calls=[
                {
                    "tool_call_id": "tc-1",
                    "function_name": "Bash",
                    "arguments": {"command": "ls"},
                }
            ],
        )
        step = recorder._steps[0]
        assert step.tool_calls is not None
        assert len(step.tool_calls) == 1
        assert step.tool_calls[0].function_name == "Bash"
        assert step.tool_calls[0].arguments == {"command": "ls"}

    def test_agent_step_with_tool_results(self, recorder):
        recorder.record_agent_step(
            response_text="",
            tool_results=[{"source_call_id": "tc-1", "content": "file1.py\nfile2.py"}],
        )
        step = recorder._steps[0]
        assert step.observation is not None
        assert len(step.observation.results) == 1
        assert step.observation.results[0].content == "file1.py\nfile2.py"

    def test_agent_step_auto_generates_tool_call_id(self, recorder):
        recorder.record_agent_step(
            response_text="",
            tool_calls=[{"function_name": "Read", "arguments": {}}],
        )
        tc = recorder._steps[0].tool_calls[0]
        assert tc.tool_call_id.startswith("tc-")

    def test_error_step(self, recorder):
        recorder.record_error_step("Connection timeout")
        step = recorder._steps[0]
        assert step.source == "system"
        assert "[ERROR]" in step.message

    def test_step_ids_increment(self, recorder):
        recorder.record_system_step("sys")
        recorder.record_user_step("user")
        recorder.record_agent_step(response_text="agent")
        ids = [s.step_id for s in recorder._steps]
        assert ids == [1, 2, 3]

    def test_token_accumulation(self, recorder):
        recorder.record_agent_step(response_text="a", tokens_in=100, tokens_out=50)
        recorder.record_agent_step(response_text="b", tokens_in=200, tokens_out=75)
        assert recorder._total_tokens_in == 300
        assert recorder._total_tokens_out == 125

    def test_cost_accumulation(self, recorder):
        recorder.record_agent_step(response_text="a", cost_usd=0.01)
        recorder.record_agent_step(response_text="b", cost_usd=0.02)
        assert abs(recorder._total_cost_usd - 0.03) < 1e-9


class TestGovernanceMetadata:
    def test_set_governance(self, recorder):
        recorder.set_governance(
            preset="conservative",
            task_type="coordination",
            trust_tier="low",
            trust_score=0.42,
        )
        gov = recorder._extra["governance"]
        assert gov["preset"] == "conservative"
        assert gov["task_type"] == "coordination"
        assert gov["trust_tier"] == "low"
        assert gov["trust_score"] == 0.42

    def test_set_governance_minimal(self, recorder):
        recorder.set_governance(preset="balanced")
        gov = recorder._extra["governance"]
        assert gov == {"preset": "balanced"}


class TestBuild:
    def test_build_returns_trajectory(self, recorder):
        recorder.record_system_step("sys")
        recorder.record_user_step("task")
        recorder.record_agent_step(response_text="done", tokens_in=100, tokens_out=50)
        trajectory = recorder.build()

        assert trajectory.schema_version == SCHEMA_VERSION
        assert trajectory.session_id == recorder._session_id
        assert trajectory.agent.name == "DevOps Engineer"
        assert trajectory.agent.version == HARNESS_VERSION
        assert len(trajectory.steps) == 3
        assert trajectory.final_metrics.total_steps == 3
        assert trajectory.final_metrics.total_prompt_tokens == 100
        assert trajectory.final_metrics.total_completion_tokens == 50

    def test_build_empty_adds_placeholder(self, recorder):
        trajectory = recorder.build()
        assert len(trajectory.steps) == 1
        assert "no execution steps" in trajectory.steps[0].message

    def test_to_dict_serializable(self, recorder):
        recorder.record_system_step("sys")
        recorder.record_user_step("task")
        recorder.record_agent_step(
            response_text="ok",
            tokens_in=50,
            tokens_out=25,
            reasoning="think",
            tool_calls=[
                {
                    "tool_call_id": "tc-1",
                    "function_name": "Bash",
                    "arguments": {"command": "echo hi"},
                }
            ],
            tool_results=[{"source_call_id": "tc-1", "content": "hi"}],
        )
        recorder.set_governance(preset="balanced", task_type="stateless")

        d = recorder.to_dict()

        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert json_str
        parsed = json.loads(json_str)

        assert parsed["schema_version"] == SCHEMA_VERSION
        assert parsed["agent"]["name"] == "DevOps Engineer"
        assert len(parsed["steps"]) == 3
        assert parsed["extra"]["governance"]["preset"] == "balanced"
        assert parsed["final_metrics"]["total_steps"] == 3

    def test_build_with_cost(self, recorder):
        recorder.record_agent_step(response_text="done", cost_usd=0.05)
        trajectory = recorder.build()
        assert trajectory.final_metrics.total_cost_usd == 0.05

    def test_build_excludes_none_tokens(self, recorder):
        recorder.record_agent_step(response_text="done")
        d = recorder.to_dict()
        # 0 tokens should be excluded (None in final_metrics)
        assert "total_prompt_tokens" not in d["final_metrics"]


class TestFullWorkflow:
    """End-to-end test mirroring how TaskWorker would use the recorder."""

    def test_task_execution_trajectory(self):
        recorder = TrajectoryRecorder(
            agent_id="agent-devops-01",
            agent_name="DevOps Engineer",
            model_name="claude-sonnet-4-20250514",
            task_id="task-deploy-001",
            tenant_id="tenant-acme",
            org_id="org-acme-prod",
        )

        # 1. System prompt
        recorder.record_system_step("You are DevOps Engineer, a deployment specialist.")

        # 2. Task submission
        recorder.record_user_step(
            "Deploy the staging environment with the latest build."
        )

        # 3. Governance selection
        recorder.set_governance(
            preset="balanced",
            task_type="pipeline",
            trust_tier="medium",
            trust_score=0.72,
        )

        # 4. Agent response
        recorder.record_agent_step(
            response_text="Deployment initiated. Staging environment "
            "updated to build v2.3.1.",
            tokens_in=1200,
            tokens_out=350,
            reasoning="Need to check the build artifact first, "
            "then run the deploy script.",
            cost_usd=0.0042,
        )

        # 5. Build
        trajectory = recorder.build()

        assert trajectory.schema_version == SCHEMA_VERSION
        assert len(trajectory.steps) == 3
        assert trajectory.final_metrics.total_prompt_tokens == 1200
        assert trajectory.final_metrics.total_completion_tokens == 350
        assert trajectory.final_metrics.total_cost_usd == 0.0042
        assert trajectory.extra["governance"]["preset"] == "balanced"
        assert trajectory.extra["task_id"] == "task-deploy-001"

        # Verify JSON round-trip
        d = recorder.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0
