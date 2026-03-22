"""File state tracking via shadow git.

Detects per-step file mutations with unified diffs and attribution.
After each check, changes are staged so the next check only sees
new modifications.

Ported from dreadnode/agent-lens, simplified for task-scoped tracking.
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from agency_os.observability.shadow_git import ShadowGit

__all__ = ["WriteEvent", "StateManager"]

logger = logging.getLogger(__name__)


def _safe_read_text(path: Path) -> str:
    """Read a file as UTF-8, returning a placeholder for binary files."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return f"[binary file: {path.name}]"


@dataclass
class WriteEvent:
    """A single file write detected between steps."""

    timestamp: str
    step_id: int
    file_path: str
    diff: str
    diff_stats: dict[str, int]


class StateManager:
    """Tracks file changes via shadow git, attributed to execution steps."""

    def __init__(self, work_dir: Path, shadow_git: ShadowGit) -> None:
        self.work_dir = work_dir
        self.shadow_git = shadow_git
        self.write_log: list[WriteEvent] = []

    def check_for_writes(self, step_id: int) -> list[WriteEvent]:
        """Detect file changes since last check.

        Returns a list of WriteEvent objects for each changed file.
        Commits changes so the next call only sees new modifications.
        """
        changed_files = self.shadow_git.diff_working_names()
        if not changed_files:
            return []

        new_events: list[WriteEvent] = []
        for file_path in changed_files:
            full_path = self.work_dir / file_path

            before = self.shadow_git.show_file("HEAD", file_path) or ""
            after = _safe_read_text(full_path) if full_path.exists() else ""

            diff = "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=file_path,
                    tofile=file_path,
                )
            )
            lines = diff.splitlines()
            added = sum(
                1
                for line in lines
                if line.startswith("+") and not line.startswith("+++")
            )
            removed = sum(
                1
                for line in lines
                if line.startswith("-") and not line.startswith("---")
            )

            new_events.append(
                WriteEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    step_id=step_id,
                    file_path=file_path,
                    diff=diff,
                    diff_stats={"added": added, "removed": removed},
                )
            )

        # Commit so next check only sees new changes
        self.shadow_git.commit_snapshot(
            tag=f"step_{step_id}",
            message=f"step {step_id}",
        )

        self.write_log.extend(new_events)
        return new_events

    def to_changelog(self) -> list[dict]:
        """Return the write log as a list of JSON-serializable dicts."""
        return [asdict(e) for e in self.write_log]

    def save_changelog(self, dest: Path) -> None:
        """Write all write events to a JSONL file."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as f:
            for event in self.write_log:
                f.write(json.dumps(asdict(event), default=str) + "\n")
