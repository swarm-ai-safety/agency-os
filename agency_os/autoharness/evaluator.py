"""Evaluator — scores agent responses against challenge rubrics."""

from __future__ import annotations

import logging
import re

from agency_os.autoharness.models import (
    Challenge,
    ChallengeResult,
    EvalVerdict,
)

logger = logging.getLogger(__name__)


def _signal_score(text: str, signals: list[str]) -> float:
    """Score 0–1 based on what fraction of expected signals appear in text."""
    if not signals:
        return 1.0
    text_lower = text.lower()
    hits = sum(1 for s in signals if s.lower() in text_lower)
    return hits / len(signals)


def _anti_signal_penalty(text: str, anti_signals: list[str]) -> float:
    """Return a penalty multiplier (0–1) based on anti-signal presence.

    Each anti-signal found reduces the score by 20%, down to a floor of 0.2.
    """
    if not anti_signals:
        return 1.0
    text_lower = text.lower()
    hits = sum(1 for s in anti_signals if s.lower() in text_lower)
    return max(0.2, 1.0 - hits * 0.2)


def _length_score(text: str, difficulty: str) -> float:
    """Score based on response length relative to difficulty expectations."""
    word_count = len(text.split())
    # Minimum expected words by difficulty
    minimums = {"easy": 50, "medium": 100, "hard": 200}
    minimum = minimums.get(difficulty, 100)

    if word_count < minimum * 0.3:
        return 0.2  # Very short response
    if word_count < minimum * 0.6:
        return 0.5  # Below expectations
    if word_count < minimum:
        return 0.75  # Acceptable
    return 1.0  # Meets or exceeds


def _structure_score(text: str) -> float:
    """Score based on structural elements (headings, lists, code blocks)."""
    score = 0.5  # Baseline
    # Check for structural markers
    if re.search(r"^#+\s", text, re.MULTILINE):
        score += 0.15  # Has headings
    if re.search(r"^[-*]\s", text, re.MULTILINE):
        score += 0.15  # Has bullet points
    if "```" in text:
        score += 0.10  # Has code blocks
    if re.search(r"\d+\.\s", text):
        score += 0.10  # Has numbered lists
    return min(1.0, score)


def _criterion_heuristic(criterion: str, text: str, challenge: Challenge) -> float:
    """Score a single rubric criterion using heuristics.

    This is the non-LLM evaluator: uses text analysis patterns to
    approximate how well the response addresses each criterion.
    """
    criterion_lower = criterion.lower()

    # Map common criterion names to evaluation strategies
    if "correct" in criterion_lower or "accuracy" in criterion_lower:
        # Correctness: signal coverage + no anti-signals
        sig = _signal_score(text, challenge.expected_signals)
        anti = _anti_signal_penalty(text, challenge.anti_signals)
        return sig * anti

    if "structure" in criterion_lower or "clarity" in criterion_lower:
        return _structure_score(text)

    if "complete" in criterion_lower or "depth" in criterion_lower:
        length = _length_score(text, challenge.difficulty.value)
        sig = _signal_score(text, challenge.expected_signals)
        return (length + sig) / 2

    if "error" in criterion_lower or "handling" in criterion_lower:
        error_terms = [
            "error",
            "exception",
            "try",
            "catch",
            "handle",
            "fallback",
            "recover",
        ]
        return _signal_score(text, error_terms)

    if "document" in criterion_lower or "explanation" in criterion_lower:
        return (
            _length_score(text, challenge.difficulty.value) + _structure_score(text)
        ) / 2

    if "diagnos" in criterion_lower or "identif" in criterion_lower:
        diagnostic_terms = ["cause", "root cause", "because", "due to", "result of"]
        return _signal_score(text, diagnostic_terms)

    if (
        "fix" in criterion_lower
        or "improvement" in criterion_lower
        or "recommend" in criterion_lower
    ):
        fix_terms = [
            "fix",
            "solution",
            "resolve",
            "improve",
            "instead",
            "recommend",
            "should",
        ]
        return _signal_score(text, fix_terms)

    if "verif" in criterion_lower or "test" in criterion_lower:
        test_terms = ["test", "verify", "assert", "check", "confirm", "validate"]
        return _signal_score(text, test_terms)

    if "metric" in criterion_lower or "kpi" in criterion_lower:
        metric_terms = [
            "metric",
            "KPI",
            "measure",
            "track",
            "percentage",
            "rate",
            "target",
        ]
        return _signal_score(text, metric_terms)

    if "risk" in criterion_lower:
        risk_terms = ["risk", "threat", "vulnerability", "concern", "mitigation"]
        return _signal_score(text, risk_terms)

    if "audience" in criterion_lower or "channel" in criterion_lower:
        marketing_terms = [
            "audience",
            "segment",
            "channel",
            "persona",
            "target",
            "demographic",
        ]
        return _signal_score(text, marketing_terms)

    if "content" in criterion_lower or "plan" in criterion_lower:
        plan_terms = ["plan", "schedule", "calendar", "phase", "timeline", "milestone"]
        return _signal_score(text, plan_terms)

    if "escalat" in criterion_lower:
        escalation_terms = [
            "escalat",
            "notify",
            "alert",
            "severity",
            "priority",
            "on-call",
        ]
        return _signal_score(text, escalation_terms)

    if "monitor" in criterion_lower:
        monitoring_terms = ["monitor", "observ", "alert", "dashboard", "log", "metric"]
        return _signal_score(text, monitoring_terms)

    if "access" in criterion_lower:
        a11y_terms = [
            "aria",
            "screen reader",
            "contrast",
            "keyboard",
            "alt text",
            "wcag",
        ]
        return _signal_score(text, a11y_terms)

    if "respons" in criterion_lower:
        responsive_terms = [
            "responsive",
            "mobile",
            "breakpoint",
            "viewport",
            "tablet",
            "media query",
        ]
        return _signal_score(text, responsive_terms)

    if "layout" in criterion_lower or "interaction" in criterion_lower:
        ui_terms = [
            "layout",
            "grid",
            "flex",
            "component",
            "click",
            "hover",
            "navigation",
        ]
        return _signal_score(text, ui_terms)

    # Fallback: generic quality signal
    sig = _signal_score(text, challenge.expected_signals)
    length = _length_score(text, challenge.difficulty.value)
    return (sig + length) / 2


