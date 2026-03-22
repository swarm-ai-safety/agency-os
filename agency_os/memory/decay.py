"""Memory decay engine for PARA-based agent knowledge graphs.

Implements retrieval-priority decay based on access recency and frequency.
Facts are never deleted — they only lose retrieval priority over time.

Decay tiers:
  - hot:  accessed in last 7 days — included prominently in summary
  - warm: accessed 8-30 days ago — included at lower priority
  - cold: 30+ days or never accessed — omitted from summary, still in items.yaml
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class DecayTier(str, Enum):
    hot = "hot"
    warm = "warm"
    cold = "cold"


# Thresholds in seconds
_HOT_WINDOW = 7 * 86400  # 7 days
_WARM_WINDOW = 30 * 86400  # 30 days
# High-access facts resist decay: if access_count >= this, bump one tier warmer
_HIGH_ACCESS_THRESHOLD = 10


@dataclass
class DecayResult:
    """Result of classifying a single fact's decay tier."""

    fact_id: str
    fact: str
    tier: DecayTier
    last_accessed: float | None
    access_count: int
    category: str
    status: str


def classify_tier(
    last_accessed: float | None,
    access_count: int,
    now: float | None = None,
) -> DecayTier:
    """Classify a fact into a decay tier based on access metadata."""
    if now is None:
        now = time.time()

    if last_accessed is None:
        base = DecayTier.cold
    else:
        age = now - last_accessed
        if age <= _HOT_WINDOW:
            base = DecayTier.hot
        elif age <= _WARM_WINDOW:
            base = DecayTier.warm
        else:
            base = DecayTier.cold

    # High access_count resists decay by one tier
    if access_count >= _HIGH_ACCESS_THRESHOLD and base != DecayTier.hot:
        if base == DecayTier.cold:
            return DecayTier.warm
        if base == DecayTier.warm:
            return DecayTier.hot
    return base


def load_facts(items_path: Path) -> list[dict[str, Any]]:
    """Load facts from a PARA items.yaml file."""
    if not items_path.exists():
        return []
    text = items_path.read_text()
    if not text.strip():
        return []
    data = yaml.safe_load(text)
    if not isinstance(data, list):
        return []
    return data


def classify_facts(
    facts: list[dict[str, Any]],
    now: float | None = None,
) -> list[DecayResult]:
    """Classify all facts in a list by decay tier."""
    results = []
    for fact in facts:
        if fact.get("status") == "superseded":
            continue
        tier = classify_tier(
            last_accessed=fact.get("last_accessed"),
            access_count=fact.get("access_count", 0),
            now=now,
        )
        results.append(
            DecayResult(
                fact_id=fact.get("id", ""),
                fact=fact.get("fact", ""),
                tier=tier,
                last_accessed=fact.get("last_accessed"),
                access_count=fact.get("access_count", 0),
                category=fact.get("category", ""),
                status=fact.get("status", "active"),
            )
        )
    return results


def synthesize_summary(
    facts: list[DecayResult],
    entity_name: str = "",
    include_cold: bool = False,
) -> str:
    """Generate a summary.md from classified facts, sorted by tier then access_count.

    Hot facts appear first, then warm. Cold facts are omitted by default.
    Within each tier, facts are sorted by access_count descending.
    """
    tiers_to_include = [DecayTier.hot, DecayTier.warm]
    if include_cold:
        tiers_to_include.append(DecayTier.cold)

    lines: list[str] = []
    if entity_name:
        lines.append(f"# {entity_name}")
        lines.append("")

    for tier in tiers_to_include:
        tier_facts = sorted(
            [f for f in facts if f.tier == tier],
            key=lambda f: f.access_count,
            reverse=True,
        )
        if not tier_facts:
            continue
        lines.append(f"## {tier.value.title()} ({len(tier_facts)})")
        lines.append("")
        for f in tier_facts:
            lines.append(f"- {f.fact}")
        lines.append("")

    return "\n".join(lines)


def run_decay_sweep(
    agent_home: Path,
    now: float | None = None,
    write: bool = True,
) -> dict[str, list[DecayResult]]:
    """Run memory decay across all entities in an agent's PARA knowledge graph.

    Scans $AGENT_HOME/life/ for entity directories containing items.yaml.
    Classifies all facts by decay tier and optionally rewrites summary.md files.

    Returns a dict mapping entity path (relative) to classified facts.
    """
    life_dir = agent_home / "life"
    if not life_dir.exists():
        return {}

    results: dict[str, list[DecayResult]] = {}

    for items_file in life_dir.rglob("items.yaml"):
        entity_dir = items_file.parent
        entity_name = entity_dir.name
        rel_path = str(entity_dir.relative_to(life_dir))

        facts = load_facts(items_file)
        classified = classify_facts(facts, now=now)
        results[rel_path] = classified

        if write and classified:
            summary = synthesize_summary(classified, entity_name=entity_name)
            summary_path = entity_dir / "summary.md"
            summary_path.write_text(summary)

    return results
