"""Dev↔QA feedback loops and quality gates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QAFeedback:
    """Feedback from QA back to development."""

    reviewer_id: str
    task_id: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 1


class FeedbackLoop:
    """
    Manages Dev↔QA iteration cycles.

    If QA rejects work, it returns to dev with specific feedback.
    Tracks iteration count to prevent infinite loops.
    """

    def __init__(self, max_iterations: int = 3):
        self._max_iterations = max_iterations
        self._history: list[QAFeedback] = []

    def submit_review(self, feedback: QAFeedback) -> str:
        """
        Process QA feedback.

        Returns:
            "approved" if passed, "rework" if needs fixes, "escalate" if max iterations hit.
        """
        self._history.append(feedback)

        if feedback.passed:
            logger.info(f"Task {feedback.task_id} approved by {feedback.reviewer_id}")
            return "approved"

        if feedback.iteration >= self._max_iterations:
            logger.warning(
                f"Task {feedback.task_id} hit max iterations ({self._max_iterations}), escalating"
            )
            return "escalate"

        logger.info(
            f"Task {feedback.task_id} needs rework (iteration {feedback.iteration}): "
            f"{len(feedback.issues)} issues"
        )
        return "rework"

    @property
    def history(self) -> list[QAFeedback]:
        return list(self._history)

    @property
    def current_iteration(self) -> int:
        return len(self._history)
