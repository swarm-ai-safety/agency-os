"""Structured fact retrieval with BM25-style keyword search.

Provides in-process keyword search across agent PARA knowledge graphs
without requiring external services. Uses term frequency with inverse
document frequency (TF-IDF / BM25) scoring for relevance ranking.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .sharing import AgentFact, discover_agents, get_agent_facts


@dataclass
class SearchResult:
    """A scored search result."""

    fact: AgentFact
    score: float
    matched_terms: list[str] = field(default_factory=list)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, stripping punctuation."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _term_freq(term: str, tokens: list[str]) -> float:
    """Raw term frequency."""
    return tokens.count(term)


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freqs: dict[str, int],
    n_docs: int,
    avg_dl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> tuple[float, list[str]]:
    """BM25 score for a single document against a query."""
    score = 0.0
    dl = len(doc_tokens)
    matched = []

    for term in query_tokens:
        tf = _term_freq(term, doc_tokens)
        if tf == 0:
            continue
        matched.append(term)
        df = doc_freqs.get(term, 0)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        score += idf * tf_norm

    return score, matched


class FactIndex:
    """In-memory BM25 index over agent facts."""

    def __init__(self) -> None:
        self._facts: list[AgentFact] = []
        self._doc_tokens: list[list[str]] = []
        self._doc_freqs: dict[str, int] = {}
        self._avg_dl: float = 0.0

    def build(self, facts: list[AgentFact]) -> None:
        """Build the index from a list of facts."""
        self._facts = list(facts)
        self._doc_tokens = []
        self._doc_freqs = {}

        total_len = 0
        for fact in self._facts:
            tokens = _tokenize(f"{fact.fact} {fact.entity} {fact.category}")
            self._doc_tokens.append(tokens)
            total_len += len(tokens)
            seen = set(tokens)
            for term in seen:
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        n = len(self._facts)
        self._avg_dl = total_len / n if n > 0 else 1.0

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search the index for facts matching a query."""
        query_tokens = _tokenize(query)
        if not query_tokens or not self._facts:
            return []

        scored: list[SearchResult] = []
        n_docs = len(self._facts)

        for i, fact in enumerate(self._facts):
            score, matched = _bm25_score(
                query_tokens,
                self._doc_tokens[i],
                self._doc_freqs,
                n_docs,
                self._avg_dl,
            )
            if score > 0:
                scored.append(
                    SearchResult(fact=fact, score=score, matched_terms=matched)
                )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]


def recall(
    query: str,
    agents_root: Path,
    agent_names: list[str] | None = None,
    limit: int = 10,
    now: float | None = None,
) -> list[SearchResult]:
    """Search across agent knowledge graphs for facts matching a query.

    This is the main entry point for structured fact retrieval (qmd recall).

    Args:
        query: Natural language search query.
        agents_root: Path to agents/ directory.
        agent_names: Specific agents to search (default: all).
        limit: Max results to return.
        now: Current timestamp for decay classification.
    """
    if agent_names is None:
        agent_names = discover_agents(agents_root)

    all_facts: list[AgentFact] = []
    for name in agent_names:
        all_facts.extend(get_agent_facts(agents_root, name, now=now))

    if not all_facts:
        return []

    index = FactIndex()
    index.build(all_facts)
    return index.search(query, limit=limit)
