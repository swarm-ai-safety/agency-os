"""Models for delegated agent git work."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentGitAction(str, Enum):
    """Actions an agent may be delegated to perform against a repository."""

    CREATE_REF = "git.ref.create"
    COMMIT = "git.commit"
    PUSH = "git.push"
    OPEN_PR = "git.pr.open"
    REVIEW = "git.review"
    MERGE = "git.merge"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class AgentGitScope:
    """A single repository capability granted to an agent."""

    repo: str
    actions: frozenset[AgentGitAction]
    ref_prefixes: tuple[str, ...] = ("refs/agents/",)
    protected_paths: tuple[str, ...] = ()
    max_changed_files: int | None = None
    require_human_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "actions": sorted(action.value for action in self.actions),
            "ref_prefixes": list(self.ref_prefixes),
            "protected_paths": list(self.protected_paths),
            "max_changed_files": self.max_changed_files,
            "require_human_approval": self.require_human_approval,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AgentGitScope:
        return cls(
            repo=raw["repo"],
            actions=frozenset(AgentGitAction(action) for action in raw["actions"]),
            ref_prefixes=tuple(raw.get("ref_prefixes") or ("refs/agents/",)),
            protected_paths=tuple(raw.get("protected_paths") or ()),
            max_changed_files=raw.get("max_changed_files"),
            require_human_approval=bool(raw.get("require_human_approval", True)),
        )


@dataclass(frozen=True)
class AgentDelegation:
    """Time-bound authority delegated from a human or organization to an agent."""

    agent_id: str
    delegated_by: str
    purpose: str
    scopes: tuple[AgentGitScope, ...]
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def delegation_id(self) -> str:
        """Stable content-derived identifier for logs and attestations."""
        payload = json.dumps(self.to_dict(include_id=False), sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"agd_{digest}"

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (time.time() if now is None else now) >= self.expires_at

    def to_dict(self, include_id: bool = True) -> dict[str, Any]:
        data = {
            "agent_id": self.agent_id,
            "delegated_by": self.delegated_by,
            "purpose": self.purpose,
            "scopes": [scope.to_dict() for scope in self.scopes],
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }
        if include_id:
            data["delegation_id"] = self.delegation_id
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AgentDelegation:
        return cls(
            agent_id=raw["agent_id"],
            delegated_by=raw["delegated_by"],
            purpose=raw["purpose"],
            scopes=tuple(AgentGitScope.from_dict(scope) for scope in raw["scopes"]),
            issued_at=float(raw["issued_at"]),
            expires_at=raw.get("expires_at"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(frozen=True)
class AgentGitWorkspace:
    """Namespaced branch/workspace for one delegated task."""

    agent_id: str
    task_id: str
    repo: str
    ref: str
    base_ref: str = "refs/heads/main"

    def to_dict(self) -> dict[str, str]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "repo": self.repo,
            "ref": self.ref,
            "base_ref": self.base_ref,
        }


@dataclass(frozen=True)
class AgentGitPolicyDecision:
    """Policy result for a requested git action."""

    allowed: bool
    reasons: tuple[str, ...] = ()
    human_approval_required: bool = False
    matched_scope: AgentGitScope | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "human_approval_required": self.human_approval_required,
            "matched_scope": self.matched_scope.to_dict()
            if self.matched_scope
            else None,
        }


@dataclass(frozen=True)
class AgentGitAttestation:
    """Structured provenance attached to commits, PRs, or audit logs."""

    delegation: AgentDelegation
    workspace: AgentGitWorkspace
    action: AgentGitAction
    checks: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    confidence: str = "medium"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "agency-os.agent-git.attestation.v1",
            "delegation": self.delegation.to_dict(),
            "workspace": self.workspace.to_dict(),
            "action": self.action.value,
            "checks": list(self.checks),
            "tools_used": list(self.tools_used),
            "changed_files": list(self.changed_files),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def commit_trailers(self) -> tuple[str, ...]:
        """Return git commit trailers carrying the minimum provenance."""
        return (
            f"Agent-ID: {self.delegation.agent_id}",
            f"Delegated-By: {self.delegation.delegated_by}",
            f"Delegation-ID: {self.delegation.delegation_id}",
            f"Agent-Workspace: {self.workspace.ref}",
            f"Agent-Action: {self.action.value}",
            f"Agent-Checks: {', '.join(self.checks) if self.checks else 'not-run'}",
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AgentGitAttestation:
        return cls(
            delegation=AgentDelegation.from_dict(raw["delegation"]),
            workspace=AgentGitWorkspace(**raw["workspace"]),
            action=AgentGitAction(raw["action"]),
            checks=tuple(raw.get("checks") or ()),
            tools_used=tuple(raw.get("tools_used") or ()),
            changed_files=tuple(raw.get("changed_files") or ()),
            confidence=raw.get("confidence", "medium"),
            created_at=float(raw["created_at"]),
        )
