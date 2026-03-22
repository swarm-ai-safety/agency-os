"""Planning-first agentic engineering: decompose projects into executable plans.

This module implements the planning layer that sits between task submission
and agent execution. Inspired by the pre.dev pattern: the bottleneck is
planning, not code generation.

Flow:
    project description → research → architecture → milestones → tasks → execution
"""

from .dag import TaskDAG
from .decomposer import ProjectDecomposer
from .executor import PlanExecutor
from .schema import (
    ArchitectureComponent,
    DataFlow,
    Milestone,
    ProjectPlan,
    SandboxRequirements,
    TaskSpec,
    TechChoice,
)

__all__ = [
    "ProjectPlan",
    "ArchitectureComponent",
    "DataFlow",
    "TechChoice",
    "Milestone",
    "TaskSpec",
    "SandboxRequirements",
    "ProjectDecomposer",
    "TaskDAG",
    "PlanExecutor",
]
