"""Tests for agency_os.orchestration.organization."""

from pathlib import Path

import pytest

from agency_os.orchestration.organization import Organization, OrgStatus

PACKAGE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "agency_os"
    / "packages"
    / "library"
    / "saas_dev_studio.yaml"
)


@pytest.fixture
def org():
    return Organization.from_file(str(PACKAGE_PATH), org_id="test-org")


class TestOrganization:
    def test_create(self, org):
        assert org.org_id == "test-org"
        assert org.status == OrgStatus.CREATED
        assert len(org.agents) == 0

    def test_start(self, org):
        org.start()
        assert org.status == OrgStatus.RUNNING
        assert len(org.agents) == 6

    def test_stop(self, org):
        org.start()
        org.stop()
        assert org.status == OrgStatus.STOPPED

    def test_submit_task(self, org):
        org.start()
        result = org.submit_task("Build a login page")
        assert result["status"] == "assigned"
        assert result["assigned_to"] is not None
        assert result["bid_amount"] > 0
        assert len(result["bids"]) == 6

    def test_submit_task_not_running(self, org):
        with pytest.raises(RuntimeError, match="not running"):
            org.submit_task("Should fail")

    def test_get_agent(self, org):
        org.start()
        agent = org.get_agent("engineering-senior-developer")
        assert agent is not None
        assert agent.name == "Tech Lead"

        assert org.get_agent("nonexistent") is None

    def test_status_dict(self, org):
        org.start()
        status = org.status_dict()
        assert status["org_id"] == "test-org"
        assert status["agent_count"] == 6
        assert status["package"] == "saas-dev-studio"

    def test_from_builtin(self):
        org = Organization.from_builtin("saas_dev_studio")
        org.start()
        assert len(org.agents) == 6

    def test_highest_bid_wins(self, org):
        org.start()
        result = org.submit_task("Any task")
        # Tech Lead has highest balance (1000) with quality_weighted strategy
        assert result["assigned_to"] == "engineering-senior-developer"
