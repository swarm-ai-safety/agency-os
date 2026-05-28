"""Git ref helpers for agent workspaces."""

from __future__ import annotations

import re

_SAFE_REF_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_DUP_SEPARATORS = re.compile(r"[./]{2,}")


def sanitize_ref_component(value: str) -> str:
    """Normalize user or model supplied ids into a safe git ref component."""
    cleaned = _SAFE_REF_CHARS.sub("-", value.strip())
    cleaned = _DUP_SEPARATORS.sub("-", cleaned)
    cleaned = cleaned.strip("./-")
    return cleaned[:80] or "unknown"


def agent_ref(agent_id: str, task_id: str) -> str:
    """Return the canonical namespace for delegated agent work."""
    return (
        "refs/agents/"
        f"{sanitize_ref_component(agent_id)}/"
        f"{sanitize_ref_component(task_id)}"
    )
