"""Tests for agency_os.memory — decay, sharing, and retrieval."""

from __future__ import annotations

import yaml

from agency_os.memory.decay import (
    DecayResult,
    DecayTier,
    classify_facts,
    classify_tier,
    load_facts,
    run_decay_sweep,
    synthesize_summary,
)
from agency_os.memory.retrieval import FactIndex, recall
from agency_os.memory.sharing import (
    AgentFact,
    discover_agents,
    get_agent_facts,
    get_shared_facts,
    read_agent_memory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = 1_700_000_000.0  # fixed timestamp for deterministic tests


def _make_fact(
    fact_id: str = "f1",
    fact: str = "some fact",
    category: str = "status",
    last_accessed: float | None = None,
    access_count: int = 0,
    status: str = "active",
) -> dict:
    d: dict = {
        "id": fact_id,
        "fact": fact,
        "category": category,
        "access_count": access_count,
        "status": status,
    }
    if last_accessed is not None:
        d["last_accessed"] = last_accessed
    return d


def _setup_agent(
    tmp_path,
    agent_name: str,
    entities: dict[str, list[dict]] | None = None,
    memory_content: str = "",
):
    """Create an agent directory with optional PARA entities and MEMORY.md."""
    agent_dir = tmp_path / "agents" / agent_name
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True)
    if memory_content:
        (memory_dir / "MEMORY.md").write_text(memory_content)
    if entities:
        life_dir = agent_dir / "life"
        for entity_name, facts in entities.items():
            entity_dir = life_dir / entity_name
            entity_dir.mkdir(parents=True)
            (entity_dir / "items.yaml").write_text(yaml.dump(facts))
    return agent_dir


# ===========================================================================
# Decay tests
# ===========================================================================


class TestClassifyTier:
    def test_recent_access_is_hot(self):
        last = NOW - 3600  # 1 hour ago
        assert classify_tier(last, 0, now=NOW) == DecayTier.hot

    def test_week_old_is_warm(self):
        last = NOW - 10 * 86400  # 10 days ago
        assert classify_tier(last, 0, now=NOW) == DecayTier.warm

    def test_month_old_is_cold(self):
        last = NOW - 60 * 86400  # 60 days ago
        assert classify_tier(last, 0, now=NOW) == DecayTier.cold

    def test_never_accessed_is_cold(self):
        assert classify_tier(None, 0, now=NOW) == DecayTier.cold

    def test_high_access_resists_cold_to_warm(self):
        last = NOW - 60 * 86400
        assert classify_tier(last, 10, now=NOW) == DecayTier.warm

    def test_high_access_resists_warm_to_hot(self):
        last = NOW - 10 * 86400
        assert classify_tier(last, 15, now=NOW) == DecayTier.hot

    def test_high_access_does_not_exceed_hot(self):
        last = NOW - 3600
        assert classify_tier(last, 100, now=NOW) == DecayTier.hot

    def test_access_count_below_threshold_no_resist(self):
        last = NOW - 60 * 86400
        assert classify_tier(last, 9, now=NOW) == DecayTier.cold


class TestClassifyFacts:
    def test_superseded_facts_excluded(self):
        facts = [_make_fact(status="superseded", last_accessed=NOW)]
        assert classify_facts(facts, now=NOW) == []

    def test_active_facts_classified(self):
        facts = [
            _make_fact("f1", "hot fact", last_accessed=NOW - 100),
            _make_fact("f2", "cold fact", last_accessed=NOW - 90 * 86400),
        ]
        results = classify_facts(facts, now=NOW)
        assert len(results) == 2
        assert results[0].tier == DecayTier.hot
        assert results[1].tier == DecayTier.cold


class TestLoadFacts:
    def test_load_valid_yaml(self, tmp_path):
        items = tmp_path / "items.yaml"
        facts = [_make_fact("f1", "test")]
        items.write_text(yaml.dump(facts))
        loaded = load_facts(items)
        assert len(loaded) == 1
        assert loaded[0]["fact"] == "test"

    def test_load_missing_file(self, tmp_path):
        assert load_facts(tmp_path / "nope.yaml") == []

    def test_load_empty_file(self, tmp_path):
        items = tmp_path / "items.yaml"
        items.write_text("")
        assert load_facts(items) == []


