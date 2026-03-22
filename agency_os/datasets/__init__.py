"""Dataset ingestion and indexing for content-based agent swarms."""

from .chunker import ChunkMeta, chunk_document
from .index import ContentIndex, SearchHit
from .loader import DatasetLoader

__all__ = [
    "DatasetLoader",
    "chunk_document",
    "ChunkMeta",
    "ContentIndex",
    "SearchHit",
]
