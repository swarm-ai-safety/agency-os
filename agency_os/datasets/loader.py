"""Load and parse content datasets from local directories.

Designed for the Lenny newsletter/podcast dataset format but generic enough
for any markdown-based content corpus with a JSON metadata index.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ContentDocument:
    """A single document from the dataset (newsletter post or podcast transcript)."""

    filename: str
    content_type: str  # "newsletter" or "podcast"
    text: str
    title: str = ""
    date: str = ""
    guest: str = ""
    description: str = ""
    subtitle: str = ""
    word_count: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def source_label(self) -> str:
        """Human-readable source reference."""
        parts = [self.content_type.title()]
        if self.title:
            parts.append(f'"{self.title}"')
        if self.guest:
            parts.append(f"with {self.guest}")
        if self.date:
            parts.append(f"({self.date})")
        return " — ".join(parts) if len(parts) > 1 else parts[0]


class DatasetLoader:
    """Load a content dataset from a directory containing markdown files and index.json.

    Expected layout::

        dataset_root/
            index.json          # metadata keyed by filename
            newsletters/*.md
            podcasts/*.md

    Usage::

        loader = DatasetLoader(Path("lennys-newsletterpodcastdata"))
        docs = loader.load_all()
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._metadata: Optional[dict] = None

    @property
    def metadata(self) -> dict:
        if self._metadata is None:
            index_path = self.root / "index.json"
            if index_path.exists():
                self._metadata = json.loads(index_path.read_text(encoding="utf-8"))
            else:
                self._metadata = {}
        return self._metadata

    def load_all(
        self,
        subdirs: tuple[str, ...] = ("newsletters", "podcasts"),
    ) -> list[ContentDocument]:
        """Load all markdown documents from the specified subdirectories."""
        docs: list[ContentDocument] = []
        for subdir in subdirs:
            dirpath = self.root / subdir
            if not dirpath.is_dir():
                continue
            content_type = subdir.rstrip("s")  # newsletters -> newsletter
            for md_path in sorted(dirpath.glob("*.md")):
                docs.append(self._load_one(md_path, content_type))
        return docs

    def _load_one(self, path: Path, content_type: str) -> ContentDocument:
        """Load a single markdown file, enriching with index.json metadata."""
        text = path.read_text(encoding="utf-8")
        meta = self.metadata.get(path.name, {})

        return ContentDocument(
            filename=path.name,
            content_type=content_type,
            text=text,
            title=meta.get("title", ""),
            date=meta.get("date", ""),
            guest=meta.get("guest", ""),
            description=meta.get("description", ""),
            subtitle=meta.get("subtitle", ""),
            word_count=meta.get("word_count", len(text.split())),
            extra={
                k: v
                for k, v in meta.items()
                if k
                not in (
                    "title",
                    "date",
                    "guest",
                    "description",
                    "subtitle",
                    "word_count",
                )
            },
        )

    def stats(self) -> dict:
        """Return summary statistics about the loaded dataset."""
        docs = self.load_all()
        by_type: dict[str, int] = {}
        total_words = 0
        for doc in docs:
            by_type[doc.content_type] = by_type.get(doc.content_type, 0) + 1
            total_words += doc.word_count
        return {
            "total_documents": len(docs),
            "by_type": by_type,
            "total_words": total_words,
            "has_index": (self.root / "index.json").exists(),
        }
