"""Agent-first git primitives.

This package is intentionally small: it gives agents a delegated identity,
scoped repository permissions, structured provenance, and deterministic branch
names without requiring a replacement for GitHub or GitLab.
"""

from agency_os.agent_git.models import (
    AgentDelegation,
    AgentGitAction,
    AgentGitAttestation,
    AgentGitPolicyDecision,
    AgentGitScope,
    AgentGitWorkspace,
)
from agency_os.agent_git.policy import evaluate_action
from agency_os.agent_git.refs import agent_ref, sanitize_ref_component

__all__ = [
    "AgentDelegation",
    "AgentGitAction",
    "AgentGitAttestation",
    "AgentGitPolicyDecision",
    "AgentGitScope",
    "AgentGitWorkspace",
    "agent_ref",
    "evaluate_action",
    "sanitize_ref_component",
]
