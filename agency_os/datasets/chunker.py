"""Document chunking strategies for content datasets.

Supports both naive character-based chunking and structure-aware chunking
that respects markdown headings and speaker turns in transcripts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import ContentDocument


@dataclass(frozen=True)
class ChunkMeta:
    """Metadata for a single text chunk."""

    chunk_id: str
    filename: str
    content_type: str
    title: str
    date: str
    guest: str
    chunk_index: int
    total_chunks: int
    text: str
    char_start: int
    char_end: int
    heading: str = ""  # nearest heading above this chunk

    @property
    def source_ref(self) -> str:
        label = self.title or self.filename
        if self.guest:
            label += f" (guest: {self.guest})"
        if self.date:
            label += f" [{self.date}]"
        return label


def chunk_document(
    doc: ContentDocument,
    chunk_size: int = 3000,
    overlap: int = 400,
    strategy: str = "structured",
) -> list[ChunkMeta]:
    """Chunk a document into overlapping text segments.

    Args:
        doc: The source document.
        chunk_size: Target chunk size in characters.
        overlap: Overlap between consecutive chunks.
        strategy: "naive" for character-based, "structured" for heading-aware.

    Returns:
        List of ChunkMeta objects.
    """
    if strategy == "structured":
        return _chunk_structured(doc, chunk_size, overlap)
    return _chunk_naive(doc, chunk_size, overlap)


def _chunk_naive(
    doc: ContentDocument, chunk_size: int, overlap: int
) -> list[ChunkMeta]:
    """Simple character-based chunking with overlap."""
    text = doc.text
    spans = _compute_spans(len(text), chunk_size, overlap)
    total = len(spans)

    return [
        ChunkMeta(
            chunk_id=f"{doc.filename}::chunk{i}",
            filename=doc.filename,
            content_type=doc.content_type,
            title=doc.title,
            date=doc.date,
            guest=doc.guest,
            chunk_index=i,
            total_chunks=total,
            text=text[start:end],
            char_start=start,
            char_end=end,
        )
        for i, (start, end) in enumerate(spans)
    ]


def _chunk_structured(
    doc: ContentDocument, chunk_size: int, overlap: int
) -> list[ChunkMeta]:
    """Heading-aware chunking that tries to break at section boundaries.

    For podcast transcripts, also respects speaker turn markers (e.g. "**Name:**").
    """
    text = doc.text
    # Find all heading positions and speaker turns
    boundaries = _find_boundaries(text)

    if not boundaries:
        return _chunk_naive(doc, chunk_size, overlap)

    sections = _split_at_boundaries(text, boundaries, chunk_size, overlap)
    total = len(sections)

    return [
        ChunkMeta(
            chunk_id=f"{doc.filename}::chunk{i}",
            filename=doc.filename,
            content_type=doc.content_type,
            title=doc.title,
            date=doc.date,
            guest=doc.guest,
            chunk_index=i,
            total_chunks=total,
            text=section_text,
            char_start=start,
            char_end=start + len(section_text),
            heading=heading,
        )
        for i, (section_text, start, heading) in enumerate(sections)
    ]


def _find_boundaries(text: str) -> list[tuple[int, str]]:
    """Find natural chunk boundaries: headings and speaker turns."""
    boundaries: list[tuple[int, str]] = []

    # Markdown headings
    for m in re.finditer(r"^(#{1,4})\s+(.+)$", text, re.MULTILINE):
        boundaries.append((m.start(), m.group(2).strip()))

    # Speaker turns in podcast transcripts: **Name:** or **Name**:
    for m in re.finditer(r"^\*\*([^*]+?)(?:\*\*:|:\*\*)", text, re.MULTILINE):
        boundaries.append((m.start(), m.group(1).strip()))

    boundaries.sort(key=lambda x: x[0])
    return boundaries


def _split_at_boundaries(
    text: str,
    boundaries: list[tuple[int, str]],
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, int, str]]:
    """Split text at boundaries, merging small sections up to chunk_size.

    Returns list of (text, start_offset, heading).
    """
    results: list[tuple[str, int, str]] = []
    current_start = 0
    current_heading = ""
    current_end = 0

    for pos, heading in boundaries:
        # If adding this section would exceed chunk_size, flush current
        if pos - current_start > chunk_size and current_end > current_start:
            chunk_text = text[current_start:current_end]
            results.append((chunk_text, current_start, current_heading))
            # Start new chunk with overlap
            current_start = max(current_end - overlap, current_start)
            current_heading = heading

        current_end = pos
        if not current_heading:
            current_heading = heading

    # Flush remaining text
    if current_start < len(text):
        chunk_text = text[current_start:]
        results.append((chunk_text, current_start, current_heading))

    # If any chunk is still too large, sub-chunk it naively
    final: list[tuple[str, int, str]] = []
    for chunk_text, start, heading in results:
        if len(chunk_text) > chunk_size * 1.5:
            spans = _compute_spans(len(chunk_text), chunk_size, overlap)
            for sub_start, sub_end in spans:
                final.append(
                    (chunk_text[sub_start:sub_end], start + sub_start, heading)
                )
        else:
            final.append((chunk_text, start, heading))

    return final


def _compute_spans(length: int, chunk_size: int, overlap: int) -> list[tuple[int, int]]:
    """Compute (start, end) spans for chunking a text of given length."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )
    spans: list[tuple[int, int]] = []
    start = 0
    while start < length:
        end = min(start + chunk_size, length)
        spans.append((start, end))
        if end >= length:
            break
        start = end - overlap
    return spans
