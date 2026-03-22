"""Response cache for the LLM gateway.

Caches non-streaming completions by content hash. Returns cached
responses instantly at zero inference cost — the gateway still
charges the customer, keeping 100% margin on cache hits.

Includes similarity-based cache lookup using MinHash signatures
so semantically equivalent prompts can hit cache even when phrased
differently.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

# MinHash constants
_NUM_HASHES = 128
_SHINGLE_SIZE = 2
_MAX_HASH = (1 << 32) - 1
# Pre-computed hash seeds for MinHash permutations
_HASH_SEEDS = [struct.pack("<I", i) for i in range(_NUM_HASHES)]

# Explicit family/tier mapping for safe cross-model reuse.
# Higher tier means equal-or-higher capability within a family.
_MODEL_FAMILY_TIER: dict[str, tuple[str, int]] = {
    "gpt-4.1-nano": ("openai:gpt-4.1", 1),
    "gpt-4.1-mini": ("openai:gpt-4.1", 2),
    "gpt-4.1": ("openai:gpt-4.1", 3),
    "gpt-4o-mini": ("openai:gpt-4o", 1),
    "gpt-4o": ("openai:gpt-4o", 2),
    "claude-haiku-4": ("anthropic:claude-4", 1),
    "claude-sonnet-4": ("anthropic:claude-4", 2),
    "claude-opus-4": ("anthropic:claude-4", 3),
    "llama-3.1-8b": ("llama:3.1-8b", 1),
    "groq-llama-3.1-8b": ("llama:3.1-8b", 1),
    "llama-3.1-70b": ("llama:3.1-70b", 2),
    "fireworks-llama-3.1-70b": ("llama:3.1-70b", 2),
    "groq-llama-3.1-70b": ("llama:3.1-70b", 2),
}


def _normalize_text(text: str) -> str:
    """Normalize text for similarity comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shingles(text: str, k: int = _SHINGLE_SIZE) -> set[str]:
    """Extract word n-gram shingles from text."""
    words = text.split()
    if len(words) < k:
        return {text} if text else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _minhash_signature(shingle_set: set[str]) -> tuple[int, ...]:
    """Compute a MinHash signature for a set of shingles."""
    if not shingle_set:
        return tuple([_MAX_HASH] * _NUM_HASHES)
    sig = [_MAX_HASH] * _NUM_HASHES
    for shingle in shingle_set:
        shingle_bytes = shingle.encode("utf-8")
        for i in range(_NUM_HASHES):
            h = int.from_bytes(
                hashlib.md5(  # noqa: S324
                    _HASH_SEEDS[i] + shingle_bytes
                ).digest()[:4],
                "little",
            )
            if h < sig[i]:
                sig[i] = h
    return tuple(sig)


def _jaccard_estimate(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    """Estimate Jaccard similarity from two MinHash signatures."""
    if len(sig_a) != len(sig_b):
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b, strict=False) if a == b)
    return matches / len(sig_a)


@dataclass
class CacheEntry:
    """A cached completion response."""

    response: dict[str, Any]
    model_id: str
    tokens_in: int
    tokens_out: int
    created_at: float
    ttl: float
    hit_count: int = 0

    @property
    def expired(self) -> bool:
        return time.time() > self.created_at + self.ttl


@dataclass
class _SimilarityEntry:
    """Index entry for similarity lookups."""

    cache_key: str
    signature: tuple[int, ...]
    model: str
    model_family: str
    model_tier: int
    max_tokens: int | None
    top_p: float | None
    stop: tuple[str, ...] | None
    tenant_id: str


