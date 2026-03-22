"""Tests for agency_os.agents.business_agent."""

from pathlib import Path

import pytest

from agency_os.agents.business_agent import BusinessAgent
from agency_os.agents.spec_parser import parse_spec
from agency_os.packages.schema import AgentEconomicConfig, AgentPermissions, BidStrategy
from swarm.agents.llm_config import LLMConfig, LLMProvider

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)


@pytest.fixture
def sample_spec():
    return parse_spec(FIXTURES_DIR / "engineering" / "engineering-senior-developer.md")


@pytest.fixture
def llm_config():
    return LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-sonnet-4-20250514")


@pytest.fixture
def agent(sample_spec, llm_config):
    return BusinessAgent(
        agent_id="test-dev",
        spec=sample_spec,
        llm_config=llm_config,
        economic=AgentEconomicConfig(
            initial_balance=1000, bid_strategy=BidStrategy.QUALITY_WEIGHTED
        ),
        permissions=AgentPermissions(
            tools=["code_write", "code_review"], deny=["deploy_production"]
        ),
        role_override={"title": "Tech Lead"},
    )


class TestBusinessAgent:
    def test_init(self, agent):
        assert agent.agent_id == "test-dev"
        assert agent.name == "Tech Lead"
        assert agent.balance == 1000.0
        assert agent.reputation == 1.0

    def test_wallet_operations(self, agent):
        agent.credit(500)
        assert agent.balance == 1500.0

        assert agent.debit(200) is True
        assert agent.balance == 1300.0

        assert agent.debit(5000) is False  # Insufficient
        assert agent.balance == 1300.0  # Unchanged

    def test_reputation(self, agent):
        agent.record_task_outcome(success=True, reputation_delta=0.1)
        assert agent.reputation == pytest.approx(1.1)

        agent.record_task_outcome(success=False, reputation_delta=-0.3)
        assert agent.reputation == pytest.approx(0.8)

    def test_reputation_bounds(self, agent):
        agent.record_task_outcome(success=True, reputation_delta=5.0)
        assert agent.reputation == 2.0  # Capped at 2.0

        agent.record_task_outcome(success=False, reputation_delta=-10.0)
        assert agent.reputation == 0.0  # Floored at 0.0

    def test_bid_quality_weighted(self, agent):
        bid = agent.compute_bid("task")
        # 1000 * 0.1 * 1.0 (reputation) = 100
        assert bid == pytest.approx(100.0)

    def test_tool_permissions(self, agent):
        assert agent.is_tool_allowed("code_write") is True
        assert agent.is_tool_allowed("deploy_production") is False
        assert agent.is_tool_allowed("code_review") is True
        assert agent.is_tool_allowed("unknown_tool") is False  # Not in allow list

    def test_status_dict(self, agent):
        status = agent.status_dict()
        assert status["agent_id"] == "test-dev"
        assert status["balance"] == 1000.0
        assert status["bid_strategy"] == "quality_weighted"
        assert "code_write" in status["allowed_tools"]
