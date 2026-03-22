"""Discover and catalog all agent specs from the agency-agents vendor directory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from agency_os.agents.spec_parser import AgentSpec, parse_spec

logger = logging.getLogger(__name__)

# Default location of the agency-agents vendor directory
_DEFAULT_SPECS_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "vendor" / "agency-agents"
)


class AgentRegistry:
    """
    Discovers and catalogs all agent specifications.

    Walks the vendor/agency-agents directory, parses each .md file,
    and builds a searchable index by slug and division.
    """

    def __init__(self, specs_root: Optional[Path] = None):
        self._specs_root = specs_root or _DEFAULT_SPECS_ROOT
        self._by_slug: dict[str, AgentSpec] = {}
        self._by_division: dict[str, list[AgentSpec]] = {}
        self._loaded = False

    def load(self) -> None:
        """Scan the specs directory and parse all agent .md files."""
        self._by_slug.clear()
        self._by_division.clear()

        if not self._specs_root.is_dir():
            raise FileNotFoundError(
                f"Agent specs directory not found: {self._specs_root}"
            )

        for md_file in sorted(self._specs_root.rglob("*.md")):
            # Skip top-level files like README.md, CONTRIBUTING.md
            if md_file.parent == self._specs_root:
                continue
            try:
                spec = parse_spec(md_file)
                self._by_slug[spec.slug] = spec
                self._by_division.setdefault(spec.division, []).append(spec)
            except (ValueError, OSError) as e:
                logger.warning(f"Skipping {md_file}: {e}")

        self._loaded = True
        logger.info(
            f"Registry loaded: {len(self._by_slug)} agents across "
            f"{len(self._by_division)} divisions"
        )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, slug: str) -> Optional[AgentSpec]:
        """Look up an agent by slug (e.g. 'engineering/senior-developer')."""
        self._ensure_loaded()
        return self._by_slug.get(slug)

    def get_or_raise(self, slug: str) -> AgentSpec:
        """Look up an agent by slug, raising KeyError if not found."""
        spec = self.get(slug)
        if spec is None:
            raise KeyError(
                f"Agent spec not found: {slug!r}. Available: {sorted(self._by_slug.keys())}"
            )
        return spec

    def list_all(self) -> list[AgentSpec]:
        """Return all discovered agent specs."""
        self._ensure_loaded()
        return list(self._by_slug.values())

    def list_division(self, division: str) -> list[AgentSpec]:
        """Return all agents in a given division."""
        self._ensure_loaded()
        return list(self._by_division.get(division, []))

    def divisions(self) -> list[str]:
        """Return all discovered division names."""
        self._ensure_loaded()
        return sorted(self._by_division.keys())

    @property
    def count(self) -> int:
        """Total number of registered agents."""
        self._ensure_loaded()
        return len(self._by_slug)

    def search(self, query: str) -> list[AgentSpec]:
        """Simple text search across name, description, and slug."""
        self._ensure_loaded()
        query_lower = query.lower()
        return [
            spec
            for spec in self._by_slug.values()
            if query_lower in spec.name.lower()
            or query_lower in spec.description.lower()
            or query_lower in spec.slug.lower()
        ]

    def __repr__(self) -> str:
        return f"AgentRegistry(agents={self.count}, divisions={len(self.divisions())})"
