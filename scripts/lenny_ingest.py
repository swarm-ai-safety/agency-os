#!/usr/bin/env python3
"""Ingest the Lenny newsletter/podcast dataset into a searchable content index.

Usage:
    # Clone the dataset first
    git clone https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git data/lenny

    # Run ingestion
    python scripts/lenny_ingest.py --data-dir data/lenny --output build/lenny.idx

    # Or with custom chunk settings
    python scripts/lenny_ingest.py --data-dir data/lenny --chunk-size 2000 --overlap 300
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agency_os.datasets.chunker import chunk_document
from agency_os.datasets.index import ContentIndex
from agency_os.datasets.loader import DatasetLoader


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Lenny content dataset into a BM25 search index."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/lenny"),
        help="Path to cloned lennys-newsletterpodcastdata repo",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/lenny.idx"),
        help="Output path for the search index",
    )
    parser.add_argument("--chunk-size", type=int, default=3000)
    parser.add_argument("--overlap", type=int, default=400)
    parser.add_argument(
        "--strategy",
        choices=["naive", "structured"],
        default="structured",
        help="Chunking strategy",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"Error: {args.data_dir} not found.")
        print("Clone the dataset first:")
        print(
            "  git clone https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git data/lenny"
        )
        sys.exit(1)

    # Load documents
    loader = DatasetLoader(args.data_dir)
    stats = loader.stats()
    print(
        f"Dataset: {stats['total_documents']} documents, {stats['total_words']:,} words"
    )
    print(f"  By type: {stats['by_type']}")
    print(f"  Has index.json: {stats['has_index']}")

    docs = loader.load_all()

    # Chunk all documents
    all_chunks = []
    for doc in docs:
        chunks = chunk_document(
            doc,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            strategy=args.strategy,
        )
        all_chunks.extend(chunks)
        print(f"  {doc.filename}: {len(chunks)} chunks ({doc.content_type})")

    print(f"\nTotal chunks: {len(all_chunks)}")

    # Build and save index
    index = ContentIndex()
    index.build(all_chunks)
    index.save(args.output)
    print(f"Index saved to {args.output} ({index.size} entries)")


if __name__ == "__main__":
    main()
