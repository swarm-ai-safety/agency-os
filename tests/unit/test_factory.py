"""Tests for agency_os.agents.agent_factory."""

from pathlib import Path

import pytest

from agency_os.agents.agent_factory import AgentFactory
from agency_os.agents.registry import AgentRegistry
from agency_os.packages.schema import AgentRef, BidStrategy, DeploymentConfig

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)


@pytest.fixture
def registry():
    reg = AgentRegistry(specs_root=FIXTURES_DIR)
    reg.load()
    return reg


@pytest.fixture
def factory(registry):
    return AgentFactory(registry, DeploymentConfig())


class TestAgentFactory:
    def test_create_single_agent(self, factory):
        ref = AgentRef(ref="engineering/senior-developer")
        agent = factory.create_agent(ref)
        assert agent.agent_id == "engineering-senior-developer"
        assert agent.spec.slug == "engineering/senior-developer"

    def test_create_with_count(self, factory):
        ref = AgentRef(ref="engineering/senior-developer", count=3)
        agents = factory.create_agents([ref])
        assert len(agents) == 3
        ids = {a.agent_id for a in agents}
        assert "engineering-senior-developer-0" in ids
        assert "engineering-senior-developer-1" in ids
        assert "engineering-senior-developer-2" in ids

    def test_create_with_overrides(self, factory):
        ref = AgentRef(
            ref="engineering/senior-developer",
            role_override={"title": "CTO"},
            economic={"initial_balance": 5000, "bid_strategy": "quality_weighted"},
        )
        agent = factory.create_agent(ref)
        assert agent.name == "CTO"
        assert agent.balance == 5000.0
        assert agent.economic.bid_strategy == BidStrategy.QUALITY_WEIGHTED

    def test_create_missing_ref(self, factory):
        ref = AgentRef(ref="nonexistent/agent")
        with pytest.raises(KeyError):
            factory.create_agent(ref)

    def test_create_all_package_agents(self, factory):
        from agency_os.packages.loader import load_package_from_name

        spec = load_package_from_name("saas_dev_studio")
        agents = factory.create_agents(spec.agents)
        assert len(agents) == 6
