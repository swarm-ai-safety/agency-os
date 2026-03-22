"""Benchmark runner: execute all protocols and produce a consolidated report."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agency_os.benchmarks.metrics import ProtocolMetrics
from agency_os.benchmarks.protocols.p1_delegated_spending import (
    DelegatedSpendingBenchmark,
)
from agency_os.benchmarks.protocols.p2_prompt_injection import PromptInjectionBenchmark
from agency_os.benchmarks.protocols.p3_multi_agent_collusion import (
    MultiAgentCollusionBenchmark,
)
from agency_os.benchmarks.protocols.p4_escrow_milestones import EscrowMilestoneBenchmark
from agency_os.benchmarks.protocols.p5_authority_boundaries import (
    AuthorityBoundaryBenchmark,
)
from agency_os.benchmarks.protocols.p6_cross_rail_routing import (
    CrossRailRoutingBenchmark,
)
from agency_os.benchmarks.protocols.p7_swarm_treasury import SwarmTreasuryBenchmark

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkReport:
    """Consolidated report from running all (or selected) protocols."""

    timestamp: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    protocol_results: dict[str, ProtocolMetrics] = field(default_factory=dict)

    @property
    def economic_capability(self) -> float:
        """Average economic capability across all protocols."""
        if not self.protocol_results:
            return 0.0
        return sum(m.economic_capability for m in self.protocol_results.values()) / len(
            self.protocol_results
        )

    @property
    def governance_safety(self) -> float:
        """Average governance safety across all protocols."""
        if not self.protocol_results:
            return 0.0
        return sum(m.governance_safety for m in self.protocol_results.values()) / len(
            self.protocol_results
        )

    def summary(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "economic_capability": self.economic_capability,
            "governance_safety": self.governance_safety,
            "protocols": {
                name: metrics.summary()
                for name, metrics in self.protocol_results.items()
            },
        }

    def save(self, path: str | Path) -> None:
        """Save report as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.summary(), indent=2, default=str))
        logger.info("Benchmark report saved to %s", path)


# Registry of all benchmark protocols
PROTOCOL_REGISTRY: dict[str, type] = {
    "delegated_spending": DelegatedSpendingBenchmark,
    "prompt_injection": PromptInjectionBenchmark,
    "multi_agent_collusion": MultiAgentCollusionBenchmark,
    "escrow_milestones": EscrowMilestoneBenchmark,
    "authority_boundaries": AuthorityBoundaryBenchmark,
    "cross_rail_routing": CrossRailRoutingBenchmark,
    "swarm_treasury": SwarmTreasuryBenchmark,
}


def run_benchmarks(
    protocols: list[str] | None = None,
) -> BenchmarkReport:
    """Run benchmark protocols and return a consolidated report.

    Args:
        protocols: List of protocol names to run. If None, runs all.

    Returns:
        BenchmarkReport with results from all executed protocols.
    """
    if protocols is None:
        protocols = list(PROTOCOL_REGISTRY.keys())

    report = BenchmarkReport()
    start = time.time()

    for name in protocols:
        bench_cls = PROTOCOL_REGISTRY.get(name)
        if bench_cls is None:
            logger.warning("Unknown protocol: %s (skipping)", name)
            continue

        logger.info("Running protocol: %s", name)
        bench = bench_cls()
        metrics = bench.run()
        report.protocol_results[name] = metrics
        logger.info(
            "Protocol %s complete: capability=%.3f, safety=%.3f",
            name,
            metrics.economic_capability,
            metrics.governance_safety,
        )

    report.duration_seconds = time.time() - start
    return report
