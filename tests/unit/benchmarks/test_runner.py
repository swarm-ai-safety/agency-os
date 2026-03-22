"""Tests for the benchmark runner."""

import json
import tempfile
from pathlib import Path

from agency_os.benchmarks.runner import (
    PROTOCOL_REGISTRY,
    run_benchmarks,
)


class TestBenchmarkRunner:
    def test_run_all_protocols(self):
        report = run_benchmarks()
        assert len(report.protocol_results) == len(PROTOCOL_REGISTRY)
        assert report.duration_seconds > 0
        assert 0.0 <= report.economic_capability <= 1.0
        assert 0.0 <= report.governance_safety <= 1.0

    def test_run_single_protocol(self):
        report = run_benchmarks(protocols=["delegated_spending"])
        assert len(report.protocol_results) == 1
        assert "delegated_spending" in report.protocol_results

    def test_run_multiple_protocols(self):
        report = run_benchmarks(protocols=["delegated_spending", "prompt_injection"])
        assert len(report.protocol_results) == 2

    def test_unknown_protocol_skipped(self):
        report = run_benchmarks(protocols=["nonexistent_protocol"])
        assert len(report.protocol_results) == 0

    def test_report_summary(self):
        report = run_benchmarks(protocols=["delegated_spending"])
        summary = report.summary()
        assert "timestamp" in summary
        assert "duration_seconds" in summary
        assert "economic_capability" in summary
        assert "governance_safety" in summary
        assert "protocols" in summary

    def test_report_save_and_load(self):
        report = run_benchmarks(protocols=["delegated_spending"])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            report.save(path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert "protocols" in data
            assert "delegated_spending" in data["protocols"]


class TestProtocolRegistry:
    def test_all_protocols_registered(self):
        expected = {
            "delegated_spending",
            "prompt_injection",
            "multi_agent_collusion",
            "escrow_milestones",
            "authority_boundaries",
            "cross_rail_routing",
            "swarm_treasury",
        }
        assert set(PROTOCOL_REGISTRY.keys()) == expected

    def test_all_protocols_instantiate(self):
        for _name, cls in PROTOCOL_REGISTRY.items():
            instance = cls()
            assert hasattr(instance, "run")

    def test_all_protocols_produce_metrics(self):
        for _name, cls in PROTOCOL_REGISTRY.items():
            bench = cls()
            metrics = bench.run()
            assert metrics.protocol_name
            assert metrics.total_tasks > 0
