"""Holmes Investigation Middleware for LangChain create_agent().

Manages the investigation workflow via wrap_model_call and after_model hooks:
- Dynamic system prompt injection (jinja2 templates)
- Context window management
- Tool filtering (runbook restriction)
- Cost/token tracking
- TodoList status injection and completion enforcement
- UI observability interface (tasks, metrics, costs, state_snapshot)
"""

import logging
import threading
from typing import Any, Dict, List, Optional

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.config import get_config

from holmes.common.env_vars import RESET_REPEATED_TOOL_CALL_CHECK_AFTER_COMPACTION
from holmes.core.langchain.message_converter import langchain_to_openai, openai_to_langchain
from holmes.core.langchain.tool_adapter import create_langchain_tools
from holmes.core.llm import LLM
from holmes.core.todo_tasks_formatter import format_tasks
from holmes.core.tools_utils.tool_executor import ToolExecutor
from holmes.core.truncation.input_context_window_limiter import limit_input_context_window
from holmes.plugins.toolsets.investigator.model import Task, TaskStatus
from holmes.utils.tags import parse_messages_tags

logger = logging.getLogger(__name__)

MAX_FORCE_CONTINUE_COUNT = 5


class HolmesInvestigationMiddleware(AgentMiddleware):
    """Holmes investigation workflow middleware.

    Provides TodoListMiddleware-like UI observability interface:
    - tasks: current TodoList state
    - metrics: benchmarking metrics
    - tool_history: all tool execution records
    - costs: accumulated token/cost info
    - state_snapshot: full state for UI display
    """

    name = "holmes_investigation"

    state_schema = AgentState

    def __init__(
        self,
        max_steps: int = 25,
        tool_executor: Optional[ToolExecutor] = None,
        holmes_llm: Optional[LLM] = None,
    ):
        self._max_steps = max_steps
        self._tool_executor = tool_executor
        self._holmes_llm = holmes_llm

        # Mutable state (accumulated across hooks)
        self._lock = threading.Lock()
        self._step_count: int = 0
        self._tasks: List[Task] = []
        self._task_updates_count: int = 0
        self._force_continue_count: int = 0
        self._runbook_in_use: bool = False
        self._tool_call_results: List[dict] = []
        self._tool_calls_history: List[dict] = []
        self._total_cost: float = 0.0
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._total_tokens: int = 0
        self._metadata: Dict[str, Any] = {}
        self._tool_number_offset: int = 0

    # =========================================================================
    # UI Observability Interface (TodoListMiddleware-compatible)
    # =========================================================================

    @property
    def tasks(self) -> List[Task]:
        """Current TodoList state (id, content, status)."""
        return list(self._tasks)

    @property
    def metrics(self) -> Dict[str, Any]:
        """Benchmarking metrics."""
        return {
            "total_task_updates": self._task_updates_count,
            "forced_continues": self._force_continue_count,
            "final_task_count": len(self._tasks),
            "completed_tasks": sum(1 for t in self._tasks if t.status == TaskStatus.COMPLETED),
            "failed_tasks": sum(1 for t in self._tasks if t.status == TaskStatus.FAILED),
            "pending_tasks": sum(1 for t in self._tasks if t.status == TaskStatus.PENDING),
            "in_progress_tasks": sum(1 for t in self._tasks if t.status == TaskStatus.IN_PROGRESS),
        }

    @property
    def tool_history(self) -> List[dict]:
        """All tool execution records."""
        return list(self._tool_calls_history)

    @property
    def costs(self) -> Dict[str, Any]:
        """Accumulated cost info."""
        return {
            "total_cost": self._total_cost,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self._total_tokens,
        }

    @property
    def step_count(self) -> int:
        """LLM invocation count."""
        return self._step_count

    @property
    def state_snapshot(self) -> Dict[str, Any]:
        """Full state snapshot for UI display."""
        return {
            "step_count": self._step_count,
            "max_steps": self._max_steps,
            "tasks": [t.model_dump() for t in self._tasks],
            "costs": self.costs,
            "metrics": self.metrics,
            "tool_history_count": len(self._tool_calls_history),
            "runbook_in_use": self._runbook_in_use,
            "metadata": self._metadata,
        }

    # =========================================================================
    # State mutation methods (called by tool_execution middleware)
    # =========================================================================

    def update_tasks(self, tasks_data: List[Dict[str, Any]]) -> None:
        """Update internal task state from TodoWrite tool params."""
        with self._lock:
            self._tasks = _parse_tasks(tasks_data)
            self._task_updates_count += 1
        logger.debug(
            f"HolmesInvestigationMiddleware: Updated tasks ({len(self._tasks)} total, "
            f"{sum(1 for t in self._tasks if t.status == TaskStatus.COMPLETED)} completed)"
        )

    def activate_runbook(self) -> None:
        """Activate restricted tools after runbook fetch."""
        self._runbook_in_use = True
        logger.debug("Runbook fetched - restricted tools now available")

    def record_tool_result(self, result_dict: dict) -> None:
        """Record a tool execution result."""
        with self._lock:
            self._tool_calls_history.append(result_dict)
            self._tool_call_results.append(result_dict)

    def next_tool_number(self) -> int:
        """Get and increment the next tool number."""
        with self._lock:
            self._tool_number_offset += 1
            return self._tool_number_offset

    def get_tool_call_results(self) -> List[dict]:
        """Get accumulated tool call results for LLMResult."""
        return list(self._tool_call_results)

    # =========================================================================
    # Middleware hooks
    # =========================================================================

    def wrap_model_call(self, request, handler):
        """Intercept model calls to manage Holmes-specific logic.

        1. Dynamic system prompt injection
        2. Context window management
        3. Tool filtering (runbook restriction)
        4. Last step: force final answer (no tools)
        5. TodoList status injection
        6. Cost tracking
        """
        config = get_config()
        configurable = config.get("configurable", {})

        system_prompt = configurable.get("system_prompt")
        tool_executor = configurable.get("tool_executor", self._tool_executor)
        holmes_llm = configurable.get("holmes_llm", self._holmes_llm)
        response_format = configurable.get("response_format")

        # 1. Dynamic system prompt injection
        if system_prompt:
            request = request.override(
                system_message=SystemMessage(content=system_prompt)
            )

        # 2. Context window management
        # Convert messages to OpenAI format for Holmes' limiter
        openai_msgs = langchain_to_openai(list(request.messages))

        # Get current tools in OpenAI format for token counting
        tools_openai = None
        if tool_executor and holmes_llm and request.tools:
            tools_openai = tool_executor.get_all_tools_openai_format(
                target_model=holmes_llm.model,
                include_restricted=self._runbook_in_use,
            )

        if holmes_llm:
            limit_result = limit_input_context_window(
                llm=holmes_llm, messages=openai_msgs, tools=tools_openai
            )
            openai_msgs = limit_result.messages
            self._metadata = self._metadata | limit_result.metadata

            # Reset repeated tool call check if conversation was compacted
            if limit_result.conversation_history_compacted and RESET_REPEATED_TOOL_CALL_CHECK_AFTER_COMPACTION:
                with self._lock:
                    self._tool_calls_history = []

        # 3. Tool filtering based on runbook state
        if self._runbook_in_use and tool_executor and holmes_llm:
            restricted_tools = create_langchain_tools(
                tool_executor, holmes_llm.model, include_restricted=True
            )
            request = request.override(tools=restricted_tools)

        # 4. Last step: no tools, force final answer
        if self._step_count >= self._max_steps - 1:
            logger.warning(f"Max steps reached: {self._step_count + 1}/{self._max_steps}")
            request = request.override(tools=[])

        # 5. TodoList status injection
        if self._tasks:
            task_injection = format_tasks(self._tasks)
            if task_injection and system_prompt:
                # Append task status to system message
                combined = f"{system_prompt}\n\n{task_injection}"
                request = request.override(
                    system_message=SystemMessage(content=combined)
                )

        # Apply context-trimmed messages
        trimmed_messages = openai_to_langchain(parse_messages_tags(openai_msgs))
        request = request.override(messages=trimmed_messages)

        # Execute model call
        response = handler(request)

        # 6. Extract cost info from response
        self._extract_costs_from_response(response)
        self._step_count += 1

        return response

    def after_model(self, state, runtime) -> Optional[Dict[str, Any]]:
        """After model hook for TodoList enforcement.

        1. Prevent parallel TodoWrite calls
        2. Force continue if tasks are incomplete
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # Find last AI message
        last_ai = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai = msg
                break

        if not last_ai:
            return None

        tool_calls = getattr(last_ai, "tool_calls", None) or []

        # 1. Prevent parallel TodoWrite calls
        todowrite_calls = [tc for tc in tool_calls if tc.get("name") == "TodoWrite"]
        if len(todowrite_calls) > 1:
            error_messages = [
                ToolMessage(
                    content=(
                        "Error: TodoWrite should never be called multiple times "
                        "in parallel. Please call it only once per model invocation."
                    ),
                    tool_call_id=tc["id"],
                    status="error",
                )
                for tc in todowrite_calls
            ]
            return {"messages": error_messages}

        # 2. Force continue if tasks incomplete and model didn't request tools
        if not tool_calls and self._tasks and not self._all_tasks_completed():
            if self._force_continue_count < MAX_FORCE_CONTINUE_COUNT:
                self._force_continue_count += 1
                force_msg = self._get_force_continue_message()
                logger.info(
                    f"Forcing agent to continue "
                    f"(attempt {self._force_continue_count}, "
                    f"{self._count_incomplete_tasks()} tasks remaining)"
                )
                return {
                    "messages": [SystemMessage(content=force_msg)],
                    "jump_to": "model",
                }
            else:
                logger.warning(
                    f"Force continue limit reached ({MAX_FORCE_CONTINUE_COUNT}), "
                    f"allowing agent to end despite incomplete tasks"
                )

        return None

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _all_tasks_completed(self) -> bool:
        if not self._tasks:
            return True
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in self._tasks
        )

    def _count_incomplete_tasks(self) -> int:
        return sum(
            1 for t in self._tasks
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        )

    def _get_force_continue_message(self) -> str:
        incomplete = [
            t for t in self._tasks
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)
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

    def _extract_costs_from_response(self, response) -> None:
        """Extract cost and token info from ModelResponse."""
        # ModelResponse has result: list[BaseMessage]
        result_messages = getattr(response, "result", [])
        if not result_messages:
            return

        for msg in result_messages:
            metadata = getattr(msg, "response_metadata", {}) or {}
            usage = metadata.get("token_usage") or metadata.get("usage", {})
            if usage:
                self._prompt_tokens += usage.get("prompt_tokens", 0)
                self._completion_tokens += usage.get("completion_tokens", 0)
                self._total_tokens += usage.get("total_tokens", 0)
            self._total_cost += float(metadata.get("response_cost", 0) or 0)

    def reset(self) -> None:
        """Reset middleware state for a new interaction."""
        self._step_count = 0
        self._tasks = []
        self._task_updates_count = 0
        self._force_continue_count = 0
        self._runbook_in_use = False
        self._tool_call_results = []
        self._tool_calls_history = []
        self._total_cost = 0.0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._metadata = {}
        self._tool_number_offset = 0


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
