#!/usr/bin/env python3
"""Interactive query interface for the Lenny content index.

Demonstrates single-agent retrieval (baseline) and multi-agent swarm
retrieval with competing retrievers, analysts, critics, and a synthesizer.

Usage:
    # Single-agent mode (BM25 search + display)
    python scripts/lenny_query.py --index build/lenny.idx

    # Swarm mode (multi-agent with LLM)
    python scripts/lenny_query.py --index build/lenny.idx --swarm

    # Filter by content type
    python scripts/lenny_query.py --index build/lenny.idx --type podcast
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agency_os.datasets.index import ContentIndex, SearchHit


def display_hits(hits: list[SearchHit], verbose: bool = False) -> None:
    """Pretty-print search results."""
    if not hits:
        print("  No results found.")
        return

    for i, hit in enumerate(hits, 1):
        c = hit.chunk
        print(f"\n  [{i}] {c.source_ref}")
        print(
            f"      Score: {hit.score:.3f} | Type: {c.content_type} | Chunk {c.chunk_index + 1}/{c.total_chunks}"
        )
        if c.heading:
            print(f"      Section: {c.heading}")
        print(f"      Matched: {', '.join(hit.matched_terms[:8])}")
        if verbose:
            preview = c.text[:500].replace("\n", " ")
            print(f"      Preview: {preview}...")


def run_swarm_query(
    query: str,
    index: ContentIndex,
    content_type: str | None,
) -> None:
    """Run a multi-agent swarm query (simulated without LLM).

    Demonstrates the swarm architecture:
    1. Multiple retrievers with different strategies
    2. Results are scored and merged
    3. Critic evaluates retrieval quality
    4. Synthesizer produces final output
    """
    print("\n=== SWARM QUERY ===")
    print(f"Query: {query}\n")

    # --- Retriever Swarm (3 variants) ---
    print("--- Retriever Swarm (3 strategies) ---")

    # Retriever A: broad search, more results
    hits_a = index.search(query, limit=10, content_type=content_type)
    print(
        f"  Retriever A (broad):    {len(hits_a)} hits, top score: {hits_a[0].score:.3f}"
        if hits_a
        else "  Retriever A: 0 hits"
    )

    # Retriever B: tight search, fewer results
    hits_b = index.search(query, limit=5, content_type=content_type)
    print(
        f"  Retriever B (focused):  {len(hits_b)} hits, top score: {hits_b[0].score:.3f}"
        if hits_b
        else "  Retriever B: 0 hits"
    )

    # Retriever C: type-filtered (opposite type for diversity)
    alt_type = (
        "podcast"
        if content_type == "newsletter"
        else "newsletter"
        if content_type == "podcast"
        else None
    )
    hits_c = index.search(query, limit=5, content_type=alt_type)
    print(
        f"  Retriever C (diverse):  {len(hits_c)} hits, top score: {hits_c[0].score:.3f}"
        if hits_c
        else "  Retriever C: 0 hits"
    )

    # --- Reciprocal Rank Fusion ---
    print("\n--- Rank Fusion ---")
    fused = _reciprocal_rank_fusion([hits_a, hits_b, hits_c], k=60)
    print(f"  Fused results: {len(fused)} unique chunks")

    # --- Critic Evaluation ---
    print("\n--- Critic Evaluation ---")
    for hit in fused[:5]:
        # Simple heuristic critic: score based on match density
        match_density = len(hit.matched_terms) / max(1, len(query.split()))
        groundedness = min(1.0, match_density)
        relevance = min(1.0, hit.score / (fused[0].score if fused else 1.0))
        verdict = "pass" if groundedness > 0.5 and relevance > 0.6 else "revise"
        print(
            f"  {hit.chunk.filename}: groundedness={groundedness:.2f} relevance={relevance:.2f} → {verdict}"
        )

    # --- Final Synthesis ---
    print("\n--- Synthesized Answer ---")
    print("  Top sources for this query:\n")
    for i, hit in enumerate(fused[:5], 1):
        c = hit.chunk
        print(f"  {i}. {c.source_ref}")
        print(f"     [{c.content_type}] Score: {hit.score:.3f}")
        preview = c.text[:200].replace("\n", " ").strip()
        print(f'     "{preview}..."\n')

    print("  Swarm telemetry:")
    print(f"    Retrievers: 3 | Unique chunks: {len(fused)}")
    print(f"    Answer variance: {_answer_variance(fused[:5]):.3f}")
    types_seen = {h.chunk.content_type for h in fused[:5]}
    print(f"    Source diversity: {len(types_seen)} type(s) — {', '.join(types_seen)}")


def _reciprocal_rank_fusion(
    hit_lists: list[list[SearchHit]], k: int = 60
) -> list[SearchHit]:
    """Merge multiple ranked lists using reciprocal rank fusion."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, SearchHit] = {}

    for hits in hit_lists:
        for rank, hit in enumerate(hits):
            cid = hit.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            # Keep the hit with the best original score
            if cid not in chunk_map or hit.score > chunk_map[cid].score:
                chunk_map[cid] = hit

    # Sort by fused score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        SearchHit(
            chunk=chunk_map[cid].chunk,
            score=fused_score,
            matched_terms=chunk_map[cid].matched_terms,
        )
        for cid, fused_score in ranked
    ]


def _answer_variance(hits: list[SearchHit]) -> float:
    """Measure how much the top results disagree (score spread)."""
    if len(hits) < 2:
        return 0.0
    scores = [h.score for h in hits]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    return variance


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Lenny content index.")
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("build/lenny.idx"),
        help="Path to the search index",
    )
    parser.add_argument("--type", choices=["newsletter", "podcast"], default=None)
    parser.add_argument(
        "--swarm", action="store_true", help="Use multi-agent swarm mode"
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.index.exists():
        print(f"Error: Index not found at {args.index}")
        print("Run ingestion first: python scripts/lenny_ingest.py")
        sys.exit(1)

    index = ContentIndex.load(args.index)
    print(f"Loaded index with {index.size} chunks")
    mode = "swarm" if args.swarm else "single"
    print(f"Mode: {mode}\n")

    while True:
        try:
            query = input("Ask: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query or query.lower() in ("exit", "quit", "q"):
            break

        if args.swarm:
            run_swarm_query(query, index, args.type)
        else:
            hits = index.search(query, limit=args.limit, content_type=args.type)
            display_hits(hits, verbose=args.verbose)
        print()


if __name__ == "__main__":
    main()
