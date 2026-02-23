"""TodoList middleware for the Holmes LangGraph agent.

Manages investigation task state across agent steps, replacing the
pure prompt-based approach with state-tracked enforcement.

Key differences from the original TodoWrite + prompt approach:
- State is tracked in the graph, not just as tool output
- Task status is injected into model context automatically
- Completion is enforced via graph routing (not just prompt instructions)
- Benchmarking metrics are collected
"""

import logging
from typing import Any, Dict, List, Optional

from holmes.core.todo_tasks_formatter import format_tasks
from holmes.plugins.toolsets.investigator.model import Task, TaskStatus

logger = logging.getLogger(__name__)

MAX_FORCE_CONTINUE_COUNT = 5  # Prevent infinite loops


class TodoListMiddleware:
    """State-tracked TodoList management middleware.

    Used by the LangGraph agent to:
    1. Track task state across iterations
    2. Inject current task status before each LLM call
    3. Enforce task completion via graph routing
    4. Collect benchmarking metrics
    """

    def __init__(self):
        self.tasks: List[Task] = []
        self._task_updates_count: int = 0
        self._forced_continue_count: int = 0

    def update_tasks(self, tasks_data: List[Dict[str, Any]]) -> None:
        """Update internal task state from TodoWrite tool params.

        Called by tool_node when it detects a TodoWrite tool call.
        """
        self.tasks = _parse_tasks(tasks_data)
        self._task_updates_count += 1
        logger.debug(
            f"TodoListMiddleware: Updated tasks ({len(self.tasks)} total, "
            f"{sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)} completed)"
        )

    def get_task_status_injection(self) -> Optional[str]:
        """Generate task status text to inject before model call.

        Returns None if no tasks exist (no injection needed).
        """
        if not self.tasks:
            return None
        return format_tasks(self.tasks)

    def all_tasks_completed(self) -> bool:
        """Check if all tasks are in a terminal state (completed or failed)."""
        if not self.tasks:
            return True
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in self.tasks
        )

    def should_force_continue(self) -> bool:
        """Check if the agent should be forced to continue (incomplete tasks).

        Returns False if:
        - No tasks exist
        - All tasks are completed/failed
        - Force continue limit exceeded (safety valve)
        """
        if not self.tasks:
            return False
        if self.all_tasks_completed():
            return False
        if self._forced_continue_count >= MAX_FORCE_CONTINUE_COUNT:
            logger.warning(
                f"TodoListMiddleware: Force continue limit reached ({MAX_FORCE_CONTINUE_COUNT}), "
                f"allowing agent to end despite incomplete tasks"
            )
            return False

        self._forced_continue_count += 1
        incomplete = [t for t in self.tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        logger.info(
            f"TodoListMiddleware: Forcing agent to continue "
            f"(attempt {self._forced_continue_count}, {len(incomplete)} tasks remaining)"
        )
        return True

    def get_force_continue_message(self) -> str:
        """Generate a system message to push agent to complete remaining tasks."""
        incomplete = [
            t for t in self.tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        ]
        task_list = "\n".join(
            f"- [{t.id}] {t.content} (status: {t.status.value})" for t in incomplete
        )
        return (
            f"SYSTEM NOTICE: You have {len(incomplete)} incomplete investigation tasks. "
            f"You MUST complete all tasks before providing a final answer.\n\n"
            f"Incomplete tasks:\n{task_list}\n\n"
            f"Continue working on the next pending task. "
            f"Use TodoWrite to update task status as you progress."
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return middleware metrics for benchmarking.

        Useful for comparing against the original TodoWrite + prompt approach.
        """
        return {
            "total_task_updates": self._task_updates_count,
            "forced_continues": self._forced_continue_count,
            "final_task_count": len(self.tasks),
            "completed_tasks": sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED),
            "failed_tasks": sum(1 for t in self.tasks if t.status == TaskStatus.FAILED),
            "pending_tasks": sum(1 for t in self.tasks if t.status == TaskStatus.PENDING),
            "in_progress_tasks": sum(1 for t in self.tasks if t.status == TaskStatus.IN_PROGRESS),
        }

    def reset(self) -> None:
        """Reset middleware state for a new interaction."""
        self.tasks = []
        self._task_updates_count = 0
        self._forced_continue_count = 0


def _parse_tasks(tasks_data: List[Dict[str, Any]]) -> List[Task]:
    """Parse task dicts into Task model objects."""
    tasks = []
    for item in tasks_data:
        if isinstance(item, dict):
            tasks.append(
                Task(
                    id=item.get("id", ""),
                    content=item.get("content", ""),
                    status=TaskStatus(item.get("status", "pending")),
                )
            )
    return tasks
