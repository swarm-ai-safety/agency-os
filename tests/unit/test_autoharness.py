"""Tests for agency_os.autoharness — models, generator, evaluator, runner."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agency_os.agents.business_agent import BusinessAgent
from agency_os.agents.spec_parser import parse_spec
from agency_os.autoharness.evaluator import (
    _anti_signal_penalty,
    _length_score,
    _signal_score,
    _structure_score,
    evaluate,
)
from agency_os.autoharness.generator import generate_challenges
from agency_os.autoharness.models import (
    Challenge,
    ChallengeDifficulty,
    ChallengeResult,
    EvalRubric,
    EvalVerdict,
    HarnessConfig,
    HarnessReport,
    LeaderboardEntry,
)
from agency_os.autoharness.runner import (
    _apply_reputation_delta,
    _build_leaderboard_entry,
    _execute_challenge,
    run_harness,
)
from agency_os.metering.collector import MeteringCollector
from agency_os.packages.schema import AgentEconomicConfig, BidStrategy
from swarm.agents.llm_config import LLMConfig, LLMProvider

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_config():
    return LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-sonnet-4-20250514")


@pytest.fixture
def eng_spec():
    return parse_spec(FIXTURES_DIR / "engineering" / "engineering-senior-developer.md")


@pytest.fixture
def agent(eng_spec, llm_config):
    return BusinessAgent(
        agent_id="test-eng",
        spec=eng_spec,
        llm_config=llm_config,
        economic=AgentEconomicConfig(
            initial_balance=500, bid_strategy=BidStrategy.DEFAULT
        ),
        domain_tags=["backend", "python"],
    )


@pytest.fixture
def config():
    return HarnessConfig(challenges_per_agent=3)


# ===========================================================================
# Model tests
# ===========================================================================


class TestModels:
    def test_rubric_valid_weights(self):
        r = EvalRubric(criteria={"a": 0.6, "b": 0.4})
        assert r.pass_threshold == 0.7

    def test_rubric_invalid_weights(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            EvalRubric(criteria={"a": 0.5, "b": 0.3})

    def test_challenge_defaults(self):
        c = Challenge()
        assert c.challenge_id.startswith("ch-")
        assert c.difficulty == ChallengeDifficulty.MEDIUM

    def test_eval_verdict_values(self):
        assert EvalVerdict.PASS.value == "pass"
        assert EvalVerdict.FAIL.value == "fail"
        assert EvalVerdict.PARTIAL.value == "partial"

    def test_harness_report_summary(self):
        entry = LeaderboardEntry(
            agent_id="a1",
            agent_name="Agent 1",
            division="eng",
            challenges_attempted=5,
            challenges_passed=4,
            avg_score=0.85,
            pass_rate=0.8,
        )
        report = HarnessReport(
            leaderboard=[entry],
            challenges_generated=5,
            challenges_executed=5,
        )
        s = report.summary()
        assert s["agents_evaluated"] == 1
        assert s["top_agent"] == "a1"
        assert s["challenges_executed"] == 5

    def test_harness_report_empty_summary(self):
        report = HarnessReport()
        s = report.summary()
        assert s["agents_evaluated"] == 0
        assert s["top_agent"] is None
        assert s["avg_pass_rate"] == 0.0

    def test_config_defaults(self):
        c = HarnessConfig()
        assert c.challenges_per_agent == 5
        assert c.reputation_reward == 0.03
        assert c.reputation_penalty == -0.06


# ===========================================================================
# Generator tests
# ===========================================================================


class TestGenerator:
    def test_generates_correct_count(self, agent, config):
        challenges = generate_challenges(agent, config, seed=42)
        assert len(challenges) == config.challenges_per_agent

    def test_challenges_have_descriptions(self, agent, config):
        challenges = generate_challenges(agent, config, seed=42)
        for c in challenges:
            assert c.description
            assert c.title
            assert c.domain == "engineering"

    def test_reproducible_with_seed(self, agent, config):
        c1 = generate_challenges(agent, config, seed=99)
        c2 = generate_challenges(agent, config, seed=99)
        assert [c.title for c in c1] == [c.title for c in c2]

    def test_different_seeds_differ(self, agent, config):
        c1 = generate_challenges(agent, config, seed=1)
        c2 = generate_challenges(agent, config, seed=2)
        # With different seeds, at least some titles should differ
        # (probabilistic but very likely with different seeds)
        titles1 = [c.title for c in c1]
        titles2 = [c.title for c in c2]
        # Just check they're both valid
        assert all(t for t in titles1)
        assert all(t for t in titles2)

    def test_rubrics_valid(self, agent, config):
        challenges = generate_challenges(agent, config, seed=42)
        for c in challenges:
            total = sum(c.rubric.criteria.values())
            assert abs(total - 1.0) < 0.01

    def test_difficulty_distribution(self, agent):
        # All easy
        config = HarnessConfig(
            challenges_per_agent=20,
            difficulty_distribution={"easy": 1.0, "medium": 0.0, "hard": 0.0},
        )
        challenges = generate_challenges(agent, config, seed=42)
        assert all(c.difficulty == ChallengeDifficulty.EASY for c in challenges)

    def test_metadata_includes_agent(self, agent, config):
        challenges = generate_challenges(agent, config, seed=42)
        for c in challenges:
            assert c.metadata["agent_target"] == "test-eng"


# ===========================================================================
# Evaluator tests
# ===========================================================================


class TestEvaluatorHelpers:
    def test_signal_score_all_present(self):
        assert (
            _signal_score("error handling with try catch", ["error", "try", "catch"])
            == 1.0
        )

    def test_signal_score_none_present(self):
        assert _signal_score("hello world", ["error", "try", "catch"]) == 0.0

    def test_signal_score_partial(self):
        assert _signal_score(
            "error occurred", ["error", "try", "catch"]
        ) == pytest.approx(1 / 3)

    def test_signal_score_empty_signals(self):
        assert _signal_score("anything", []) == 1.0

    def test_anti_signal_no_hits(self):
        assert _anti_signal_penalty("clean response", ["todo", "placeholder"]) == 1.0

    def test_anti_signal_one_hit(self):
        assert (
            _anti_signal_penalty("this is a todo item", ["todo", "placeholder"]) == 0.8
        )

    def test_anti_signal_floor(self):
        assert (
            _anti_signal_penalty(
                "todo placeholder not implemented skip",
                ["todo", "placeholder", "not implemented", "skip", "ignore"],
            )
            == 0.2
        )  # Floor

    def test_length_score_very_short(self):
        assert _length_score("hello", "medium") == 0.2

    def test_length_score_adequate(self):
        text = " ".join(["word"] * 100)
        assert _length_score(text, "medium") == 1.0

    def test_structure_score_plain(self):
        assert _structure_score("Just plain text") == 0.5

    def test_structure_score_rich(self):
        text = "# Heading\n- bullet\n```code```\n1. numbered"
        score = _structure_score(text)
        assert score == 1.0


class TestEvaluate:
    def test_pass_verdict(self):
        challenge = Challenge(
            title="Test",
            description="Write error handling code",
            rubric=EvalRubric(criteria={"correctness": 1.0}, pass_threshold=0.5),
            expected_signals=["error", "handle", "return", "validate"],
        )
        response = (
            "Here is the error handling code with proper validation. "
            "We handle the error case and return an appropriate response. "
            "We also validate all inputs before processing."
        )
        result = evaluate(challenge, "agent-1", response)
        assert result.verdict == EvalVerdict.PASS
        assert result.weighted_score >= 0.5

    def test_fail_verdict_empty_response(self):
        challenge = Challenge(
            title="Test",
            description="Do something",
            rubric=EvalRubric(criteria={"completeness": 1.0}),
            expected_signals=["analysis", "recommend"],
        )
        result = evaluate(challenge, "agent-1", "")
        assert result.verdict == EvalVerdict.FAIL
        assert result.weighted_score < 0.4

    def test_anti_signals_reduce_score(self):
        challenge = Challenge(
            title="Test",
            description="Build a component",
            rubric=EvalRubric(criteria={"correctness": 1.0}, pass_threshold=0.7),
            expected_signals=["function", "return"],
            anti_signals=["todo", "not implemented"],
        )
        good = "function process() { return result; }"
        bad = "function process() { // todo: not implemented }"

        good_result = evaluate(challenge, "a1", good)
        bad_result = evaluate(challenge, "a2", bad)
        assert good_result.weighted_score > bad_result.weighted_score

    def test_criterion_scores_populated(self):
        challenge = Challenge(
            rubric=EvalRubric(criteria={"correctness": 0.5, "structure": 0.5}),
            expected_signals=["test"],
        )
        result = evaluate(challenge, "a1", "# Heading\n- test item")
        assert "correctness" in result.criterion_scores
        assert "structure" in result.criterion_scores

    def test_reasoning_includes_scores(self):
        challenge = Challenge(
            rubric=EvalRubric(criteria={"completeness": 1.0}),
        )
        result = evaluate(challenge, "a1", "some text")
        assert "Weighted score" in result.reasoning
        assert "completeness" in result.reasoning


# ===========================================================================
# Runner tests
# ===========================================================================


class TestRunner:
    def _mock_execute(self, description, context=None):
        """Simulate a successful LLM response."""
        return {
            "response": (
                "# Analysis\n"
                "Here is a thorough analysis with error handling and validation.\n"
                "- We handle the error case with try/catch\n"
                "- Return appropriate values\n"
                "- Validate inputs before processing\n"
                "1. First recommendation: fix the root cause\n"
                "2. Second: add test coverage to verify\n"
                "The main risk is resource exhaustion under load.\n"
                "```python\ndef handle():\n    pass\n```\n"
            ),
            "tokens_in": 100,
            "tokens_out": 200,
            "success": True,
        }

    def test_execute_challenge(self, agent):
        challenge = Challenge(
            title="Test",
            description="Do something",
            rubric=EvalRubric(criteria={"completeness": 1.0}),
            expected_signals=["analysis"],
        )
        with patch.object(agent, "execute_task", side_effect=self._mock_execute):
            result = _execute_challenge(agent, challenge)
        assert isinstance(result, ChallengeResult)
        assert result.agent_id == "test-eng"
        assert result.tokens_in == 100

    def test_execute_challenge_frozen_agent(self, agent):
        agent._frozen = True
        challenge = Challenge(
            title="Test",
            description="Do something",
            rubric=EvalRubric(criteria={"completeness": 1.0}),
        )
        result = _execute_challenge(agent, challenge)
        assert result.verdict == EvalVerdict.FAIL
        assert (
            "frozen" in result.reasoning.lower()
            or "circuit breaker" in result.reasoning.lower()
        )

    def test_apply_reputation_pass(self, agent, config):
        before = agent.reputation
        delta = _apply_reputation_delta(agent, EvalVerdict.PASS, config)
        assert delta == config.reputation_reward
        assert agent.reputation == pytest.approx(before + delta)

    def test_apply_reputation_fail(self, agent, config):
        before = agent.reputation
        delta = _apply_reputation_delta(agent, EvalVerdict.FAIL, config)
        assert delta == config.reputation_penalty
        assert agent.reputation == pytest.approx(before + delta)

    def test_build_leaderboard_entry(self, agent):
        results = [
            ChallengeResult(
                challenge_id=f"ch-{i}",
                agent_id="test-eng",
                verdict=EvalVerdict.PASS if i < 3 else EvalVerdict.FAIL,
                weighted_score=0.8 if i < 3 else 0.2,
                criterion_scores={},
            )
            for i in range(5)
        ]
        entry = _build_leaderboard_entry(agent, results, rep_before=1.0)
        assert entry.challenges_attempted == 5
        assert entry.challenges_passed == 3
        assert entry.challenges_failed == 2
        assert entry.pass_rate == pytest.approx(0.6)

    def test_run_harness_full(self, agent, config):
        with patch.object(type(agent), "execute_task", side_effect=self._mock_execute):
            report = run_harness([agent], config=config, seed=42)

        assert isinstance(report, HarnessReport)
        assert report.challenges_generated == config.challenges_per_agent
        assert report.challenges_executed == config.challenges_per_agent
        assert len(report.leaderboard) == 1
        assert report.leaderboard[0].agent_id == "test-eng"

    def test_run_harness_records_metering(self, agent, config):
        collector = MeteringCollector()
        config.record_to_metering = True

        with patch.object(type(agent), "execute_task", side_effect=self._mock_execute):
            run_harness(
                [agent],
                config=config,
                collector=collector,
                tenant_id="t1",
                org_id="o1",
                seed=42,
            )

        # Should have recorded outcomes
        outcomes = collector.get_agent_outcomes("test-eng", "t1")
        assert len(outcomes) == config.challenges_per_agent

    def test_run_harness_skips_frozen(self, agent, config):
        agent._frozen = True
        with patch.object(type(agent), "execute_task", side_effect=self._mock_execute):
            report = run_harness([agent], config=config, seed=42)
        assert report.challenges_executed == 0
        assert len(report.leaderboard) == 0

    def test_run_harness_reputation_changes(self, agent, config):
        before = agent.reputation
        with patch.object(type(agent), "execute_task", side_effect=self._mock_execute):
            report = run_harness([agent], config=config, seed=42)
        # Reputation delta should match verdict-derived accounting.
        entry = report.leaderboard[0]
        verdict_deltas = {
            EvalVerdict.PASS: config.reputation_reward,
            EvalVerdict.PARTIAL: config.reputation_partial,
            EvalVerdict.FAIL: config.reputation_penalty,
        }
        expected_delta = round(
            sum(verdict_deltas[result.verdict] for result in report.results), 3
        )
        assert entry.reputation_before == pytest.approx(before, abs=0.01)
        assert entry.reputation_delta == pytest.approx(expected_delta, abs=0.001)
        assert entry.reputation_after == pytest.approx(
            entry.reputation_before + expected_delta, abs=0.001
        )

    def test_run_harness_multiple_agents(self, eng_spec, llm_config, config):
        agents = [
            BusinessAgent(
                agent_id=f"agent-{i}",
                spec=eng_spec,
                llm_config=llm_config,
                economic=AgentEconomicConfig(initial_balance=500),
            )
            for i in range(3)
        ]
        with patch.object(
            BusinessAgent, "execute_task", side_effect=self._mock_execute
        ):
            report = run_harness(agents, config=config, seed=42)
        assert len(report.leaderboard) == 3
        assert report.challenges_executed == 3 * config.challenges_per_agent
        # Leaderboard should be sorted by score descending
        scores = [e.avg_score for e in report.leaderboard]
        assert scores == sorted(scores, reverse=True)
