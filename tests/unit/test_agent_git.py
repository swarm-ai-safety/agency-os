"""Tests for agent-first git primitives."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from agency_os.agent_git import (
    AgentDelegation,
    AgentGitAction,
    AgentGitAttestation,
    AgentGitScope,
    AgentGitWorkspace,
    agent_ref,
    evaluate_action,
)
from agency_os.service.cli import app


def _delegation(now: float = 100.0) -> AgentDelegation:
    return AgentDelegation(
        agent_id="codex-agent-17",
        delegated_by="alice",
        purpose="agency-os-123",
        issued_at=now,
        expires_at=now + 3600,
        scopes=(
            AgentGitScope(
                repo="acme/widget",
                actions=frozenset(
                    {
                        AgentGitAction.CREATE_REF,
                        AgentGitAction.COMMIT,
                        AgentGitAction.PUSH,
                    }
                ),
                protected_paths=("billing", ".github/workflows"),
                max_changed_files=3,
                require_human_approval=True,
            ),
        ),
    )


def test_agent_ref_sanitizes_model_supplied_ids():
    ref = agent_ref("../Codex Agent 17", "task:ship/mvp")

    assert ref == "refs/agents/Codex-Agent-17/task-ship-mvp"


def test_delegation_id_is_stable_for_json_roundtrip():
    delegation = _delegation()
    restored = AgentDelegation.from_dict(delegation.to_dict())

    assert restored.delegation_id == delegation.delegation_id
    assert restored.scopes[0].actions == delegation.scopes[0].actions


def test_policy_allows_scoped_agent_ref_action():
    decision = evaluate_action(
        _delegation(),
        repo="acme/widget",
        action=AgentGitAction.PUSH,
        ref="refs/agents/codex-agent-17/agency-os-123",
        changed_files=("agency_os/agent_git/models.py",),
        now=200.0,
    )

    assert decision.allowed is True
    assert decision.human_approval_required is True
    assert decision.reasons == ()


def test_policy_blocks_expired_delegation():
    decision = evaluate_action(
        _delegation(),
        repo="acme/widget",
        action=AgentGitAction.PUSH,
        ref="refs/agents/codex-agent-17/agency-os-123",
        now=4000.0,
    )

    assert decision.allowed is False
    assert decision.reasons == ("delegation expired",)


def test_policy_blocks_protected_paths_and_large_changes():
    decision = evaluate_action(
        _delegation(),
        repo="acme/widget",
        action=AgentGitAction.PUSH,
        ref="refs/agents/codex-agent-17/agency-os-123",
        changed_files=(
            "billing/stripe.py",
            "agency_os/a.py",
            "agency_os/b.py",
            "agency_os/c.py",
        ),
        now=200.0,
    )

    assert decision.allowed is False
    assert "changed file count 4 exceeds limit 3" in decision.reasons
    assert "protected paths touched: billing/stripe.py" in decision.reasons


def test_policy_blocks_human_namespace():
    decision = evaluate_action(
        _delegation(),
        repo="acme/widget",
        action=AgentGitAction.PUSH,
        ref="refs/heads/main",
        now=200.0,
    )

    assert decision.allowed is False
    assert decision.reasons == (
        "ref refs/heads/main is outside delegated prefixes: refs/agents/",
    )


def test_attestation_emits_commit_trailers():
    attestation = AgentGitAttestation(
        delegation=_delegation(),
        workspace=AgentGitWorkspace(
            agent_id="codex-agent-17",
            task_id="agency-os-123",
            repo="acme/widget",
            ref="refs/agents/codex-agent-17/agency-os-123",
        ),
        action=AgentGitAction.COMMIT,
        checks=("pytest tests/unit/test_agent_git.py",),
    )

    trailers = attestation.commit_trailers()

    assert "Agent-ID: codex-agent-17" in trailers
    assert "Delegated-By: alice" in trailers
    assert "Agent-Action: git.commit" in trailers
    assert "Agent-Checks: pytest tests/unit/test_agent_git.py" in trailers


def test_cli_delegate_check_and_attest(tmp_path):
    runner = CliRunner()
    delegation_path = tmp_path / "delegation.json"

    delegate_result = runner.invoke(
        app,
        [
            "agent-git",
            "delegate",
            "--agent-id",
            "codex-agent-17",
            "--delegated-by",
            "alice",
            "--repo",
            "acme/widget",
            "--purpose",
            "agency-os-123",
            "--ttl-minutes",
            "60",
            "--output",
            str(delegation_path),
        ],
    )

    assert delegate_result.exit_code == 0
    delegation = json.loads(delegation_path.read_text())
    assert delegation["agent_id"] == "codex-agent-17"

    check_result = runner.invoke(
        app,
        [
            "agent-git",
            "check",
            str(delegation_path),
            "--repo",
            "acme/widget",
            "--action",
            "git.push",
            "--ref",
            "refs/agents/codex-agent-17/agency-os-123",
        ],
    )

    assert check_result.exit_code == 0
    assert '"allowed": true' in check_result.stdout

    attest_result = runner.invoke(
        app,
        [
            "agent-git",
            "attest",
            str(delegation_path),
            "--repo",
            "acme/widget",
            "--task-id",
            "agency-os-123",
            "--check",
            "pytest",
            "--trailers",
        ],
    )

    assert attest_result.exit_code == 0
    assert "Agent-ID: codex-agent-17" in attest_result.stdout
    assert "Agent-Checks: pytest" in attest_result.stdout
