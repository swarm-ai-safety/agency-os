"""Tests for LLM execution wiring: BusinessAgent.execute_task and Organization.submit_task(execute=True)."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "swarm")
)

import pytest

from agency_os.agents.business_agent import BusinessAgent
from agency_os.agents.spec_parser import parse_spec
from agency_os.orchestration.organization import Organization
from agency_os.packages.schema import AgentEconomicConfig, AgentPermissions, BidStrategy
from swarm.agents.llm_config import LLMConfig, LLMProvider

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)
PACKAGE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "agency_os"
    / "packages"
    / "library"
    / "saas_dev_studio.yaml"
)


@pytest.fixture
def sample_spec():
    return parse_spec(FIXTURES_DIR / "engineering" / "engineering-senior-developer.md")


@pytest.fixture
def llm_config():
    return LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-sonnet-4-20250514")


@pytest.fixture
def agent(sample_spec, llm_config):
    return BusinessAgent(
        agent_id="test-dev",
        spec=sample_spec,
        llm_config=llm_config,
        economic=AgentEconomicConfig(
            initial_balance=1000, bid_strategy=BidStrategy.QUALITY_WEIGHTED
        ),
        permissions=AgentPermissions(
            tools=["code_write", "code_review"], deny=["deploy_production"]
        ),
        role_override={"title": "Tech Lead"},
    )


@pytest.fixture
def org():
    return Organization.from_file(str(PACKAGE_PATH), org_id="test-org")


class TestExecuteTask:
    """Tests for BusinessAgent.execute_task."""

    def test_execute_task_success(self, agent):
        """execute_task returns LLM response on success."""
        canned = ("Here is the login page code.", 150, 42)
        with patch.object(agent, "_call_llm_sync", return_value=canned) as mock_llm:
            result = agent.execute_task("Build a login page")

        assert result["success"] is True
        assert result["response"] == "Here is the login page code."
        assert result["tokens_in"] == 150
        assert result["tokens_out"] == 42
        assert "error" not in result

        # Verify the LLM was called with system prompt and task description
        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        assert call_args[0][0] == agent.llm_config.system_prompt
        assert "Build a login page" in call_args[0][1]

    def test_execute_task_with_context(self, agent):
        """execute_task merges context into the user prompt."""
        canned = ("Done.", 10, 5)
        with patch.object(agent, "_call_llm_sync", return_value=canned) as mock_llm:
            result = agent.execute_task(
                "Fix bug", context={"file": "app.py", "line": "42"}
            )

        assert result["success"] is True
        user_prompt = mock_llm.call_args[0][1]
        assert "file" in user_prompt
        assert "app.py" in user_prompt
        assert "line" in user_prompt
        assert "42" in user_prompt

    def test_execute_task_error_handling(self, agent):
        """execute_task returns error dict when LLM call fails."""
        with patch.object(
            agent, "_call_llm_sync", side_effect=RuntimeError("No API key set")
        ):
            result = agent.execute_task("Do something")

        assert result["success"] is False
        assert result["response"] == ""
        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0
        assert result["error"] == "No API key set"


class TestSubmitTaskExecute:
    """Tests for Organization.submit_task with execute flag."""

    def test_submit_task_execute_false(self, org):
        """submit_task with execute=False still works as before (no 'result' key)."""
        org.start()
        record = org.submit_task("Build a login page", execute=False)
        assert record["status"] == "assigned"
        assert "result" not in record

    def test_submit_task_default_no_execute(self, org):
        """submit_task defaults to execute=False for backward compatibility."""
        org.start()
        record = org.submit_task("Build a login page")
        assert record["status"] == "assigned"
        assert "result" not in record

    def test_submit_task_execute_true(self, org):
        """submit_task with execute=True calls the LLM and includes result."""
        org.start()
        canned = ("Generated code for login page.", 200, 80)

        with patch.object(BusinessAgent, "_call_llm_sync", return_value=canned):
            record = org.submit_task("Build a login page", execute=True)

        assert record["status"] == "completed"
        assert "result" in record
        assert record["result"]["success"] is True
        assert record["result"]["response"] == "Generated code for login page."
        assert record["result"]["tokens_in"] == 200
        assert record["result"]["tokens_out"] == 80

    def test_submit_task_execute_true_llm_failure(self, org):
        """submit_task with execute=True handles LLM errors gracefully."""
        org.start()

        with patch.object(
            BusinessAgent,
            "_call_llm_sync",
            side_effect=ConnectionError("Network error"),
        ):
            record = org.submit_task("Build a login page", execute=True)

        assert record["status"] == "failed"
        assert "result" in record
        assert record["result"]["success"] is False
        assert record["result"]["error"] == "Network error"

    def test_submit_task_with_metadata_passed_as_context(self, org):
        """submit_task passes metadata to execute_task as context."""
        org.start()
        canned = ("Done.", 10, 5)

        with patch.object(
            BusinessAgent, "_call_llm_sync", return_value=canned
        ) as mock_llm:
            record = org.submit_task(
                "Fix the bug",
                metadata={"priority": "high"},
                execute=True,
            )

        assert record["result"]["success"] is True
        # Verify the user prompt included the metadata context
        user_prompt = mock_llm.call_args[0][1]
        assert "priority" in user_prompt
        assert "high" in user_prompt
