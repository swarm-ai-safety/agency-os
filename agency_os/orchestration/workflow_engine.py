"""Multi-step workflow pipelines with quality gates."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agency_os.packages.schema import QualityGate, WorkflowDef

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    GATE_CHECK = "gate_check"


@dataclass
class StageResult:
    name: str
    agents: list[str]
    status: StageStatus = StageStatus.PENDING
    evidence: list[dict[str, Any]] = field(default_factory=list)
    approvals: int = 0


@dataclass
class WorkflowRun:
    run_id: str
    workflow_name: str
    stages: list[StageResult]
    status: str = "created"
    current_stage_index: int = 0


class WorkflowEngine:
    """
    Executes multi-step workflow pipelines defined in package YAML.

    Each workflow has ordered stages, each assigned to specific agents.
    Quality gates between stages enforce minimum evidence, approvals, etc.
    """

    def __init__(self, workflow_defs: list[WorkflowDef]):
        self._workflows = {w.name: w for w in workflow_defs}

    def create_run(self, workflow_name: str) -> WorkflowRun:
        """Create a new workflow run."""
        wf = self._workflows.get(workflow_name)
        if wf is None:
            raise KeyError(f"Workflow not found: {workflow_name}")

        stages = []
        for stage_dict in wf.stages:
            for name, agents in stage_dict.items():
                stages.append(StageResult(name=name, agents=agents))

        return WorkflowRun(
            run_id=f"wf-{uuid.uuid4().hex[:8]}",
            workflow_name=workflow_name,
            stages=stages,
        )

    def advance_stage(
        self,
        run: WorkflowRun,
        evidence: list[dict[str, Any]] | None = None,
        approvals: int = 0,
    ) -> bool:
        """
        Complete the current stage and attempt to advance to the next.

        Checks quality gates between stages. Returns True if advanced,
        False if blocked by a gate.
        """
        if run.current_stage_index >= len(run.stages):
            return False

        current = run.stages[run.current_stage_index]
        current.evidence = evidence or []
        current.approvals = approvals
        current.status = StageStatus.PASSED

        # Check gate to next stage
        wf = self._workflows[run.workflow_name]
        if run.current_stage_index < len(run.stages) - 1:
            next_stage = run.stages[run.current_stage_index + 1]
            gate_name = f"{current.name}_to_{next_stage.name}"

            gate = wf.quality_gates.get(gate_name)
            if gate:
                if not self._check_gate(gate, current):
                    current.status = StageStatus.GATE_CHECK
                    logger.warning(f"Gate blocked: {gate_name}")
                    return False

        run.current_stage_index += 1
        if run.current_stage_index >= len(run.stages):
            run.status = "completed"
        else:
            run.status = "running"

        logger.info(
            f"Workflow {run.workflow_name} advanced to stage {run.current_stage_index}"
        )
        return True

    def _check_gate(self, gate: QualityGate, stage: StageResult) -> bool:
        """Check if a stage result passes a quality gate."""
        if gate.min_evidence_items is not None:
            if len(stage.evidence) < gate.min_evidence_items:
                return False
        if gate.min_approvals is not None:
            if stage.approvals < gate.min_approvals:
                return False
        return True