class ResponseCache:
    """In-memory LRU cache for gateway completions.

    Thread-safe. Bounded by max_entries with LRU eviction.
    Tracks hit rate and cost savings for analytics.

    Supports similarity-based lookups: when an exact cache key misses,
    a MinHash-based search finds semantically similar cached prompts
    above the configured similarity threshold.
    """

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        default_ttl: float = 3600.0,  # 1 hour
        similarity_threshold: float = 0.85,
    ) -> None:
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._similarity_threshold = similarity_threshold
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        # Similarity index: cache_key -> _SimilarityEntry
        self._sim_index: dict[str, _SimilarityEntry] = {}
        # Stats
        self._hits = 0
        self._similarity_hits = 0
        self._misses = 0
        self._cost_saved = 0.0

    @staticmethod
    def _normalize_stop(stop: str | list[str] | None) -> tuple[str, ...] | None:
        if stop is None:
            return None
        if isinstance(stop, str):
            return (stop,)
        return tuple(stop)

    @staticmethod
    def cache_key(
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tenant_id: str = "",
    ) -> str:
        """Generate a deterministic cache key from request parameters.

        Temperature > 0 is considered non-deterministic and not cached
        (caller should skip cache). Temperature == 0 or None is cacheable.

        The tenant_id is included to prevent cross-tenant cache leaks.
        """
        key_data = json.dumps(
            {
                "tenant_id": tenant_id,
                "messages": messages,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "stop": ResponseCache._normalize_stop(stop),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(key_data.encode()).hexdigest()

    @staticmethod
    def _messages_text(messages: list[dict[str, Any]]) -> str:
        """Extract and normalize text from messages for similarity comparison."""
        parts = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            parts.append(f"{role}: {_normalize_text(content)}")
        return " ".join(parts)

    @staticmethod
    def _model_family_and_tier(model: str) -> tuple[str, int]:
        family_tier = _MODEL_FAMILY_TIER.get(model)
        if family_tier is not None:
            return family_tier
        # Unknown models remain isolated to themselves.
        return (f"model:{model}", 0)

    def get(self, key: str) -> CacheEntry | None:
        """Look up a cached response by exact key. Returns None on miss or expiry."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expired:
                self._remove_entry(key)
                self._misses += 1
                return None
            entry.hit_count += 1
            self._hits += 1
            self._cache.move_to_end(key)
            return entry

    def get_similar(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tenant_id: str = "",
        allow_model_family_match: bool = False,
    ) -> CacheEntry | None:
        """Find a cached response by similarity matching.

        Only considers entries for the same tenant and sampling parameters.
        By default, model must match exactly. When ``allow_model_family_match``
        is enabled, same-family entries are allowed only if the cached model
        tier is >= requested model tier.
        Returns the best match above the similarity threshold, or None.
        """
        text = self._messages_text(messages)
        query_sig = _minhash_signature(_shingles(text))
        normalized_stop = self._normalize_stop(stop)
        query_family, query_tier = self._model_family_and_tier(model)

        with self._lock:
            best_key: str | None = None
            best_score = 0.0

            for sim_entry in self._sim_index.values():
                # Enforce tenant isolation and sampling parameter matching.
                if sim_entry.tenant_id != tenant_id:
                    continue
                if sim_entry.model != model:
                    if not allow_model_family_match:
                        continue
                    if sim_entry.model_family != query_family:
                        continue
                    if sim_entry.model_tier < query_tier:
                        continue
                if sim_entry.max_tokens != max_tokens:
                    continue
                if sim_entry.top_p != top_p:
                    continue
                if sim_entry.stop != normalized_stop:
                    continue

                score = _jaccard_estimate(query_sig, sim_entry.signature)
                if score > best_score:
                    best_score = score
                    best_key = sim_entry.cache_key

            if best_key is None or best_score < self._similarity_threshold:
                return None

            entry = self._cache.get(best_key)
            if entry is None or entry.expired:
                if entry is not None:
                    self._remove_entry(best_key)
                return None

            entry.hit_count += 1
            self._similarity_hits += 1
            self._cache.move_to_end(best_key)
            return entry

    def put(
        self,
        key: str,
        response: dict[str, Any],
        model_id: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float = 0.0,
        ttl: float | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        tenant_id: str = "",
    ) -> None:
        """Store a response in the cache.

        If messages are provided, also builds a similarity index entry
        so future similar prompts can match this cached response.
        """
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_entries:
                evicted_key, _ = self._cache.popitem(last=False)
                self._sim_index.pop(evicted_key, None)

            self._cache[key] = CacheEntry(
                response=response,
                model_id=model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                created_at=time.time(),
                ttl=ttl or self._default_ttl,
            )

            # Build similarity index entry
            if messages is not None:
                text = self._messages_text(messages)
                sig = _minhash_signature(_shingles(text))
                self._sim_index[key] = _SimilarityEntry(
                    cache_key=key,
                    signature=sig,
                    model=model_id,
                    model_family=self._model_family_and_tier(model_id)[0],
                    model_tier=self._model_family_and_tier(model_id)[1],
                    max_tokens=max_tokens,
                    top_p=top_p,
                    stop=self._normalize_stop(stop),
                    tenant_id=tenant_id,
                )

    def _remove_entry(self, key: str) -> None:
        """Remove an entry from both cache and similarity index (caller holds lock)."""
        self._cache.pop(key, None)
        self._sim_index.pop(key, None)

    def record_cost_saved(self, amount: float) -> None:
        """Record cost savings from a cache hit."""
        with self._lock:
            self._cost_saved += amount

    @property
    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._similarity_hits + self._misses
            return {
                "hits": self._hits,
                "similarity_hits": self._similarity_hits,
                "misses": self._misses,
                "hit_rate": (
                    round((self._hits + self._similarity_hits) / total, 4)
                    if total > 0
                    else 0.0
                ),
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "similarity_index_size": len(self._sim_index),
                "cost_saved_usd": round(self._cost_saved, 4),
            }