class TestSynthesizeSummary:
    def test_summary_groups_by_tier(self):
        facts = [
            DecayResult("f1", "hot fact", DecayTier.hot, NOW, 5, "status", "active"),
            DecayResult(
                "f2",
                "warm fact",
                DecayTier.warm,
                NOW - 15 * 86400,
                2,
                "status",
                "active",
            ),
            DecayResult("f3", "cold fact", DecayTier.cold, None, 0, "status", "active"),
        ]
        summary = synthesize_summary(facts, entity_name="TestEntity")
        assert "# TestEntity" in summary
        assert "## Hot (1)" in summary
        assert "## Warm (1)" in summary
        assert "cold fact" not in summary  # cold excluded by default

    def test_summary_includes_cold_when_requested(self):
        facts = [
            DecayResult("f1", "cold fact", DecayTier.cold, None, 0, "status", "active"),
        ]
        summary = synthesize_summary(facts, include_cold=True)
        assert "cold fact" in summary

    def test_summary_sorted_by_access_count(self):
        facts = [
            DecayResult("f1", "low access", DecayTier.hot, NOW, 1, "status", "active"),
            DecayResult(
                "f2", "high access", DecayTier.hot, NOW, 10, "status", "active"
            ),
        ]
        summary = synthesize_summary(facts)
        # high access should appear first
        assert summary.index("high access") < summary.index("low access")


class TestRunDecaySweep:
    def test_sweep_processes_entities(self, tmp_path):
        agent_home = tmp_path / "agent"
        life_dir = agent_home / "life" / "projects" / "agency-os"
        life_dir.mkdir(parents=True)
        facts = [
            _make_fact("f1", "project fact", last_accessed=NOW - 100),
        ]
        (life_dir / "items.yaml").write_text(yaml.dump(facts))

        results = run_decay_sweep(agent_home, now=NOW, write=True)
        assert len(results) == 1
        key = list(results.keys())[0]
        assert results[key][0].tier == DecayTier.hot
        # summary.md should be written
        assert (life_dir / "summary.md").exists()

    def test_sweep_no_life_dir(self, tmp_path):
        results = run_decay_sweep(tmp_path / "nope", now=NOW)
        assert results == {}


# ===========================================================================
# Sharing tests
# ===========================================================================


class TestDiscoverAgents:
    def test_finds_agents_with_memory(self, tmp_path):
        _setup_agent(tmp_path, "ceo")
        _setup_agent(tmp_path, "engineer")
        agents = discover_agents(tmp_path / "agents")
        assert agents == ["ceo", "engineer"]

    def test_skips_dirs_without_memory(self, tmp_path):
        (tmp_path / "agents" / "no-memory").mkdir(parents=True)
        _setup_agent(tmp_path, "ceo")
        assert discover_agents(tmp_path / "agents") == ["ceo"]

    def test_empty_dir(self, tmp_path):
        assert discover_agents(tmp_path / "nope") == []


class TestGetAgentFacts:
    def test_returns_classified_facts(self, tmp_path):
        _setup_agent(
            tmp_path,
            "ceo",
            entities={
                "company": [
                    _make_fact("f1", "company is growing", last_accessed=NOW - 100),
                ]
            },
        )
        facts = get_agent_facts(tmp_path / "agents", "ceo", now=NOW)
        assert len(facts) == 1
        assert facts[0].agent == "ceo"
        assert facts[0].entity == "company"
        assert facts[0].tier == DecayTier.hot

    def test_no_life_dir(self, tmp_path):
        _setup_agent(tmp_path, "ceo")
        assert get_agent_facts(tmp_path / "agents", "ceo") == []


