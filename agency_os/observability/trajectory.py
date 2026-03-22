"""ATIF trajectory recorder for agent task execution.

Captures agent execution steps in the ATIF (Agent Trajectory Interchange
Format) standard using harbor models.  Designed to wrap around
BusinessAgent.execute_task() calls inside the TaskWorker.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from harbor.models.trajectories import (
    Agent as ATIFAgent,
)
from harbor.models.trajectories import (
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "ATIF-v1.6"
HARNESS_NAME = "agency-os"
HARNESS_VERSION = "0.1.0"


class TrajectoryRecorder:
    """Records agent execution as an ATIF trajectory.

    Usage::

        recorder = TrajectoryRecorder(
            agent_id="agent-abc",
            agent_name="DevOps Engineer",
            model_name="claude-sonnet-4-20250514",
        )

        # Record the system prompt / setup step
        recorder.record_system_step(system_prompt)

        # Record the user task submission
        recorder.record_user_step(task_description)

        # Record the agent's LLM response
        recorder.record_agent_step(
            response_text="...",
            tokens_in=1200,
            tokens_out=350,
            reasoning="internal chain of thought...",
        )

        # Build the final trajectory
        trajectory = recorder.build()
    """

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        model_name: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        tenant_id: str | None = None,
        org_id: str | None = None,
    ) -> None:
        self._session_id = session_id or f"task-{uuid.uuid4().hex[:12]}"
        self._agent = ATIFAgent(
            name=agent_name,
            version=HARNESS_VERSION,
            model_name=model_name,
        )
        self._steps: list[Step] = []
        self._step_counter = 0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._total_cost_usd: float | None = None
        self._extra: dict[str, Any] = {
            "agent_id": agent_id,
            "harness": HARNESS_NAME,
        }
        if task_id:
            self._extra["task_id"] = task_id
        if tenant_id:
            self._extra["tenant_id"] = tenant_id
        if org_id:
            self._extra["org_id"] = org_id

    def _next_step_id(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Step recording
    # ------------------------------------------------------------------

    def record_system_step(self, system_prompt: str) -> None:
        """Record the system prompt as a system step."""
        self._steps.append(
            Step(
                step_id=self._next_step_id(),
                timestamp=self._now_iso(),
                source="system",
                message=system_prompt,
            )
        )

    def record_user_step(self, user_message: str) -> None:
        """Record a user message (task submission)."""
        self._steps.append(
            Step(
                step_id=self._next_step_id(),
                timestamp=self._now_iso(),
                source="user",
                message=user_message,
            )
        )

    def record_agent_step(
        self,
        response_text: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        model_name: str | None = None,
        reasoning: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """Record an agent response step.

        Parameters
        ----------
        response_text:
            The agent's text response.
        tokens_in / tokens_out:
            Token counts for this step.
        model_name:
            Model used (overrides default if provided).
        reasoning:
            Internal chain-of-thought / thinking content.
        tool_calls:
            List of tool invocations, each with keys:
            ``tool_call_id``, ``function_name``, ``arguments``.
        tool_results:
            List of tool results, each with keys:
            ``source_call_id``, ``content``.
        cost_usd:
            Cost for this step in USD.
        """
        self._total_tokens_in += tokens_in
        self._total_tokens_out += tokens_out
        if cost_usd is not None:
            if self._total_cost_usd is None:
                self._total_cost_usd = 0.0
            self._total_cost_usd += cost_usd

        # Build tool calls if present
        atif_tool_calls = None
        if tool_calls:
            atif_tool_calls = [
                ToolCall(
                    tool_call_id=tc.get("tool_call_id", f"tc-{uuid.uuid4().hex[:8]}"),
                    function_name=tc["function_name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in tool_calls
            ]

        # Build observation if tool results present
        observation = None
        if tool_results:
            observation = Observation(
                results=[
                    ObservationResult(
                        source_call_id=tr.get("source_call_id"),
                        content=tr.get("content", ""),
                    )
                    for tr in tool_results
                ]
            )

        self._steps.append(
            Step(
                step_id=self._next_step_id(),
                timestamp=self._now_iso(),
                source="agent",
                model_name=model_name or self._agent.model_name,
                message=response_text,
                reasoning_content=reasoning,
                tool_calls=atif_tool_calls,
                observation=observation,
            )
        )

    def record_error_step(self, error: str) -> None:
        """Record an execution error as a system step."""
        self._steps.append(
            Step(
                step_id=self._next_step_id(),
                timestamp=self._now_iso(),
                source="system",
                message=f"[ERROR] {error}",
            )
        )

    # ------------------------------------------------------------------
    # Governance metadata
    # ------------------------------------------------------------------

    def set_governance(
        self,
        preset: str,
        task_type: str | None = None,
        trust_tier: str | None = None,
        trust_score: float | None = None,
    ) -> None:
        """Attach governance selection metadata to the trajectory."""
        gov: dict[str, Any] = {"preset": preset}
        if task_type:
            gov["task_type"] = task_type
        if trust_tier:
            gov["trust_tier"] = trust_tier
        if trust_score is not None:
            gov["trust_score"] = trust_score
        self._extra["governance"] = gov

    def set_cost(self, cost_usd: float) -> None:
        """Set total cost for the trajectory."""
        self._total_cost_usd = cost_usd

    def set_file_changes(self, changelog: list[dict[str, Any]]) -> None:
        """Attach file change log from StateManager to the trajectory."""
        if changelog:
            self._extra["file_changes"] = changelog

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> Trajectory:
        """Build the final ATIF Trajectory object.

        Returns a harbor Trajectory model that can be serialized to JSON
        via ``trajectory.model_dump(exclude_none=True)``.
        """
        if not self._steps:
            # ATIF requires at least one step — add a placeholder
            self.record_system_step("[no execution steps recorded]")

        return Trajectory(
            schema_version=SCHEMA_VERSION,
            session_id=self._session_id,
            agent=self._agent,
            steps=self._steps,
            final_metrics=FinalMetrics(
                total_steps=len(self._steps),
                total_prompt_tokens=self._total_tokens_in or None,
                total_completion_tokens=self._total_tokens_out or None,
                total_cost_usd=self._total_cost_usd,
            ),
            extra=self._extra,
        )

    def to_dict(self) -> dict[str, Any]:
        """Build and serialize the trajectory to a JSON-safe dict."""
        return self.build().model_dump(exclude_none=True)
