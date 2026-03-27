"""CAIRN Protocol adapter for Agency-OS governance.

Maps Agency-OS task classification and failure signals to CAIRN-compatible
types for future integration with the CAIRN fault-tolerant recovery protocol.

CAIRN Protocol: github.com/MarouaBoud/cairn-protocol
ERC-8183 (Agentic Commerce), ERC-8004 (Agent Identity), ERC-7710 (Delegation)

ZERA-371
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from agency_os.governance.classifier import TaskType
from agency_os.governance.normalize import normalize_for_matching


class CairnTaskType(enum.Enum):
    """CAIRN domain.operation taxonomy."""

    single_action = "single_action"
    multi_step = "multi_step"
    multi_agent = "multi_agent"


class CairnFailureType(enum.Enum):
    """CAIRN failure classification types."""

    LIVENESS = "LIVENESS"  # Agent unresponsive / timed out
    RESOURCE = "RESOURCE"  # Budget, quota, or capacity exhausted
    LOGIC = "LOGIC"  # Wrong output, validation failure, bad result


# Mapping from Agency-OS TaskType to CAIRN task type
_TASK_TYPE_MAP: dict[TaskType, CairnTaskType] = {
    TaskType.stateless: CairnTaskType.single_action,
    TaskType.pipeline: CairnTaskType.multi_step,
    TaskType.coordination: CairnTaskType.multi_agent,
}

# Keyword patterns for failure type classification
_LIVENESS_PATTERNS = re.compile(
    r"\b(timeout|timed out|unresponsive|heartbeat|health check|"
    r"connection refused|connection reset|unreachable|"
    r"hung|deadlock|stall|frozen|not responding)\b",
    re.IGNORECASE,
)
_RESOURCE_PATTERNS = re.compile(
    r"\b(budget|quota|rate limit|rate-limit|throttl\w*|"
    r"out of memory|oom|disk full|capacity|"
    r"exceeded|exhausted|insufficient|limit reached|"
    r"429|503|credit)\b",
    re.IGNORECASE,
)
_LOGIC_PATTERNS = re.compile(
    r"\b(wrong|incorrect|invalid|malformed|"
    r"validation|assertion|mismatch|unexpected|"
    r"type error|value error|key error|"
    r"failed check|bad response|corrupt|"
    r"hallucin\w*|nonsense|incoherent)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CairnMapping:
    """Result of mapping an Agency-OS task to CAIRN types."""

    agency_os_task_type: TaskType
    cairn_task_type: CairnTaskType
    requires_checkpoints: bool


@dataclass(frozen=True)
class CairnFailureClassification:
    """Result of classifying a failure into CAIRN types."""

    failure_type: CairnFailureType
    confidence: float  # 0.0-1.0, based on keyword match density
    matched_signals: int


def map_task_type(task_type: TaskType) -> CairnMapping:
    """Map an Agency-OS TaskType to its CAIRN equivalent.

    Args:
        task_type: Agency-OS task classification.

    Returns:
        CairnMapping with the CAIRN task type and checkpoint requirement.
    """
    cairn_type = _TASK_TYPE_MAP[task_type]
    return CairnMapping(
        agency_os_task_type=task_type,
        cairn_task_type=cairn_type,
        requires_checkpoints=cairn_type != CairnTaskType.single_action,
    )


def classify_failure(error_text: str) -> CairnFailureClassification:
    """Classify a failure description into a CAIRN failure type.

    Uses keyword matching (same approach as task classifier) to determine
    whether a failure is LIVENESS, RESOURCE, or LOGIC.

    Args:
        error_text: Error message, stack trace, or failure description.

    Returns:
        CairnFailureClassification with type and confidence.
    """
    text = normalize_for_matching(error_text)

    liveness_hits = len(_LIVENESS_PATTERNS.findall(text))
    resource_hits = len(_RESOURCE_PATTERNS.findall(text))
    logic_hits = len(_LOGIC_PATTERNS.findall(text))

    total_hits = liveness_hits + resource_hits + logic_hits

    if total_hits == 0:
        return CairnFailureClassification(
            failure_type=CairnFailureType.LOGIC,
            confidence=0.0,
            matched_signals=0,
        )

    # Highest signal wins; ties break to LOGIC (safest default)
    if liveness_hits > resource_hits and liveness_hits > logic_hits:
        winner = CairnFailureType.LIVENESS
        winner_hits = liveness_hits
    elif resource_hits > logic_hits:
        winner = CairnFailureType.RESOURCE
        winner_hits = resource_hits
    else:
        winner = CairnFailureType.LOGIC
        winner_hits = logic_hits

    # Confidence: proportion of hits that agree on the winning type
    confidence = min(1.0, winner_hits / max(total_hits, 1))

    return CairnFailureClassification(
        failure_type=winner,
        confidence=round(confidence, 2),
        matched_signals=total_hits,
    )
