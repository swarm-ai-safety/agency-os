"""Structured agent memory: decay, cross-agent sharing, and fact retrieval."""

from .decay import (
    DecayResult,
    DecayTier,
    classify_facts,
    classify_tier,
    load_facts,
    run_decay_sweep,
    synthesize_summary,
)
from .retrieval import FactIndex, SearchResult, recall
from .sharing import (
    AgentFact,
    discover_agents,
    get_agent_facts,
    get_shared_facts,
    read_agent_memory,
)

__all__ = [
    "AgentFact",
    "DecayResult",
    "DecayTier",
    "FactIndex",
    "SearchResult",
    "classify_facts",
    "classify_tier",
    "discover_agents",
    "get_agent_facts",
    "get_shared_facts",
    "load_facts",
    "read_agent_memory",
    "recall",
    "run_decay_sweep",
    "synthesize_summary",
]
