"""Pydantic models for package YAML validation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Tier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class BidStrategy(str, Enum):
    DEFAULT = "default"
    QUALITY_WEIGHTED = "quality_weighted"
    SPECIALIZATION_BONUS = "specialization_bonus"
    BUDGET_CONSCIOUS = "budget_conscious"


class AgentEconomicConfig(BaseModel):
    initial_balance: float = 500.0
    bid_strategy: BidStrategy = BidStrategy.DEFAULT


class AgentPermissions(BaseModel):
    tools: Optional[list[str]] = (
        None  # None = unconfigured (allow all); [] = no tools allowed
    )
    deny: list[str] = Field(default_factory=list)


class AgentRef(BaseModel):
    """Reference to an agent spec with optional overrides."""

    ref: str  # e.g. "engineering/senior-developer"
    count: int = 1
    role_override: dict[str, Any] = Field(default_factory=dict)
    economic: AgentEconomicConfig = Field(default_factory=AgentEconomicConfig)
    permissions: AgentPermissions = Field(
        default_factory=lambda: AgentPermissions(tools=[])
    )
    domain_tags: list[str] = Field(
        default_factory=list
    )  # e.g. ["frontend", "react", "css"]


class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    threshold: int = Field(default=3, ge=1, le=100)


class GovernanceOverrides(BaseModel):
    audit_frequency: Optional[float] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    tax_rate: Optional[float] = None


class GovernanceConfig(BaseModel):
    preset: str = "balanced"
    overrides: GovernanceOverrides = Field(default_factory=GovernanceOverrides)


class QualityGate(BaseModel):
    min_evidence_items: Optional[int] = Field(default=None, ge=0)
    min_approvals: Optional[int] = Field(default=None, ge=0)


class WorkflowStage(BaseModel):
    """A single stage in a workflow pipeline.

    Each stage is a dict with a single key (stage name) mapping to a list of agent roles.
    """

    name: str
    agents: list[str]


class WorkflowDef(BaseModel):
    name: str
    pipeline: str = "nexus_full"
    stages: list[dict[str, list[str]]] = Field(default_factory=list)
    quality_gates: dict[str, QualityGate] = Field(default_factory=dict)

    def parsed_stages(self) -> list[WorkflowStage]:
        """Convert raw stage dicts to WorkflowStage objects."""
        result = []
        for stage_dict in self.stages:
            for stage_name, agents in stage_dict.items():
                result.append(WorkflowStage(name=stage_name, agents=agents))
        return result


class DeploymentConfig(BaseModel):
    llm_provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    budget_limit_usd: float = 100.0


class PackageMetadata(BaseModel):
    name: str
    display_name: str = ""
    tier: Tier = Tier.PROFESSIONAL
    icon: str = ""
    tagline: str = ""
    use_cases: list[str] = Field(default_factory=list)
    category: str = ""


class PackageSpec(BaseModel):
    """Top-level package definition."""

    apiVersion: str = "agency-os/v1"
    kind: str = "Package"
    metadata: PackageMetadata
    extends: Optional[str] = None
    agents: list[AgentRef] = Field(default_factory=list)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    workflows: list[WorkflowDef] = Field(default_factory=list)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
