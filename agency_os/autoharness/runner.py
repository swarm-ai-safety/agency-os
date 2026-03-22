"""Harness runner — the closed-loop: generate → run → score → promote/demote."""

from __future__ import annotations

import logging
import time

from agency_os.agents.business_agent import BusinessAgent
from agency_os.autoharness.evaluator import evaluate
from agency_os.autoharness.generator import generate_challenges
from agency_os.autoharness.models import (
    Challenge,
    ChallengeResult,
    EvalVerdict,
    HarnessConfig,
    HarnessReport,
    LeaderboardEntry,
)
from agency_os.metering.collector import MeteringCollector, TaskOutcome

logger = logging.getLogger(__name__)


def _execute_challenge(
    agent: BusinessAgent,
    challenge: Challenge,
) -> ChallengeResult:
    """Execute a single challenge against an agent and evaluate the result."""
    start = time.monotonic()
    result = agent.execute_task(challenge.description)
    duration = time.monotonic() - start

    response = result.get("response", "")
    tokens_in = result.get("tokens_in", 0)
    tokens_out = result.get("tokens_out", 0)

    # If execution itself failed (frozen, permission denied, LLM error),
    # treat it as an automatic FAIL
    if not result.get("success", False):
        return ChallengeResult(
            challenge_id=challenge.challenge_id,
            agent_id=agent.agent_id,
            verdict=EvalVerdict.FAIL,
            weighted_score=0.0,
            criterion_scores=dict.fromkeys(challenge.rubric.criteria, 0.0),
            response=response,
            reasoning=f"Execution failed: {result.get('error', 'unknown error')}",
            duration_sec=duration,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    return evaluate(
        challenge=challenge,
        agent_id=agent.agent_id,
        response=response,
        duration_sec=duration,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


def _apply_reputation_delta(
    agent: BusinessAgent,
    verdict: EvalVerdict,
    config: HarnessConfig,
) -> float:
    """Apply reputation change based on eval verdict. Returns the delta."""
    delta_map = {
        EvalVerdict.PASS: config.reputation_reward,
        EvalVerdict.PARTIAL: config.reputation_partial,
        EvalVerdict.FAIL: config.reputation_penalty,
    }
    delta = delta_map[verdict]
    success = verdict != EvalVerdict.FAIL
    agent.record_task_outcome(
        success=success,
        reputation_delta=delta,
        freeze_threshold=config.freeze_on_consecutive_fails,
    )
    return delta


def _record_to_metering(
    collector: MeteringCollector,
    agent: BusinessAgent,
    result: ChallengeResult,
    tenant_id: str,
    org_id: str,
) -> None:
    """Push challenge result into the metering system."""
    outcome_map = {
        EvalVerdict.PASS: TaskOutcome.success,
        EvalVerdict.PARTIAL: TaskOutcome.partial,
        EvalVerdict.FAIL: TaskOutcome.failure,
    }
    # Record token usage
    if result.tokens_in or result.tokens_out:
        collector.record_llm_call(
            tenant_id=tenant_id,
            org_id=org_id,
            agent_id=agent.agent_id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
        )
    # Record task outcome
    collector.record_task_outcome(
        tenant_id=tenant_id,
        org_id=org_id,
        agent_id=agent.agent_id,
        outcome=outcome_map[result.verdict],
        task_id=result.challenge_id,
        duration_sec=result.duration_sec,
    )


def _build_leaderboard_entry(
    agent: BusinessAgent,
    results: list[ChallengeResult],
    rep_before: float,
) -> LeaderboardEntry:
    """Build a leaderboard entry from an agent's challenge results."""
    passed = sum(1 for r in results if r.verdict == EvalVerdict.PASS)
    partial = sum(1 for r in results if r.verdict == EvalVerdict.PARTIAL)
    failed = sum(1 for r in results if r.verdict == EvalVerdict.FAIL)
    total = len(results)
    avg_score = sum(r.weighted_score for r in results) / total if total else 0.0

    # Trend detection: compare first and second half
    trend = "stable"
    if total >= 4:
        mid = total // 2
        first_half = sum(r.weighted_score for r in results[:mid]) / mid
        second_half = sum(r.weighted_score for r in results[mid:]) / (total - mid)
        delta = second_half - first_half
        if delta > 0.1:
            trend = "improving"
        elif delta < -0.1:
            trend = "declining"

    rep_after = agent.reputation
    return LeaderboardEntry(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        division=agent.spec.division,
        challenges_attempted=total,
        challenges_passed=passed,
        challenges_partial=partial,
        challenges_failed=failed,
        avg_score=round(avg_score, 3),
        pass_rate=round(passed / total, 3) if total else 0.0,
        trend=trend,
        reputation_before=round(rep_before, 3),
        reputation_after=round(rep_after, 3),
        reputation_delta=round(rep_after - rep_before, 3),
    )


def run_harness(
    agents: list[BusinessAgent],
    config: HarnessConfig | None = None,
    collector: MeteringCollector | None = None,
    tenant_id: str = "autoharness",
    org_id: str = "autoharness",
    seed: int | None = None,
) -> HarnessReport:
    """Run a full AutoHarness evaluation cycle.

    Closed loop:
        1. Generate challenges tailored to each agent's domain
        2. Execute each challenge against the target agent
        3. Score the response using the rubric evaluator
        4. Apply reputation deltas (promote/demote)
        5. Optionally record results to the metering system
        6. Build leaderboard and report

    Args:
        agents: List of agents to evaluate.
        config: Harness configuration. Uses defaults if not provided.
        collector: Optional MeteringCollector for recording results.
        tenant_id: Tenant scope for metering events.
        org_id: Organization scope for metering events.
        seed: Optional random seed for reproducible challenge generation.

    Returns:
        HarnessReport with all results, leaderboard, and summary.
    """
    config = config or HarnessConfig()
    report = HarnessReport(config=config)
    run_start = time.monotonic()

    all_results: list[ChallengeResult] = []
    agent_results: dict[str, list[ChallengeResult]] = {}
    rep_snapshots: dict[str, float] = {}

    logger.info(
        f"AutoHarness run {report.run_id}: evaluating {len(agents)} agents, "
        f"{config.challenges_per_agent} challenges each"
    )

    for agent in agents:
        if agent.is_frozen:
            logger.warning(f"Skipping frozen agent {agent.agent_id}")
            continue

        rep_snapshots[agent.agent_id] = agent.reputation
        agent_seed = None if seed is None else seed + hash(agent.agent_id) % 10000

        # 1. Generate challenges
        challenges = generate_challenges(agent, config, seed=agent_seed)
        report.challenges_generated += len(challenges)

        results_for_agent: list[ChallengeResult] = []

        for challenge in challenges:
            # 2+3. Execute and score
            result = _execute_challenge(agent, challenge)
            results_for_agent.append(result)
            all_results.append(result)
            report.challenges_executed += 1

            # 4. Apply reputation delta
            _apply_reputation_delta(agent, result.verdict, config)

            # 5. Record to metering
            if config.record_to_metering and collector is not None:
                _record_to_metering(collector, agent, result, tenant_id, org_id)

            # Short-circuit if agent got frozen during eval
            if agent.is_frozen:
                logger.warning(
                    f"Agent {agent.agent_id} frozen during eval after "
                    f"{len(results_for_agent)} challenges"
                )
                break

        agent_results[agent.agent_id] = results_for_agent

    # 6. Build leaderboard
    leaderboard: list[LeaderboardEntry] = []
    for agent in agents:
        results = agent_results.get(agent.agent_id, [])
        if not results:
            continue
        entry = _build_leaderboard_entry(
            agent, results, rep_snapshots.get(agent.agent_id, 1.0)
        )
        leaderboard.append(entry)

    # Sort by avg_score descending
    leaderboard.sort(key=lambda e: e.avg_score, reverse=True)

    report.results = all_results
    report.leaderboard = leaderboard
    report.total_duration_sec = time.monotonic() - run_start

    logger.info(
        f"AutoHarness run {report.run_id} complete: "
        f"{report.challenges_executed}/{report.challenges_generated} challenges, "
        f"{len(leaderboard)} agents on leaderboard"
    )

    return report
