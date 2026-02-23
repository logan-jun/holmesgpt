"""LLM invocation node for the Holmes LangGraph agent.

Handles context window management, tool binding, cost tracking,
and TodoList status injection.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from holmes.common.env_vars import (
    RESET_REPEATED_TOOL_CALL_CHECK_AFTER_COMPACTION,
    TEMPERATURE,
)
from holmes.core.langchain.message_converter import langchain_to_openai, openai_to_langchain
from holmes.core.langchain.state import HolmesAgentState
from holmes.core.truncation.input_context_window_limiter import limit_input_context_window
from holmes.utils.tags import parse_messages_tags

logger = logging.getLogger(__name__)


def call_model(state: HolmesAgentState, config: RunnableConfig) -> dict:
    """LLM invocation node.

    1. Convert messages to OpenAI format for context window limiter
    2. Apply context window management
    3. Get tools (respecting runbook restriction state)
    4. Bind tools to ChatLiteLLM and invoke
    5. Extract cost info and return state updates
    """
    configurable = config["configurable"]
    chat_model = configurable["chat_model"]
    holmes_llm = configurable["holmes_llm"]
    tool_executor = configurable["tool_executor"]
    todo_middleware = configurable.get("todo_middleware")
    response_format = configurable.get("response_format")

    step = state["step_count"] + 1
    max_steps = state["max_steps"]
    metadata = dict(state.get("metadata", {}))

    # Get tools in OpenAI format (may include restricted if runbook active)
    include_restricted = state.get("runbook_in_use", False)
    tools = tool_executor.get_all_tools_openai_format(
        target_model=holmes_llm.model,
        include_restricted=include_restricted,
    )

    # On last step: no tools, force final text answer
    if step >= max_steps:
        tools = None

    # Convert LangChain messages to OpenAI format for context window limiter
    openai_messages = langchain_to_openai(state["messages"])

    # Context window management (reuses Holmes' existing limiter)
    limit_result = limit_input_context_window(
        llm=holmes_llm, messages=openai_messages, tools=tools
    )
    openai_messages = limit_result.messages
    metadata = metadata | limit_result.metadata

    # Reset repeated tool call check if conversation was compacted
    tool_calls_history = list(state.get("tool_calls_history", []))
    if limit_result.conversation_history_compacted and RESET_REPEATED_TOOL_CALL_CHECK_AFTER_COMPACTION:
        tool_calls_history = []

    # Inject TodoList status before model call
    if todo_middleware:
        task_injection = todo_middleware.get_task_status_injection()
        if task_injection:
            openai_messages.append({"role": "system", "content": task_injection})

    # Convert back to LangChain messages for ChatLiteLLM
    lc_messages = openai_to_langchain(parse_messages_tags(openai_messages))

    # Bind tools and invoke
    if tools:
        bound_model = chat_model.bind_tools(tools, tool_choice="auto")
    else:
        bound_model = chat_model

    invoke_kwargs: Dict[str, Any] = {}
    if response_format:
        invoke_kwargs["response_format"] = response_format

    response: AIMessage = bound_model.invoke(lc_messages, **invoke_kwargs)

    # Extract cost info from response metadata
    cost_update = _extract_costs_from_response(response)

    return {
        "messages": [response],
        "step_count": step,
        "tool_calls_history": tool_calls_history,
        "total_cost": state.get("total_cost", 0.0) + cost_update.get("cost", 0.0),
        "prompt_tokens": state.get("prompt_tokens", 0) + cost_update.get("prompt_tokens", 0),
        "completion_tokens": state.get("completion_tokens", 0) + cost_update.get("completion_tokens", 0),
        "total_tokens": state.get("total_tokens", 0) + cost_update.get("total_tokens", 0),
        "metadata": metadata,
    }


def call_model_force_continue(state: HolmesAgentState, config: RunnableConfig) -> dict:
    """Inject a force-continue system message when TodoList has incomplete tasks.

    This node is entered when the model tried to end but tasks remain incomplete.
    It adds a reminder message and routes back to call_model.
    """
    todo_middleware = config["configurable"].get("todo_middleware")
    if todo_middleware:
        force_msg = todo_middleware.get_force_continue_message()
        return {
            "messages": [SystemMessage(content=force_msg)],
        }
    return {}


def _extract_costs_from_response(response: AIMessage) -> dict:
    """Extract cost and token info from LangChain AIMessage response_metadata."""
    result = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    metadata = getattr(response, "response_metadata", {}) or {}
    usage = metadata.get("token_usage") or metadata.get("usage", {})

    if usage:
        result["prompt_tokens"] = usage.get("prompt_tokens", 0)
        result["completion_tokens"] = usage.get("completion_tokens", 0)
        result["total_tokens"] = usage.get("total_tokens", 0)

    # LiteLLM stores cost in _hidden_params via response_metadata
    result["cost"] = float(metadata.get("response_cost", 0) or 0)

    return result
