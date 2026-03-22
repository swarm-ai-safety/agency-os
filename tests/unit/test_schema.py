"""Tests for agency_os.packages.schema."""

from agency_os.packages.schema import (
    AgentRef,
    BidStrategy,
    DeploymentConfig,
    GovernanceConfig,
    PackageMetadata,
    PackageSpec,
    Tier,
    WorkflowDef,
)


class TestPackageSpec:
    def test_minimal_valid(self):
        spec = PackageSpec(
            metadata=PackageMetadata(name="test"),
        )
        assert spec.metadata.name == "test"
        assert spec.metadata.tier == Tier.PROFESSIONAL
        assert spec.governance.preset == "balanced"

    def test_full_spec(self):
        spec = PackageSpec(
            metadata=PackageMetadata(
                name="full-test",
                display_name="Full Test",
                tier=Tier.ENTERPRISE,
            ),
            agents=[
                AgentRef(
                    ref="engineering/senior-developer",
                    count=2,
                    economic={
                        "initial_balance": 1000,
                        "bid_strategy": "quality_weighted",
                    },
                ),
            ],
            governance=GovernanceConfig(preset="aggressive"),
            deployment=DeploymentConfig(budget_limit_usd=500.0),
        )
        assert spec.agents[0].count == 2
        assert spec.agents[0].economic.bid_strategy == BidStrategy.QUALITY_WEIGHTED
        assert spec.deployment.budget_limit_usd == 500.0

    def test_defaults(self):
        spec = PackageSpec(metadata=PackageMetadata(name="defaults"))
        assert spec.apiVersion == "agency-os/v1"
        assert spec.kind == "Package"
        assert spec.deployment.model == "claude-sonnet-4-20250514"
        assert spec.extends is None


class TestAgentRef:
    def test_defaults(self):
        ref = AgentRef(ref="engineering/senior-developer")
        assert ref.count == 1
        assert ref.economic.initial_balance == 500.0
        assert ref.economic.bid_strategy == BidStrategy.DEFAULT
        assert ref.permissions.tools == []
        assert ref.permissions.deny == []

    def test_with_permissions(self):
        ref = AgentRef(
            ref="test/agent",
            permissions={"tools": ["code_write"], "deny": ["deploy_production"]},
        )
        assert "code_write" in ref.permissions.tools
        assert "deploy_production" in ref.permissions.deny


class TestWorkflowDef:
    def test_parsed_stages(self):
        wf = WorkflowDef(
            name="test",
            stages=[
                {"plan": ["pm"]},
                {"implement": ["dev1", "dev2"]},
            ],
        )
        stages = wf.parsed_stages()
        assert len(stages) == 2
        assert stages[0].name == "plan"
        assert stages[1].agents == ["dev1", "dev2"]
