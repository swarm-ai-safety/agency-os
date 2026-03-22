"""Parse markdown agent specification files from agency-agents into structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AgentSpec:
    """Parsed agent specification from a markdown file."""

    name: str
    description: str
    color: str
    division: str
    slug: str  # e.g. "engineering/senior-developer"
    identity: str  # Full markdown body (used as system prompt base)
    source_path: Path

    # Extracted sections (optional, parsed from markdown)
    role: Optional[str] = None
    personality: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


def parse_spec(path: Path) -> AgentSpec:
    """
    Parse a single markdown agent spec file.

    Expected format:
        ---
        name: Agent Name
        description: One-line description
        color: green
        ---

        # Markdown body ...

    Args:
        path: Path to the .md file.

    Returns:
        Parsed AgentSpec.

    Raises:
        ValueError: If the file has no valid YAML frontmatter.
    """
    text = path.read_text(encoding="utf-8")

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        raise ValueError(f"No YAML frontmatter found in {path}")

    fm = _parse_yaml_frontmatter(frontmatter)

    name = fm.get("name", path.stem)
    description = fm.get("description", "")
    color = fm.get("color", "gray")

    division = path.parent.name
    slug = _derive_slug(division, path.stem)

    role = _extract_section(body, r"Role")
    personality = _extract_section(body, r"Personality")
    tools = _extract_list_items(body, r"Tools|Technical Stack|Capabilities")
    success_criteria = _extract_list_items(body, r"Success Criteria")

    return AgentSpec(
        name=name,
        description=description,
        color=color,
        division=division,
        slug=slug,
        identity=body.strip(),
        source_path=path,
        role=role,
        personality=personality,
        tools=tools,
        success_criteria=success_criteria,
    )


def _split_frontmatter(text: str) -> tuple[Optional[str], str]:
    """Split YAML frontmatter from markdown body."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return None, text


def _parse_yaml_frontmatter(raw: str) -> dict[str, str]:
    """Simple key: value parser for frontmatter (avoids PyYAML dep for parsing specs)."""
    result: dict[str, str] = {}
    for line in raw.strip().splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _derive_slug(division: str, stem: str) -> str:
    """
    Derive a canonical slug from division and file stem.

    Example: division="engineering", stem="engineering-senior-developer"
        → "engineering/senior-developer"
    """
    # Strip division prefix from stem if present
    prefix = f"{division}-"
    if stem.startswith(prefix):
        agent_name = stem[len(prefix) :]
    else:
        agent_name = stem
    return f"{division}/{agent_name}"


def _extract_section(body: str, header_pattern: str) -> Optional[str]:
    """Extract first paragraph after a heading matching the pattern."""
    # Restrict heading match to a single line; DOTALL is only for section capture.
    pattern = rf"^#+\s*[^\n]*(?:{header_pattern})[^\n]*\n(.*?)(?=\n#|\Z)"
    match = re.search(pattern, body, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_list_items(body: str, header_pattern: str) -> list[str]:
    """Extract bullet list items from a section matching the header pattern."""
    section = _extract_section(body, header_pattern)
    if not section:
        return []
    items = re.findall(r"^[\s]*[-*]\s+(.+)$", section, re.MULTILINE)
    return [item.strip() for item in items]