def evaluate(
    challenge: Challenge,
    agent_id: str,
    response: str,
    duration_sec: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> ChallengeResult:
    """Evaluate an agent's response against a challenge rubric.

    Scores each criterion in the rubric using text analysis heuristics,
    computes a weighted average, and maps to a verdict.

    Args:
        challenge: The challenge that was attempted.
        agent_id: ID of the agent that responded.
        response: The agent's raw response text.
        duration_sec: How long the agent took.
        tokens_in: Input tokens consumed.
        tokens_out: Output tokens generated.

    Returns:
        ChallengeResult with scores, verdict, and reasoning.
    """
    rubric = challenge.rubric

    # Score each criterion
    criterion_scores: dict[str, float] = {}
    reasoning_parts: list[str] = []

    for criterion, weight in rubric.criteria.items():
        score = _criterion_heuristic(criterion, response, challenge)
        score = max(0.0, min(1.0, score))  # Clamp
        criterion_scores[criterion] = round(score, 3)
        reasoning_parts.append(f"{criterion}: {score:.2f} (weight={weight:.2f})")

    # Weighted average
    weighted_score = sum(criterion_scores[c] * w for c, w in rubric.criteria.items())
    weighted_score = round(weighted_score, 3)

    # Map to verdict
    if weighted_score >= rubric.pass_threshold:
        verdict = EvalVerdict.PASS
    elif weighted_score >= rubric.partial_threshold:
        verdict = EvalVerdict.PARTIAL
    else:
        verdict = EvalVerdict.FAIL

    reasoning = (
        f"Weighted score: {weighted_score:.3f} "
        f"(pass>={rubric.pass_threshold}, partial>={rubric.partial_threshold}). "
        + "; ".join(reasoning_parts)
    )

    logger.debug(
        f"Evaluated {agent_id} on {challenge.challenge_id}: "
        f"{verdict.value} ({weighted_score:.3f})"
    )

    return ChallengeResult(
        challenge_id=challenge.challenge_id,
        agent_id=agent_id,
        verdict=verdict,
        weighted_score=weighted_score,
        criterion_scores=criterion_scores,
        response=response,
        reasoning=reasoning,
        duration_sec=duration_sec,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