class TestGetSharedFacts:
    def test_excludes_requesting_agent(self, tmp_path):
        _setup_agent(
            tmp_path,
            "ceo",
            entities={"co": [_make_fact("f1", "ceo fact", last_accessed=NOW - 100)]},
        )
        _setup_agent(
            tmp_path,
            "engineer",
            entities={"co": [_make_fact("f2", "eng fact", last_accessed=NOW - 100)]},
        )
        facts = get_shared_facts(
            tmp_path / "agents",
            exclude_agent="ceo",
            now=NOW,
        )
        assert all(f.agent != "ceo" for f in facts)
        assert len(facts) == 1
        assert facts[0].agent == "engineer"

    def test_filters_by_tier(self, tmp_path):
        _setup_agent(
            tmp_path,
            "ceo",
            entities={
                "co": [
                    _make_fact("f1", "hot", last_accessed=NOW - 100),
                    _make_fact("f2", "cold", last_accessed=NOW - 90 * 86400),
                ]
            },
        )
        hot_only = get_shared_facts(
            tmp_path / "agents",
            tier_filter={DecayTier.hot},
            now=NOW,
        )
        assert len(hot_only) == 1
        assert hot_only[0].fact == "hot"


class TestReadAgentMemory:
    def test_reads_memory_file(self, tmp_path):
        _setup_agent(tmp_path, "ceo", memory_content="# CEO Memory\nStuff here")
        content = read_agent_memory(tmp_path / "agents", "ceo")
        assert content is not None
        assert "CEO Memory" in content

    def test_returns_none_for_missing(self, tmp_path):
        _setup_agent(tmp_path, "ceo")
        assert read_agent_memory(tmp_path / "agents", "ceo") is None


# ===========================================================================
# Retrieval tests
# ===========================================================================


class TestFactIndex:
    def _make_agent_fact(self, fact: str, entity: str = "co", agent: str = "ceo"):
        return AgentFact(
            agent=agent,
            entity=entity,
            fact_id="f1",
            fact=fact,
            category="status",
            tier=DecayTier.hot,
            access_count=5,
        )

    def test_search_returns_matching_facts(self):
        idx = FactIndex()
        idx.build(
            [
                self._make_agent_fact("the company uses Python"),
                self._make_agent_fact("the agent runs on Linux"),
                self._make_agent_fact("Python is the primary language"),
            ]
        )
        results = idx.search("Python language")
        assert len(results) >= 1
        # The fact with both "python" and "language" should score highest
        assert (
            "python" in results[0].fact.fact.lower()
            or "language" in results[0].fact.fact.lower()
        )

    def test_search_no_match(self):
        idx = FactIndex()
        idx.build([self._make_agent_fact("hello world")])
        results = idx.search("quantum physics")
        assert results == []

    def test_search_empty_index(self):
        idx = FactIndex()
        idx.build([])
        assert idx.search("anything") == []

    def test_search_respects_limit(self):
        idx = FactIndex()
        idx.build(
            [self._make_agent_fact(f"fact about Python number {i}") for i in range(20)]
        )
        results = idx.search("Python", limit=5)
        assert len(results) == 5

    def test_matched_terms_populated(self):
        idx = FactIndex()
        idx.build([self._make_agent_fact("Python is great")])
        results = idx.search("Python")
        assert "python" in results[0].matched_terms


class TestRecall:
    def test_recall_across_agents(self, tmp_path):
        _setup_agent(
            tmp_path,
            "ceo",
            entities={
                "company": [
                    _make_fact("f1", "company uses FastAPI", last_accessed=NOW - 100),
                ]
            },
        )
        _setup_agent(
            tmp_path,
            "engineer",
            entities={
                "code": [
                    _make_fact(
                        "f2", "codebase is Python FastAPI", last_accessed=NOW - 100
                    ),
                ]
            },
        )
        results = recall("FastAPI", tmp_path / "agents", now=NOW)
        assert len(results) == 2
        agents = {r.fact.agent for r in results}
        assert agents == {"ceo", "engineer"}

    def test_recall_empty(self, tmp_path):
        assert recall("anything", tmp_path / "agents") == []

    def test_recall_specific_agents(self, tmp_path):
        _setup_agent(
            tmp_path,
            "ceo",
            entities={"co": [_make_fact("f1", "CEO stuff", last_accessed=NOW - 100)]},
        )
        _setup_agent(
            tmp_path,
            "engineer",
            entities={"co": [_make_fact("f2", "eng stuff", last_accessed=NOW - 100)]},
        )
        results = recall("stuff", tmp_path / "agents", agent_names=["ceo"], now=NOW)
        assert len(results) == 1
        assert results[0].fact.agent == "ceo"
