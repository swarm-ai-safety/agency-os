"""E2E tests: budget enforcement and circuit breaker integration."""

import pytest

from agency_os.governance.presets import resolve_governance
from agency_os.orchestration.organization import Organization
from agency_os.packages.schema import GovernanceConfig


class TestCircuitBreaker:
    """Circuit breaker: trips after N failures, integrates with governance."""

    def test_conservative_circuit_breaker(self):
        config = GovernanceConfig(preset="conservative")
        swarm_config = resolve_governance(config)
        assert swarm_config.circuit_breaker_enabled is True
        assert swarm_config.freeze_threshold_violations == 2  # Trips quickly
        assert swarm_config.freeze_duration_epochs == 3

    def test_aggressive_circuit_breaker(self):
        config = GovernanceConfig(preset="aggressive")
        swarm_config = resolve_governance(config)
        assert swarm_config.circuit_breaker_enabled is True
        assert swarm_config.freeze_threshold_violations == 5  # High tolerance
        assert swarm_config.freeze_duration_epochs == 1

    def test_reputation_degradation_on_failure(self):
        org = Organization.from_builtin("saas_dev_studio")
        org.start()

        agent = org.get_agent("engineering-senior-developer")
        initial_rep = agent.reputation

        # Simulate repeated failures
        for _i in range(3):
            agent.record_task_outcome(success=False, reputation_delta=-0.2)

        assert agent.reputation < initial_rep
        assert agent.reputation == pytest.approx(0.4)


class TestMultiPackageLaunch:
    """Test launching orgs from all available packages."""

    @pytest.mark.parametrize(
        "package_name",
        [
            "saas_dev_studio",
            "marketing_agency",
            "devops_team",
            "product_squad",
        ],
    )
    def test_launch_package(self, package_name):
        org = Organization.from_builtin(package_name)
        org.start()
        assert len(org.agents) > 0
        assert org.status.value == "running"

        # Submit a task and verify routing works
        result = org.submit_task("Test task for validation")
        assert result["status"] == "assigned"
        assert result["assigned_to"] is not None

        org.stop()
        assert org.status.value == "stopped"
