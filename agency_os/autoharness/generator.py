"""Challenge generator — synthesizes evaluation tasks from agent specs."""

from __future__ import annotations

import logging
import random
from typing import Any

from agency_os.agents.business_agent import BusinessAgent
from agency_os.autoharness.models import (
    Challenge,
    ChallengeDifficulty,
    EvalRubric,
    HarnessConfig,
)

logger = logging.getLogger(__name__)


def _to_singular(plural: str) -> str:
    """Naive English plural → singular (covers template keys only)."""
    if plural.endswith("sses"):
        return plural[:-2]  # "processes" → "process"  (not used but safe)
    if plural.endswith("ses"):
        return plural[:-2]  # "focuses" → "focus"
    if plural.endswith("ies"):
        return plural[:-3] + "y"  # "strategies" → "strategy"
    if plural.endswith("s") and not plural.endswith("ss"):
        return plural[:-1]  # "components" → "component"
    return plural


# ---------------------------------------------------------------------------
# Domain challenge templates
# ---------------------------------------------------------------------------
# Each template is a dict with:
#   title_fmt:   f-string for the challenge title ({agent_name}, {division})
#   description_fmt: f-string for the task prompt
#   rubric:      EvalRubric instance
#   expected_signals: patterns that should appear in a good answer
#   anti_signals: patterns that indicate a bad answer

_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "engineering": [
        {
            "title_fmt": "Implement a {component} component",
            "description_fmt": (
                "Write a well-structured {component} component. "
                "Include proper error handling, input validation, and "
                "clear documentation. Explain your design choices."
            ),
            "rubric": EvalRubric(
                criteria={
                    "correctness": 0.35,
                    "structure": 0.25,
                    "error_handling": 0.20,
                    "documentation": 0.20,
                }
            ),
            "expected_signals": ["function", "error", "return", "validate"],
            "anti_signals": ["todo", "not implemented", "placeholder"],
            "components": [
                "rate limiter",
                "cache invalidator",
                "retry handler",
                "pagination helper",
                "input sanitizer",
                "event emitter",
            ],
        },
        {
            "title_fmt": "Debug a {scenario} issue",
            "description_fmt": (
                "A production system is experiencing {scenario}. "
                "Diagnose the likely root causes, propose a fix, and "
                "describe how you would verify the fix works."
            ),
            "rubric": EvalRubric(
                criteria={
                    "diagnosis": 0.35,
                    "fix_quality": 0.35,
                    "verification": 0.30,
                }
            ),
            "expected_signals": ["cause", "fix", "test", "verify"],
            "anti_signals": ["not sure", "maybe try"],
            "scenarios": [
                "memory leak in a long-running process",
                "race condition in concurrent writes",
                "N+1 query performance degradation",
                "deadlock between database transactions",
                "cache stampede under high load",
            ],
        },
        {
            "title_fmt": "Review code for {focus}",
            "description_fmt": (
                "Review the following approach and identify issues related "
                "to {focus}. Suggest concrete improvements with code examples."
            ),
            "rubric": EvalRubric(
                criteria={
                    "issue_identification": 0.40,
                    "improvement_quality": 0.35,
                    "explanation_clarity": 0.25,
                }
            ),
            "expected_signals": ["issue", "improve", "instead", "recommend"],
            "anti_signals": ["looks good", "no issues"],
            "focuses": [
                "security vulnerabilities",
                "performance bottlenecks",
                "maintainability concerns",
                "error handling gaps",
            ],
        },
    ],
    "design": [
        {
            "title_fmt": "Design a {system} interface",
            "description_fmt": (
                "Design the user interface for a {system}. Cover layout, "
                "interaction patterns, accessibility requirements, and "
                "responsive behavior across devices."
            ),
            "rubric": EvalRubric(
                criteria={
                    "layout_clarity": 0.30,
                    "interaction_design": 0.25,
                    "accessibility": 0.25,
                    "responsiveness": 0.20,
                }
            ),
            "expected_signals": ["layout", "interaction", "accessible", "responsive"],
            "anti_signals": ["skip accessibility", "desktop only"],
            "systems": [
                "dashboard analytics panel",
                "multi-step onboarding flow",
                "real-time notification center",
                "data table with filters",
            ],
        },
    ],
    "marketing": [
        {
            "title_fmt": "Create a {campaign_type} strategy",
            "description_fmt": (
                "Develop a comprehensive {campaign_type} strategy. "
                "Include target audience analysis, channel selection, "
                "content calendar, KPIs, and expected ROI."
            ),
            "rubric": EvalRubric(
                criteria={
                    "audience_analysis": 0.25,
                    "channel_strategy": 0.25,
                    "content_plan": 0.25,
                    "metrics_kpis": 0.25,
                }
            ),
            "expected_signals": ["audience", "channel", "content", "metric", "ROI"],
            "anti_signals": ["generic", "one-size-fits-all"],
            "campaign_types": [
                "product launch",
                "brand awareness",
                "lead generation",
                "customer retention",
                "seasonal promotion",
            ],
        },
    ],
    "operations": [
        {
            "title_fmt": "Plan a {process} workflow",
            "description_fmt": (
                "Design an end-to-end {process} workflow. Include roles, "
                "handoff points, escalation paths, SLAs, and monitoring."
            ),
            "rubric": EvalRubric(
                criteria={
                    "completeness": 0.30,
                    "clarity": 0.25,
                    "escalation_paths": 0.25,
                    "monitoring": 0.20,
                }
            ),
            "expected_signals": ["workflow", "escalat", "SLA", "monitor"],
            "anti_signals": ["ad hoc", "figure it out"],
            "processes": [
                "incident response",
                "customer onboarding",
                "release management",
                "vendor evaluation",
            ],
        },
    ],
    "_default": [
        {
            "title_fmt": "Analyze and recommend for {topic}",
            "description_fmt": (
                "Provide a thorough analysis of {topic} relevant to your "
                "domain. Include current state assessment, key risks, "
                "actionable recommendations, and success metrics."
            ),
            "rubric": EvalRubric(
                criteria={
                    "analysis_depth": 0.30,
                    "risk_identification": 0.25,
                    "recommendations": 0.25,
                    "metrics": 0.20,
                }
            ),
            "expected_signals": ["analysis", "risk", "recommend", "metric"],
            "anti_signals": ["generic", "unclear"],
            "topics": [
                "process improvement",
                "resource allocation",
                "quality assurance",
                "team productivity",
            ],
        },
    ],
}

