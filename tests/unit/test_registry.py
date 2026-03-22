"""Tests for agency_os.agents.registry."""

from pathlib import Path

import pytest

from agency_os.agents.registry import AgentRegistry

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)


@pytest.fixture
def registry():
    reg = AgentRegistry(specs_root=FIXTURES_DIR)
    reg.load()
    return reg


class TestAgentRegistry:
    def test_load_discovers_agents(self, registry):
        assert registry.count >= 50  # At least 50 agents

    def test_divisions(self, registry):
        divs = registry.divisions()
        assert "engineering" in divs
        assert "testing" in divs
        assert "marketing" in divs
        assert len(divs) >= 9

    def test_get_existing(self, registry):
        spec = registry.get("engineering/senior-developer")
        assert spec is not None
        assert spec.name == "Senior Developer"

    def test_get_missing(self, registry):
        assert registry.get("nonexistent/agent") is None

    def test_get_or_raise(self, registry):
        with pytest.raises(KeyError, match="nonexistent"):
            registry.get_or_raise("nonexistent/agent")

    def test_list_division(self, registry):
        eng = registry.list_division("engineering")
        assert len(eng) >= 5
        slugs = [s.slug for s in eng]
        assert "engineering/senior-developer" in slugs

    def test_search(self, registry):
        results = registry.search("developer")
        assert len(results) >= 2
        names = [s.name for s in results]
        assert "Senior Developer" in names

    def test_lazy_load(self):
        reg = AgentRegistry(specs_root=FIXTURES_DIR)
        # Should auto-load on first access
        assert reg.count >= 50

    def test_missing_dir(self):
        reg = AgentRegistry(specs_root=Path("/nonexistent"))
        with pytest.raises(FileNotFoundError):
            reg.load()
