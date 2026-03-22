"""Task dependency graph (DAG) for project plans.

Provides topological sorting, critical path analysis, and parallel
execution scheduling for task graphs produced by the planning layer.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .schema import TaskSpec, TaskStatus


@dataclass
class TaskNode:
    """A node in the task dependency graph."""

    task: TaskSpec
    children: list[str] = field(default_factory=list)  # tasks that depend on this
    depth: int = 0  # distance from root (for scheduling)


class TaskDAG:
    """Directed acyclic graph of task dependencies.

    Provides:
    - Cycle detection (plans with cycles are invalid)
    - Topological sort (execution order)
    - Critical path analysis (longest dependency chain)
    - Parallel scheduling (which tasks can run concurrently)
    """

    def __init__(self, tasks: list[TaskSpec]) -> None:
        self._nodes: dict[str, TaskNode] = {}
        self._build(tasks)

    def _build(self, tasks: list[TaskSpec]) -> None:
        """Build the DAG from a list of tasks."""
        for task in tasks:
            self._nodes[task.id] = TaskNode(task=task)

        # Wire up child pointers (reverse of depends_on)
        for task in tasks:
            for dep_id in task.depends_on:
                if dep_id in self._nodes:
                    self._nodes[dep_id].children.append(task.id)

        # Compute depths
        self._compute_depths()

    def _compute_depths(self) -> None:
        """BFS to compute depth (distance from roots) for each node."""
        in_degree: dict[str, int] = dict.fromkeys(self._nodes, 0)
        for nid, node in self._nodes.items():
            for dep in node.task.depends_on:
                if dep in in_degree:
                    in_degree[nid] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        while queue:
            nid = queue.popleft()
            node = self._nodes[nid]
            for child_id in node.children:
                child = self._nodes[child_id]
                child.depth = max(child.depth, node.depth + 1)
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

    def validate(self) -> list[str]:
        """Check for cycles and missing dependencies. Returns list of errors."""
        errors: list[str] = []
        task_ids = set(self._nodes.keys())

        # Check for missing dependencies
        for nid, node in self._nodes.items():
            for dep in node.task.depends_on:
                if dep not in task_ids:
                    errors.append(f"Task {nid} depends on unknown task {dep}")

        # Check for cycles via topological sort
        if not errors:
            try:
                self.topological_sort()
            except ValueError as e:
                errors.append(str(e))

        return errors

    def topological_sort(self) -> list[str]:
        """Return task IDs in valid execution order (Kahn's algorithm)."""
        in_degree: dict[str, int] = dict.fromkeys(self._nodes, 0)
        for nid, node in self._nodes.items():
            for dep in node.task.depends_on:
                if dep in in_degree:
                    in_degree[nid] += 1

        queue = deque(
            sorted(
                (nid for nid, deg in in_degree.items() if deg == 0),
                key=lambda nid: self._nodes[nid].task.estimated_tokens,
            )
        )
        order: list[str] = []

        while queue:
            nid = queue.popleft()
            order.append(nid)
            for child_id in self._nodes[nid].children:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if len(order) != len(self._nodes):
            raise ValueError(
                f"Cycle detected in task DAG: "
                f"sorted {len(order)} of {len(self._nodes)} tasks"
            )

        return order

    def critical_path(self) -> list[str]:
        """Find the longest dependency chain (critical path).

        Uses dynamic programming: for each task, the longest path ending
        at that task is 1 + max(longest path ending at each dependency).
        """
        if not self._nodes:
            return []

        order = self.topological_sort()
        longest: dict[str, int] = dict.fromkeys(self._nodes, 1)
        parent: dict[str, str] = {}

        for nid in order:
            node = self._nodes[nid]
            for child_id in node.children:
                new_len = longest[nid] + 1
                if new_len > longest[child_id]:
                    longest[child_id] = new_len
                    parent[child_id] = nid

        # Trace back from the deepest node
        end_node = max(longest, key=longest.get)  # type: ignore[arg-type]
        path: list[str] = [end_node]
        while end_node in parent:
            end_node = parent[end_node]
            path.append(end_node)
        path.reverse()
        return path

    def parallel_schedule(self) -> list[list[str]]:
        """Group tasks into waves that can execute concurrently.

        Each wave contains tasks whose dependencies are all in earlier waves.
        """
        waves: list[list[str]] = []
        depth_groups: dict[int, list[str]] = defaultdict(list)

        for nid, node in self._nodes.items():
            depth_groups[node.depth].append(nid)

        for depth in sorted(depth_groups.keys()):
            waves.append(sorted(depth_groups[depth]))

        return waves

    def ready_tasks(self) -> list[str]:
        """Tasks whose dependencies are all PASSED."""
        completed = {
            nid
            for nid, node in self._nodes.items()
            if node.task.status == TaskStatus.PASSED
        }
        return [
            nid
            for nid, node in self._nodes.items()
            if node.task.status == TaskStatus.PENDING
            and all(dep in completed for dep in node.task.depends_on)
        ]

    def summary(self) -> dict[str, Any]:
        """DAG summary statistics."""
        waves = self.parallel_schedule()
        return {
            "total_tasks": len(self._nodes),
            "max_depth": max((n.depth for n in self._nodes.values()), default=0),
            "parallel_waves": len(waves),
            "wave_sizes": [len(w) for w in waves],
            "critical_path_length": len(self.critical_path()),
            "root_tasks": len(
                [nid for nid, node in self._nodes.items() if not node.task.depends_on]
            ),
        }
