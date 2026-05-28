"""Policy evaluation for delegated agent git actions."""

from __future__ import annotations

from collections.abc import Iterable

from agency_os.agent_git.models import (
    AgentDelegation,
    AgentGitAction,
    AgentGitPolicyDecision,
    AgentGitScope,
)


def evaluate_action(
    delegation: AgentDelegation,
    *,
    repo: str,
    action: AgentGitAction,
    ref: str,
    changed_files: Iterable[str] = (),
    now: float | None = None,
) -> AgentGitPolicyDecision:
    """Evaluate whether a delegated agent may perform a git action.

    This deliberately stays deterministic and side-effect free so it can run in
    a CLI, API route, CI check, or GitHub App webhook.
    """
    if delegation.is_expired(now):
        return AgentGitPolicyDecision(False, ("delegation expired",))

    changed = tuple(changed_files)
    for scope in delegation.scopes:
        if scope.repo != repo:
            continue
        reasons = _scope_rejections(
            scope, action=action, ref=ref, changed_files=changed
        )
        if not reasons:
            return AgentGitPolicyDecision(
                allowed=True,
                human_approval_required=scope.require_human_approval,
                matched_scope=scope,
            )
        return AgentGitPolicyDecision(
            allowed=False,
            reasons=reasons,
            human_approval_required=scope.require_human_approval,
            matched_scope=scope,
        )

    return AgentGitPolicyDecision(False, (f"no scope for repo {repo}",))


def _scope_rejections(
    scope: AgentGitScope,
    *,
    action: AgentGitAction,
    ref: str,
    changed_files: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if action not in scope.actions:
        reasons.append(f"action {action.value} is not delegated")
    if not ref.startswith(scope.ref_prefixes):
        prefixes = ", ".join(scope.ref_prefixes)
        reasons.append(f"ref {ref} is outside delegated prefixes: {prefixes}")
    if (
        scope.max_changed_files is not None
        and len(changed_files) > scope.max_changed_files
    ):
        reasons.append(
            f"changed file count {len(changed_files)} exceeds limit {scope.max_changed_files}"
        )
    protected = _matching_protected_paths(changed_files, scope.protected_paths)
    if protected:
        reasons.append("protected paths touched: " + ", ".join(protected))
    return tuple(reasons)


def _matching_protected_paths(
    changed_files: tuple[str, ...],
    protected_paths: tuple[str, ...],
) -> tuple[str, ...]:
    matches: list[str] = []
    for path in changed_files:
        normalized = path.strip("/")
        for protected in protected_paths:
            protected_prefix = protected.strip("/")
            if normalized == protected_prefix or normalized.startswith(
                f"{protected_prefix}/"
            ):
                matches.append(path)
                break
    return tuple(matches)