# Difficulty modifiers applied to challenge descriptions
_DIFFICULTY_MODIFIERS: dict[ChallengeDifficulty, str] = {
    ChallengeDifficulty.EASY: (
        " Keep your response focused and concise. A straightforward approach is fine."
    ),
    ChallengeDifficulty.MEDIUM: (
        " Consider edge cases and trade-offs. "
        "Provide a balanced, well-reasoned response."
    ),
    ChallengeDifficulty.HARD: (
        " This is a complex scenario with competing constraints. "
        "Address edge cases, failure modes, scalability concerns, "
        "and provide production-grade reasoning."
    ),
}


def _pick_difficulty(config: HarnessConfig) -> ChallengeDifficulty:
    """Sample a difficulty level from the configured distribution."""
    dist = config.difficulty_distribution
    levels = list(dist.keys())
    weights = [dist[k] for k in levels]
    chosen = random.choices(levels, weights=weights, k=1)[0]
    return ChallengeDifficulty(chosen)


def _fill_template(
    template: dict[str, Any],
    agent: BusinessAgent,
    difficulty: ChallengeDifficulty,
) -> Challenge:
    """Instantiate a challenge from a template."""
    # Pick a random variant from the template's options list
    variant_key = None
    variant_value = ""
    for key in template:
        if key not in {
            "title_fmt",
            "description_fmt",
            "rubric",
            "expected_signals",
            "anti_signals",
        }:
            variant_key = key
            variant_value = random.choice(template[key])
            break

    # Build substitutions
    subs: dict[str, str] = {
        "agent_name": agent.name,
        "division": agent.spec.division,
    }
    if variant_key:
        # Map plural key to singular for format string (e.g. "components" → "component")
        singular = _to_singular(variant_key)
        subs[singular] = variant_value

    title = template["title_fmt"].format(**subs)
    description = template["description_fmt"].format(**subs)
    description += _DIFFICULTY_MODIFIERS[difficulty]

    return Challenge(
        title=title,
        description=description,
        domain=agent.spec.division,
        difficulty=difficulty,
        rubric=template["rubric"],
        expected_signals=list(template.get("expected_signals", [])),
        anti_signals=list(template.get("anti_signals", [])),
        metadata={"agent_target": agent.agent_id, "variant": variant_value},
    )


def generate_challenges(
    agent: BusinessAgent,
    config: HarnessConfig,
    seed: int | None = None,
) -> list[Challenge]:
    """Generate evaluation challenges tailored to an agent's domain.

    Uses the agent's division to select domain-specific templates,
    falling back to generic templates for unknown divisions.

    Args:
        agent: The agent to generate challenges for.
        config: Harness configuration (controls count, difficulty distribution).
        seed: Optional random seed for reproducibility.

    Returns:
        List of Challenge objects ready for execution.
    """
    if seed is not None:
        random.seed(seed)

    division = agent.spec.division.lower()
    templates = _TEMPLATES.get(division, _TEMPLATES["_default"])

    challenges: list[Challenge] = []
    for _ in range(config.challenges_per_agent):
        template = random.choice(templates)
        difficulty = _pick_difficulty(config)
        challenge = _fill_template(template, agent, difficulty)
        challenges.append(challenge)

    logger.info(
        f"Generated {len(challenges)} challenges for {agent.agent_id} "
        f"(division={division})"
    )
    return challenges
