"""Routing feedback loop — tracks eval scores per model per complexity tier.

After each request, callers record eval scores (quality, latency, etc.)
for the model that handled it. The RoutingFeedback component maintains
rolling averages and provides model rankings that the SmartRouter
consults when choosing models.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class EvalRecord:
    """A single eval score observation."""

    model_id: str
    complexity: str  # "simple", "medium", "complex"
    score: float  # 0.0–1.0 normalized quality score
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelStats:
    """Rolling statistics for a model within a complexity tier."""

    total_score: float = 0.0
    count: int = 0
    total_latency_ms: float = 0.0
    latency_count: int = 0
    success_count: int = 0
    total_attempts: int = 0

    @property
    def avg_score(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_score / self.count

    @property
    def avg_latency_ms(self) -> float | None:
        if self.latency_count == 0:
            return None
        return self.total_latency_ms / self.latency_count

    @property
    def reliability(self) -> float | None:
        if self.total_attempts == 0:
            return None
        return self.success_count / self.total_attempts


@dataclass(frozen=True)
class RoutingWeights:
    """Relative importance of quality, reliability, latency, and cost."""

    quality: float = 0.45
    reliability: float = 0.30
    latency: float = 0.15
    cost: float = 0.10

    def normalized(self) -> "RoutingWeights":
        total = self.quality + self.reliability + self.latency + self.cost
        if total <= 0:
            return RoutingWeights()
        return RoutingWeights(
            quality=self.quality / total,
            reliability=self.reliability / total,
            latency=self.latency / total,
            cost=self.cost / total,
        )


class RoutingFeedback:
    """Tracks eval scores per model per complexity tier.

    Records are kept in a bounded buffer. Stats are maintained as
    rolling averages per (model_id, complexity) pair.

    Thread-safe: all mutations and reads are protected by a lock.
    """

    _MAX_RECORDS = 10_000
    _MIN_SAMPLES = 5  # minimum observations before we trust a model's score

    def __init__(
        self,
        *,
        max_records: int = _MAX_RECORDS,
        min_samples: int = _MIN_SAMPLES,
        decay_seconds: float = 86400.0,  # 24h — records older than this are discounted
        model_cost_per_1k: dict[str, float] | None = None,
        weights: RoutingWeights | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._records: list[EvalRecord] = []
        self._max_records = max_records
        self._min_samples = min_samples
        self._decay_seconds = decay_seconds
        self._model_cost_per_1k = model_cost_per_1k or {}
        self._weights = (weights or RoutingWeights()).normalized()
        # (model_id, complexity) -> ModelStats
        self._stats: dict[tuple[str, str], ModelStats] = defaultdict(ModelStats)

    def record(
        self,
        model_id: str,
        complexity: str,
        score: float,
        *,
        latency_ms: float | None = None,
        success: bool | None = None,
        **metadata: Any,
    ) -> None:
        """Record an eval score for a model at a given complexity tier."""
        # Allow callers to pass via metadata for backward compatibility.
        if latency_ms is None and "latency_ms" in metadata:
            try:
                latency_ms = float(metadata["latency_ms"])
            except (TypeError, ValueError):
                latency_ms = None
        if success is None and "success" in metadata:
            success = bool(metadata["success"])

        record_metadata = dict(metadata)
        if latency_ms is not None:
            record_metadata["latency_ms"] = latency_ms
        if success is not None:
            record_metadata["success"] = success

        rec = EvalRecord(
            model_id=model_id,
            complexity=complexity,
            score=max(0.0, min(1.0, score)),
            metadata=record_metadata,
        )
        with self._lock:
            if len(self._records) >= self._max_records:
                self._compact()
            self._records.append(rec)
            key = (model_id, complexity)
            self._stats[key].total_score += rec.score
            self._stats[key].count += 1
            if latency_ms is not None and latency_ms >= 0:
                self._stats[key].total_latency_ms += latency_ms
                self._stats[key].latency_count += 1
            if success is not None:
                self._stats[key].total_attempts += 1
                if success:
                    self._stats[key].success_count += 1

    def get_model_ranking(self, complexity: str, candidates: list[str]) -> list[str]:
        """Rank candidate models by eval performance for a complexity tier.

        Only models with >= min_samples observations are ranked by score.
        Models with insufficient data keep their original order (heuristic fallback).

        Returns:
            Reordered list of model_ids — best performing first, then
            unscored models in their original order.
        """
        with self._lock:
            scored: list[tuple[str, float]] = []
            unscored: list[str] = []
            candidate_stats: dict[str, ModelStats] = {}

            for model_id in candidates:
                key = (model_id, complexity)
                stats = self._stats.get(key)
                if stats and stats.count >= self._min_samples:
                    candidate_stats[model_id] = stats
                else:
                    unscored.append(model_id)

            if not candidate_stats:
                return unscored

            quality = {m: s.avg_score for m, s in candidate_stats.items()}
            latency = {m: s.avg_latency_ms for m, s in candidate_stats.items()}
            reliability = {m: s.reliability for m, s in candidate_stats.items()}
            cost = {m: self._model_cost_per_1k.get(m) for m in candidate_stats}

            quality_norm = self._normalize_metric(quality, higher_is_better=True)
            latency_norm = self._normalize_metric(latency, higher_is_better=False)
            reliability_norm = self._normalize_metric(
                reliability, higher_is_better=True
            )
            cost_norm = self._normalize_metric(cost, higher_is_better=False)

            w = self._weights
            for model_id in candidate_stats:
                composite = (
                    w.quality * quality_norm[model_id]
                    + w.reliability * reliability_norm[model_id]
                    + w.latency * latency_norm[model_id]
                    + w.cost * cost_norm[model_id]
                )
                scored.append((model_id, composite))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [m for m, _ in scored] + unscored

    def get_stats(self, model_id: str, complexity: str) -> dict[str, Any]:
        """Get stats for a specific model/complexity pair."""
        with self._lock:
            key = (model_id, complexity)
            stats = self._stats.get(key)
            if stats is None:
                return {
                    "model_id": model_id,
                    "complexity": complexity,
                    "count": 0,
                    "avg_score": None,
                    "avg_latency_ms": None,
                    "reliability": None,
                }
            return {
                "model_id": model_id,
                "complexity": complexity,
                "count": stats.count,
                "avg_score": round(stats.avg_score, 4),
                "avg_latency_ms": (
                    round(stats.avg_latency_ms, 2)
                    if stats.avg_latency_ms is not None
                    else None
                ),
                "reliability": (
                    round(stats.reliability, 4)
                    if stats.reliability is not None
                    else None
                ),
            }

    def get_all_stats(self) -> list[dict[str, Any]]:
        """Get stats for all tracked model/complexity pairs."""
        with self._lock:
            result = []
            for (model_id, complexity), stats in self._stats.items():
                result.append(
                    {
                        "model_id": model_id,
                        "complexity": complexity,
                        "count": stats.count,
                        "avg_score": round(stats.avg_score, 4),
                        "avg_latency_ms": (
                            round(stats.avg_latency_ms, 2)
                            if stats.avg_latency_ms is not None
                            else None
                        ),
                        "reliability": (
                            round(stats.reliability, 4)
                            if stats.reliability is not None
                            else None
                        ),
                    }
                )
            return result

    @property
    def total_records(self) -> int:
        with self._lock:
            return len(self._records)

    def _compact(self) -> None:
        """Drop oldest 10% of records and rebuild stats."""
        drop_count = self._max_records // 10
        self._records = self._records[drop_count:]
        self._stats.clear()
        for rec in self._records:
            key = (rec.model_id, rec.complexity)
            self._stats[key].total_score += rec.score
            self._stats[key].count += 1
            latency = rec.metadata.get("latency_ms")
            if isinstance(latency, (int, float)) and latency >= 0:
                self._stats[key].total_latency_ms += float(latency)
                self._stats[key].latency_count += 1
            success = rec.metadata.get("success")
            if isinstance(success, bool):
                self._stats[key].total_attempts += 1
                if success:
                    self._stats[key].success_count += 1

    @staticmethod
    def _normalize_metric(
        values: Mapping[str, float | None], *, higher_is_better: bool
    ) -> dict[str, float]:
        """Min-max normalize metric values, with neutral fill for missing data."""
        present = [v for v in values.values() if v is not None]
        if not present:
            return dict.fromkeys(values, 0.5)
        low = min(present)
        high = max(present)
        if high == low:
            return dict.fromkeys(values, 0.5)

        normalized: dict[str, float] = {}
        for key, value in values.items():
            if value is None:
                normalized[key] = 0.5
                continue
            score = (value - low) / (high - low)
            normalized[key] = score if higher_is_better else 1.0 - score
        return normalized
