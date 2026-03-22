"""NEXUS 7-phase pipeline adapter — maps agency-agents NEXUS strategy to workflow engine."""

from __future__ import annotations

# Standard NEXUS phases (from agency-agents/strategy/nexus-strategy.md)
NEXUS_PHASES = [
    "discovery",
    "strategy",
    "foundation",
    "build",
    "hardening",
    "launch",
    "operate",
]


def is_nexus_pipeline(pipeline: str) -> bool:
    """Check if a pipeline name is a NEXUS variant."""
    return pipeline.startswith("nexus")


def get_nexus_phase_index(phase_name: str) -> int:
    """Get the index of a NEXUS phase (-1 if not a standard phase)."""
    try:
        return NEXUS_PHASES.index(phase_name.lower())
    except ValueError:
        return -1
