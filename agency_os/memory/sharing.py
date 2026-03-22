"""Cross-agent memory sharing.

Agents can discover and read facts from other agents' PARA knowledge graphs.
All access is read-only — agents cannot modify each other's memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .decay import DecayTier, classify_facts, load_facts


@dataclass
class AgentFact:
    """A fact attributed to a specific agent."""

    agent: str
    entity: str
    fact_id: str
    fact: str
    category: str
    tier: DecayTier
    access_count: int


def _validate_agent_name(agents_root: Path, agent_name: str) -> Path:
    """Resolve an agent directory and verify it stays within agents_root.

    Raises ValueError if the resolved path escapes the agents root
    (e.g. agent_name contains '../').
    """
    resolved = (agents_root / agent_name).resolve()
    root_resolved = agents_root.resolve()
    if (
        not str(resolved).startswith(str(root_resolved) + "/")
        and resolved != root_resolved
    ):
        raise ValueError(f"Invalid agent name: {agent_name!r}")
    return resolved


def discover_agents(agents_root: Path) -> list[str]:
    """Discover agent names that have memory directories."""
    if not agents_root.exists():
        return []
    return sorted(
        d.name for d in agents_root.iterdir() if d.is_dir() and (d / "memory").is_dir()
    )


def get_agent_facts(
    agents_root: Path,
    agent_name: str,
    now: float | None = None,
) -> list[AgentFact]:
    """Load all active facts from an agent's PARA knowledge graph."""
    agent_dir = _validate_agent_name(agents_root, agent_name)
    life_dir = agent_dir / "life"
    if not life_dir.exists():
        return []

    results: list[AgentFact] = []
    for items_file in life_dir.rglob("items.yaml"):
        entity_dir = items_file.parent
        entity_name = entity_dir.name

        raw_facts = load_facts(items_file)
        classified = classify_facts(raw_facts, now=now)

        for cf in classified:
            results.append(
                AgentFact(
                    agent=agent_name,
                    entity=entity_name,
                    fact_id=cf.fact_id,
                    fact=cf.fact,
                    category=cf.category,
                    tier=cf.tier,
                    access_count=cf.access_count,
                )
            )
    return results


def get_shared_facts(
    agents_root: Path,
    exclude_agent: str | None = None,
    tier_filter: set[DecayTier] | None = None,
    now: float | None = None,
) -> list[AgentFact]:
    """Gather facts from all agents, optionally filtering by tier.

    Args:
        agents_root: Path to agents/ directory.
        exclude_agent: Skip this agent (typically the requesting agent).
        tier_filter: Only include facts in these tiers (default: hot + warm).
        now: Current timestamp for decay classification.
    """
    if tier_filter is None:
        tier_filter = {DecayTier.hot, DecayTier.warm}

    all_facts: list[AgentFact] = []
    for agent_name in discover_agents(agents_root):
        if agent_name == exclude_agent:
            continue
        facts = get_agent_facts(agents_root, agent_name, now=now)
        all_facts.extend(f for f in facts if f.tier in tier_filter)

    return all_facts


def read_agent_memory(agents_root: Path, agent_name: str) -> str | None:
    """Read another agent's MEMORY.md (tacit knowledge layer)."""
    agent_dir = _validate_agent_name(agents_root, agent_name)
    memory_file = agent_dir / "memory" / "MEMORY.md"
    if memory_file.exists():
        return memory_file.read_text()
    return None
