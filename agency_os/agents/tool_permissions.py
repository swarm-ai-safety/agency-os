"""Per-agent tool permission enforcement."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from agency_os.agents.business_agent import BusinessAgent

logger = logging.getLogger(__name__)


class ToolPermissionDenied(PermissionError):
    """Raised when an agent attempts to use a denied tool."""

    def __init__(self, agent_id: str, tool_name: str):
        self.agent_id = agent_id
        self.tool_name = tool_name
        super().__init__(f"Agent {agent_id} denied access to tool: {tool_name}")


def check_permission(agent: BusinessAgent, tool_name: str) -> bool:
    """
    Check if an agent is allowed to use a tool.

    Returns True if allowed, False if denied.
    """
    return agent.is_tool_allowed(tool_name)


def enforce_permission(agent: BusinessAgent, tool_name: str) -> None:
    """
    Enforce tool permission, raising ToolPermissionDenied if denied.
    """
    if not agent.is_tool_allowed(tool_name):
        logger.warning(f"Permission denied: {agent.agent_id} -> {tool_name}")
        raise ToolPermissionDenied(agent.agent_id, tool_name)


def requires_tool(tool_name: str) -> Callable:
    """
    Decorator that enforces tool permission before execution.

    The decorated function must receive a BusinessAgent as its first argument.

    Usage:
        @requires_tool("deploy_production")
        def deploy(agent: BusinessAgent, target: str) -> None:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(agent: BusinessAgent, *args: Any, **kwargs: Any) -> Any:
            enforce_permission(agent, tool_name)
            return func(agent, *args, **kwargs)

        return wrapper

    return decorator


class ToolPermissionGate:
    """
    Middleware-style gate that tracks permission checks and denials.

    Useful for auditing which agents attempt which tools.
    """

    def __init__(self) -> None:
        self._checks: list[dict[str, Any]] = []

    def check(self, agent: BusinessAgent, tool_name: str) -> bool:
        """Check permission and record the attempt."""
        allowed = agent.is_tool_allowed(tool_name)
        self._checks.append(
            {
                "agent_id": agent.agent_id,
                "tool": tool_name,
                "allowed": allowed,
            }
        )
        if not allowed:
            logger.info(f"Tool denied: {agent.agent_id} -> {tool_name}")
        return allowed

    @property
    def denied_attempts(self) -> list[dict[str, Any]]:
        """Return all denied permission checks."""
        return [c for c in self._checks if not c["allowed"]]

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """Return full audit log of all permission checks."""
        return list(self._checks)
