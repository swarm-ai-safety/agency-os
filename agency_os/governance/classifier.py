"""Task-type classifier that auto-selects governance presets.

Categorizes tasks by structure (stateless, pipeline, coordination) and
combines that with agent trust scores to select the appropriate governance
preset from the profiles directory.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from agency_os.governance.presets import list_profiles
from agency_os.governance.trust import TrustScore


class TaskType(enum.Enum):
    """Structural category of a task."""

    stateless = "stateless"  # Independent, no sequencing needed
    pipeline = "pipeline"  # Sequential multi-step workflow
    coordination = "coordination"  # Requires cross-agent or cross-team work


# Keyword patterns for classification (compiled once)
_PIPELINE_PATTERNS = re.compile(
    r"\b(pipeline|sequential|multi[- ]?step|chain|workflow|depends on|"
    r"stage|phase|ordered|etl|batch|migration|deploy)\b",
    re.IGNORECASE,
)
_COORDINATION_PATTERNS = re.compile(
    r"\b(coordinat\w*|collaborat\w*|cross[- ]?team|handoff|hand off|"
    r"delegat\w*|sync with|align with|review by|approval|"
    r"multi[- ]?agent|consensus|merge|integrat\w*)\b",
    re.IGNORECASE,
)
_STATELESS_PATTERNS = re.compile(
    r"\b(fix|patch|hotfix|lint|format|refactor|rename|"
    r"add test|write test|update doc|bump version|"
    r"single|standalone|independent|one[- ]?off|simple)\b",
    re.IGNORECASE,
)

# How task type shifts governance strictness.
# Positive = stricter (toward conservative), negative = looser.
_TASK_TYPE_SHIFT: dict[TaskType, int] = {
    TaskType.stateless: -1,  # Low risk → loosen one tier
    TaskType.pipeline: 1,  # Long-horizon → tighten one tier
    TaskType.coordination: 1,  # Cross-agent → tighten one tier
}

# Ordered from loosest to strictest
_PRESET_LADDER = ["aggressive", "balanced", "conservative"]


def classify_task(title: str, description: str = "") -> TaskType:
    """Classify a task by its structural type using keyword matching.

    Args:
        title: Task title.
        description: Task description (optional).

    Returns:
        The detected TaskType.
    """
    text = f"{title} {description}"

    pipeline_score = len(_PIPELINE_PATTERNS.findall(text))
    coordination_score = len(_COORDINATION_PATTERNS.findall(text))
    stateless_score = len(_STATELESS_PATTERNS.findall(text))

    # Highest signal wins; ties break toward stricter category
    if coordination_score > pipeline_score and coordination_score > stateless_score:
        return TaskType.coordination
    if pipeline_score > stateless_score:
        return TaskType.pipeline
    if stateless_score > 0:
        return TaskType.stateless

    # Default: no strong signal → treat as pipeline (moderate strictness)
    return TaskType.pipeline


@dataclass(frozen=True)
class GovernanceSelection:
    """Result of the governance auto-selection."""

    preset: str
    task_type: TaskType
    trust_tier: str
    trust_preset: str  # What trust alone would suggest
    reason: str


def select_governance_preset(
    title: str,
    description: str = "",
    trust: TrustScore | None = None,
) -> GovernanceSelection:
    """Select a governance preset by combining task type and agent trust.

    The trust score provides a base preset. The task type then shifts it
    up or down one tier on the strictness ladder. Pipeline and coordination
    tasks tighten governance; stateless tasks loosen it.

    Args:
        title: Task title.
        description: Task description.
        trust: Agent trust score (if None, defaults to conservative).

    Returns:
        GovernanceSelection with the chosen preset and reasoning.
    """
    task_type = classify_task(title, description)

    # Base preset from trust
    if trust is not None:
        trust_preset = trust.governance_preset
        trust_tier = trust.tier
    else:
        trust_preset = "conservative"
        trust_tier = "low"

    # Find position on the ladder and apply shift
    available = [p for p in _PRESET_LADDER if p in list_profiles()]
    if not available:
        available = _PRESET_LADDER

    base_idx = (
        available.index(trust_preset)
        if trust_preset in available
        else len(available) - 1
    )
    shift = _TASK_TYPE_SHIFT.get(task_type, 0)
    final_idx = max(0, min(len(available) - 1, base_idx + shift))
    preset = available[final_idx]

    # Build reason
    if shift > 0 and preset != trust_preset:
        reason = (
            f"Trust suggests '{trust_preset}' but {task_type.value} task "
            f"structure tightens governance to '{preset}'"
        )
    elif shift < 0 and preset != trust_preset:
        reason = (
            f"Trust suggests '{trust_preset}' but {task_type.value} task "
            f"structure loosens governance to '{preset}'"
        )
    else:
        reason = f"Trust tier '{trust_tier}' with {task_type.value} task → '{preset}'"

    return GovernanceSelection(
        preset=preset,
        task_type=task_type,
        trust_tier=trust_tier,
        trust_preset=trust_preset,
        reason=reason,
    )
