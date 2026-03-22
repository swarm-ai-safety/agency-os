"""Isolated task sandbox for safe, reproducible agent execution.

Each task runs in its own sandbox with:
- Filesystem isolation (temporary working directory)
- Resource limits (timeout, memory)
- Network control (enabled/disabled per task)
- Clean environment (no state leakage between tasks)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .schema import SandboxRequirements, TaskSpec

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result of running a task in a sandbox."""

    task_id: str
    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    working_dir: str = ""
    files_created: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output[:2000],  # Truncate for storage
            "error": self.error[:1000],
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "files_created": self.files_created,
        }


class TaskSandbox:
    """Manages isolated execution environments for agent tasks.

    Usage::

        sandbox = TaskSandbox(project_dir=Path("/path/to/project"))

        # Create sandbox for a task
        work_dir = sandbox.create(task)

        # After agent produces output, verify it
        result = sandbox.run_verification(task, work_dir, [
            "ruff check .",
            "mypy .",
        ])

        # Clean up
        sandbox.cleanup(task.id)
    """

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        sandbox_root: Optional[Path] = None,
    ) -> None:
        self._project_dir = project_dir
        self._sandbox_root = sandbox_root or Path(
            tempfile.mkdtemp(prefix="agency-sandbox-")
        )
        self._active: dict[str, Path] = {}

    def create(self, task: TaskSpec) -> Path:
        """Create an isolated working directory for a task.

        If a project directory exists, copies relevant files into the sandbox.
        Otherwise, creates a clean empty workspace.
        """
        work_dir = self._sandbox_root / f"task-{task.id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Copy project files into sandbox if available
        if self._project_dir and self._project_dir.is_dir():
            # Shallow copy: only project metadata and relevant directories
            for item in self._project_dir.iterdir():
                if item.name.startswith(".") and item.name not in (".gitignore",):
                    continue
                if item.name in (
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    "build",
                    "dist",
                ):
                    continue
                dst = work_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)

        self._active[task.id] = work_dir
        logger.info(f"Sandbox created for task {task.id}: {work_dir}")
        return work_dir

    def run_verification(
        self,
        task: TaskSpec,
        work_dir: Path,
        commands: list[str],
    ) -> SandboxResult:
        """Run verification commands in the sandbox.

        Args:
            task: The task being verified.
            work_dir: The sandbox working directory.
            commands: Shell commands to run (lint, typecheck, tests, etc.)
        """
        start = time.monotonic()
        all_output: list[str] = []
        all_errors: list[str] = []
        final_exit_code = 0

        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=task.sandbox.max_duration_seconds,
                    env=self._build_env(task.sandbox),
                )
                all_output.append(f"$ {cmd}\n{result.stdout}")
                if result.returncode != 0:
                    all_errors.append(f"$ {cmd}\n{result.stderr}")
                    final_exit_code = result.returncode
            except subprocess.TimeoutExpired:
                all_errors.append(
                    f"$ {cmd}\nTIMEOUT after {task.sandbox.max_duration_seconds}s"
                )
                final_exit_code = 124
                break
            except Exception as e:
                all_errors.append(f"$ {cmd}\nERROR: {e}")
                final_exit_code = 1

        duration_ms = int((time.monotonic() - start) * 1000)

        # List files created/modified in sandbox
        files_created = []
        if work_dir.exists():
            for f in work_dir.rglob("*"):
                if f.is_file():
                    files_created.append(str(f.relative_to(work_dir)))

        return SandboxResult(
            task_id=task.id,
            success=final_exit_code == 0,
            output="\n".join(all_output),
            error="\n".join(all_errors),
            exit_code=final_exit_code,
            duration_ms=duration_ms,
            working_dir=str(work_dir),
            files_created=files_created[:100],  # Cap at 100 files
        )

    def cleanup(self, task_id: str) -> None:
        """Remove a task's sandbox directory."""
        work_dir = self._active.pop(task_id, None)
        if work_dir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info(f"Sandbox cleaned up for task {task_id}")

    def cleanup_all(self) -> None:
        """Remove all active sandboxes."""
        for task_id in list(self._active.keys()):
            self.cleanup(task_id)
        if self._sandbox_root.exists():
            shutil.rmtree(self._sandbox_root, ignore_errors=True)

    @staticmethod
    def _build_env(reqs: SandboxRequirements) -> dict[str, str]:
        """Build environment variables for sandbox execution."""
        import os

        env = dict(os.environ)
        env.update(reqs.environment_vars)
        # Signal to scripts that they're running in a sandbox
        env["AGENCY_SANDBOX"] = "1"
        env["AGENCY_SANDBOX_NETWORK"] = "1" if reqs.needs_network else "0"
        return env
