"""Integration tests: full org lifecycle with governance."""

import pytest

from agency_os.agents.tool_permissions import ToolPermissionDenied, enforce_permission
from agency_os.governance.presets import resolve_governance
from agency_os.orchestration.feedback_loops import FeedbackLoop, QAFeedback
from agency_os.orchestration.organization import Organization
from agency_os.orchestration.task_router import TaskRouter
from agency_os.orchestration.workflow_engine import WorkflowEngine
from agency_os.packages.loader import load_package_from_name


@pytest.fixture
def org():
    org = Organization.from_builtin("saas_dev_studio")
    org.start()
    return org


class TestFullOrgLifecycle:
    """Test: create org → submit task → agents bid → winner selected → wallet debited → reputation updated."""

    def test_task_bid_and_assignment(self, org):
        router = TaskRouter(org.agents)
        assignment = router.route("Implement user authentication")

        assert assignment.assigned_to == "engineering-senior-developer"
        assert assignment.winning_bid > 0
        assert len(assignment.bids) == 6

    def test_reputation_update(self, org):
        agent = org.get_agent("engineering-senior-developer")
        initial_rep = agent.reputation

        agent.record_task_outcome(success=True, reputation_delta=0.1)
        assert agent.reputation == pytest.approx(initial_rep + 0.1)


class TestGovernanceProfiles:
    """Test all three governance profiles resolve correctly."""

    def test_conservative_profile(self):
        from agency_os.packages.schema import GovernanceConfig

        config = GovernanceConfig(preset="conservative")
        swarm_config = resolve_governance(config)
        assert swarm_config.audit_enabled is True
        assert swarm_config.staking_enabled is True
        assert swarm_config.transaction_tax_rate == 0.10

    def test_balanced_profile(self):
        from agency_os.packages.schema import GovernanceConfig

        config = GovernanceConfig(preset="balanced")
        swarm_config = resolve_governance(config)
        assert swarm_config.circuit_breaker_enabled is True
        assert swarm_config.staking_enabled is False
        assert swarm_config.transaction_tax_rate == 0.05

    def test_aggressive_profile(self):
        from agency_os.packages.schema import GovernanceConfig

        config = GovernanceConfig(preset="aggressive")
        swarm_config = resolve_governance(config)
        assert swarm_config.audit_enabled is False
        assert swarm_config.transaction_tax_rate == 0.02
        assert swarm_config.bandwidth_cap == 20


class TestToolPermissions:
    """Test tool permission enforcement across agents."""

    def test_allowed_tool(self, org):
        dev = org.get_agent("engineering-senior-developer")
        assert dev.is_tool_allowed("code_write")

    def test_denied_tool(self, org):
        dev = org.get_agent("engineering-senior-developer")
        assert not dev.is_tool_allowed("deploy_production")

    def test_enforce_raises(self, org):
        dev = org.get_agent("engineering-senior-developer")
        with pytest.raises(ToolPermissionDenied):
            enforce_permission(dev, "deploy_production")

    def test_devops_can_deploy(self, org):
        devops = org.get_agent("engineering-devops-automator")
        assert devops.is_tool_allowed("deploy_production")


class TestWorkflowWithGates:
    """Test workflow execution with quality gate enforcement."""

    def test_full_workflow(self, org):
        spec = load_package_from_name("saas_dev_studio")
        engine = WorkflowEngine(spec.workflows)
        run = engine.create_run("feature_development")

        # plan → design (no gate)
        assert engine.advance_stage(run, approvals=1)
        # design → implement (no gate)
        assert engine.advance_stage(run, approvals=1)
        # implement → test (gate: min_approvals=1)
        assert not engine.advance_stage(run, approvals=0)  # Blocked
        assert engine.advance_stage(run, approvals=1)  # Passes
        # test → deploy (gate: min_evidence=3, min_approvals=2)
        assert not engine.advance_stage(
            run, evidence=[{"e": 1}], approvals=1
        )  # Blocked
        assert engine.advance_stage(
            run, evidence=[{"e": 1}, {"e": 2}, {"e": 3}], approvals=2
        )

    def test_feedback_loop_rework(self):
        loop = FeedbackLoop(max_iterations=3)

        # First attempt: fails
        result = loop.submit_review(
            QAFeedback(
                reviewer_id="qa-001",
                task_id="task-1",
                passed=False,
                issues=["Bug in auth"],
                iteration=1,
            )
        )
        assert result == "rework"

        # Second attempt: fails again
        result = loop.submit_review(
            QAFeedback(
                reviewer_id="qa-001",
                task_id="task-1",
                passed=False,
                issues=["Still broken"],
                iteration=2,
            )
        )
        assert result == "rework"

        # Third attempt: max iterations hit → escalate
        result = loop.submit_review(
            QAFeedback(
                reviewer_id="qa-001",
                task_id="task-1",
                passed=False,
                issues=["Not fixed"],
                iteration=3,
            )
        )
        assert result == "escalate"

    def test_feedback_loop_approval(self):
        loop = FeedbackLoop()
        result = loop.submit_review(
            QAFeedback(
                reviewer_id="qa-001",
                task_id="task-1",
                passed=True,
                iteration=1,
            )
        )
        assert result == "approved"
