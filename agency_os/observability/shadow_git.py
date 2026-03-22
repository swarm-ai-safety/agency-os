"""Shadow git: invisible file-change tracking for agent task execution.

Uses GIT_DIR + GIT_WORK_TREE to maintain a bare git repo separate from
any actual repo in the working directory.  The agent never sees this
repo — it's purely for capturing per-step file diffs and building an
audit trail of what the agent changed.

Ported from dreadnode/agent-lens, simplified for task-scoped tracking
(no session chaining, replay, or worktrees).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

__all__ = ["ShadowGit"]

logger = logging.getLogger(__name__)

DEFAULT_IGNORE = """\
.git
__pycache__
*.pyc
*.pyo
node_modules
.venv
.env
.DS_Store
"""


class ShadowGit:
    """Invisible git repo that tracks all changes in a working directory."""

    def __init__(self, work_dir: Path, git_dir: Path) -> None:
        self.work_dir = work_dir.resolve()
        self.git_dir = git_dir.resolve()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command with GIT_DIR and GIT_WORK_TREE set."""
        env = {
            **os.environ,
            "GIT_DIR": str(self.git_dir),
            "GIT_WORK_TREE": str(self.work_dir),
        }
        result = subprocess.run(
            ["git", *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(self.work_dir),
        )
        if check and result.returncode != 0:
            logger.error("git %s failed: %s", " ".join(args), result.stderr.strip())
            result.check_returncode()
        return result

    def init(self) -> None:
        """Initialize the shadow git repo."""
        self.git_dir.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "GIT_DIR": str(self.git_dir)}
        subprocess.run(
            ["git", "init", "--bare"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        info_dir = self.git_dir / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        (info_dir / "exclude").write_text(DEFAULT_IGNORE)
        logger.debug(
            "Shadow git initialized: git_dir=%s work_dir=%s",
            self.git_dir,
            self.work_dir,
        )

    def commit_baseline(self, message: str = "baseline") -> None:
        """Stage everything and commit as the baseline snapshot."""
        self._git("add", "-A")
        self._git("commit", "-m", message, "--allow-empty")
        self._git("tag", "-f", "baseline")

    def commit_snapshot(self, tag: str, message: str | None = None) -> None:
        """Stage all changes and commit with a tag (only if there are changes)."""
        self._git("add", "-A")
        msg = message or tag
        status = self._git("diff", "--cached", "--quiet", check=False)
        if status.returncode != 0:
            self._git("commit", "-m", msg)
        self._git("tag", "-f", tag)

    def diff_from_ref(self, ref: str = "baseline") -> str:
        """Get unified diff of all changes since a ref."""
        result = self._git("diff", ref, "HEAD", "--no-color", check=False)
        return result.stdout

    def diff_working_names(self) -> list[str]:
        """Get list of changed files in working tree (uncommitted)."""
        self._git("add", "-A")
        result = self._git("diff", "--cached", "--name-only", check=False)
        return [f for f in result.stdout.strip().splitlines() if f]

    def show_file(self, ref: str, path: str) -> str | None:
        """Get file content at a specific ref. Returns None if not found."""
        result = self._git("show", f"{ref}:{path}", check=False)
        if result.returncode != 0:
            return None
        return result.stdout
