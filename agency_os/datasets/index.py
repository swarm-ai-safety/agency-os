"""In-memory content index with BM25 search for dataset chunks.

Provides the retrieval backbone for content swarm agents. Uses the same
BM25 approach as agency_os.memory.retrieval but specialized for content
dataset chunks with richer metadata filtering.
"""

from __future__ import annotations

import math
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .chunker import ChunkMeta


@dataclass
class SearchHit:
    """A scored search result from the content index."""

    chunk: ChunkMeta
    score: float
    matched_terms: list[str] = field(default_factory=list)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


class ContentIndex:
    """BM25 search index over content dataset chunks.

    Usage::

        index = ContentIndex()
        index.build(chunks)
        results = index.search("product-market fit", limit=10)

        # Save/load for persistence
        index.save(Path("build/lenny.idx"))
        index = ContentIndex.load(Path("build/lenny.idx"))
    """

    def __init__(self) -> None:
        self._chunks: list[ChunkMeta] = []
        self._doc_tokens: list[list[str]] = []
        self._doc_freqs: dict[str, int] = {}
        self._avg_dl: float = 0.0

    @property
    def size(self) -> int:
        return len(self._chunks)

    def build(self, chunks: list[ChunkMeta]) -> None:
        """Build the BM25 index from a list of chunks."""
        self._chunks = list(chunks)
        self._doc_tokens = []
        self._doc_freqs = {}

        total_len = 0
        for chunk in self._chunks:
            # Index text + metadata fields for richer matching
            combined = (
                f"{chunk.text} {chunk.title} {chunk.guest} "
                f"{chunk.heading} {chunk.content_type}"
            )
            tokens = _tokenize(combined)
            self._doc_tokens.append(tokens)
            total_len += len(tokens)
            for term in set(tokens):
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        n = len(self._chunks)
        self._avg_dl = total_len / n if n > 0 else 1.0

    def search(
        self,
        query: str,
        limit: int = 10,
        content_type: Optional[str] = None,
        guest: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[SearchHit]:
        """Search the index with optional metadata filters.

        Args:
            query: Natural language search query.
            limit: Maximum results to return.
            content_type: Filter to "newsletter" or "podcast".
            guest: Filter to a specific podcast guest.
            date_from: Include only docs on or after this date (YYYY-MM-DD).
            date_to: Include only docs on or before this date (YYYY-MM-DD).
        """
        query_tokens = _tokenize(query)
        if not query_tokens or not self._chunks:
            return []

        scored: list[SearchHit] = []

        for i, chunk in enumerate(self._chunks):
            # Apply metadata filters
            if content_type and chunk.content_type != content_type:
                continue
            if guest and guest.lower() not in chunk.guest.lower():
                continue
            if date_from:
                if not chunk.date or chunk.date < date_from:
                    continue
            if date_to:
                if not chunk.date or chunk.date > date_to:
                    continue

            score, matched = self._bm25_score(query_tokens, self._doc_tokens[i])
            if score > 0:
                scored.append(
                    SearchHit(chunk=chunk, score=score, matched_terms=matched)
                )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def _bm25_score(
        self,
        query_tokens: list[str],
        doc_tokens: list[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> tuple[float, list[str]]:
        """BM25 scoring for a single document against a query."""
        score = 0.0
        dl = len(doc_tokens)
        n_docs = len(self._chunks)
        matched: list[str] = []

        for term in query_tokens:
            tf = doc_tokens.count(term)
            if tf == 0:
                continue
            matched.append(term)
            df = self._doc_freqs.get(term, 0)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / self._avg_dl))
            score += idf * tf_norm

        return score, matched

    def save(self, path: Path) -> None:
        """Persist the index to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "chunks": self._chunks,
            "doc_tokens": self._doc_tokens,
            "doc_freqs": self._doc_freqs,
            "avg_dl": self._avg_dl,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load(cls, path: Path) -> ContentIndex:
        """Load a persisted index from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        idx = cls()
        idx._chunks = data["chunks"]
        idx._doc_tokens = data["doc_tokens"]
        idx._doc_freqs = data["doc_freqs"]
        idx._avg_dl = data["avg_dl"]
        return idx
