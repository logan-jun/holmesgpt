"""Parallel tool execution node for the Holmes LangGraph agent.

Executes tool calls using Holmes' native tool invocation with ThreadPoolExecutor(16),
preserving all existing safeguards, approval handling, and context management.
"""

import concurrent.futures
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from holmes.core.langchain.state import HolmesAgentState
from holmes.core.models import ToolCallResult, format_tool_result_data
from holmes.core.safeguards import prevent_overly_repeated_tool_call
from holmes.core.tools import (
    StructuredToolResult,
    StructuredToolResultStatus,
    ToolInvokeContext,
)
from holmes.core.tools_utils.tool_context_window_limiter import prevent_overly_big_tool_response

logger = logging.getLogger(__name__)

TODO_WRITE_TOOL_NAME = "TodoWrite"


def execute_tools(state: HolmesAgentState, config: RunnableConfig) -> dict:
    """Execute all tool calls from the last AI message in parallel.

    Uses ThreadPoolExecutor(max_workers=16) for parallel execution,
    identical to the original ToolCallingLLM implementation.
    """
    configurable = config["configurable"]
    tool_executor = configurable["tool_executor"]
    holmes_llm = configurable["holmes_llm"]
    approval_callback = configurable.get("approval_callback")
    todo_middleware = configurable.get("todo_middleware")

    last_ai_message = state["messages"][-1]
    tool_calls = last_ai_message.tool_calls

    if not tool_calls:
        return {}

    tool_calls_history = list(state.get("tool_calls_history", []))
    all_results = list(state.get("all_tool_call_results", []))
    tool_number_offset = state.get("tool_number_offset", 0)
    pending_approvals: List[dict] = []
    tool_messages: List[ToolMessage] = []
    runbook_in_use = state.get("runbook_in_use", False)
    tasks = list(state.get("tasks", []))

    request_context = configurable.get("request_context")
    session_approved_prefixes: List[str] = []  # TODO: extract from messages if needed

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures: Dict[concurrent.futures.Future, tuple] = {}

        for idx, tool_call in enumerate(tool_calls, 1):
            tool_number = tool_number_offset + idx
            future = executor.submit(
                _invoke_single_tool,
                tool_executor=tool_executor,
                holmes_llm=holmes_llm,
                tool_name=tool_call["name"],
                tool_args=tool_call.get("args", {}),
                tool_call_id=tool_call["id"],
                tool_number=tool_number,
                tool_calls_history=tool_calls_history,
                session_approved_prefixes=session_approved_prefixes,
                request_context=request_context,
            )
            futures[future] = (tool_call, tool_number)

        for future in concurrent.futures.as_completed(futures):
            tool_call, tool_number = futures[future]
            result: ToolCallResult = future.result()

            # Handle approval requirement
            if result.result.status == StructuredToolResultStatus.APPROVAL_REQUIRED:
                if approval_callback:
                    approved, feedback = approval_callback(result.result)
                    if approved:
                        result = _re_invoke_approved(
                            tool_executor, holmes_llm, result, request_context
                        )
                    else:
                        result.result = StructuredToolResult(
                            status=StructuredToolResultStatus.ERROR,
                            error=f"User denied execution. {feedback or ''}",
                            params=result.result.params,
                        )
                else:
                    pending_approvals.append(
                        {
                            "tool_call_id": result.tool_call_id,
                            "tool_name": result.tool_name,
                            "description": result.description,
                            "params": result.result.params or {},
                        }
                    )

            # Oversized response check
            prevent_overly_big_tool_response(tool_call_result=result, llm=holmes_llm)

            # Track runbook activation
            if (
                result.tool_name == "fetch_runbook"
                and result.result.status == StructuredToolResultStatus.SUCCESS
            ):
                runbook_in_use = True
                logger.debug("Runbook fetched - restricted tools now available")

            # Track TodoWrite calls -> update middleware state
            if result.tool_name == TODO_WRITE_TOOL_NAME and result.result.status == StructuredToolResultStatus.SUCCESS:
                if result.result.params and "todos" in result.result.params:
                    tasks = result.result.params["todos"]
                    if todo_middleware:
                        todo_middleware.update_tasks(tasks)

            # Build ToolMessage for LangChain message history
            content = format_tool_result_data(
                tool_result=result.result,
                tool_call_id=result.tool_call_id,
                tool_name=result.tool_name,
            )
            tool_messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=result.tool_call_id,
                    name=result.tool_name,
                )
            )

            # Track for safeguards and accumulated results
            tool_result_dict = result.as_tool_result_response()
            tool_calls_history.append(tool_result_dict)
            all_results.append(tool_result_dict)

    return {
        "messages": tool_messages,
        "tool_calls_history": tool_calls_history,
        "all_tool_call_results": all_results,
        "tool_number_offset": tool_number_offset + len(tool_calls),
        "pending_approvals": pending_approvals,
        "runbook_in_use": runbook_in_use,
        "tasks": tasks,
    }


def _invoke_single_tool(
    tool_executor,
    holmes_llm,
    tool_name: str,
    tool_args: dict,
    tool_call_id: str,
    tool_number: int,
    tool_calls_history: list,
    session_approved_prefixes: Optional[List[str]] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> ToolCallResult:
    """Invoke a single Holmes tool (runs in thread pool).

    Mirrors ToolCallingLLM._get_tool_call_result() + _directly_invoke_tool_call().
    """
    tool = tool_executor.get_tool_by_name(tool_name)
    if not tool:
        logger.warning(f"Tool not found: {tool_name}")
        return ToolCallResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            description=tool_name,
            result=StructuredToolResult(
                status=StructuredToolResultStatus.ERROR,
                error=f"Failed to find tool {tool_name}",
                params=tool_args,
            ),
        )

    # Safeguard: detect repeated tool calls
    repeated_result = prevent_overly_repeated_tool_call(
        tool_name=tool_name,
        tool_params=tool_args,
        tool_calls=tool_calls_history,
    )
    if repeated_result:
        return ToolCallResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            description=str(tool.get_parameterized_one_liner(tool_args)),
            result=repeated_result,
        )

    # Invoke the tool with Holmes' native context
    context = ToolInvokeContext(
        tool_number=tool_number,
        user_approved=False,
        llm=holmes_llm,
        max_token_count=holmes_llm.get_max_token_count_for_single_tool(),
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        session_approved_prefixes=session_approved_prefixes or [],
        request_context=request_context,
    )

    try:
        tool_response = tool.invoke(tool_args, context=context)
    except Exception as e:
        logger.error(f"Tool call to {tool_name} failed", exc_info=True)
        tool_response = StructuredToolResult(
            status=StructuredToolResultStatus.ERROR,
            error=f"Tool call failed: {e}",
            params=tool_args,
        )

    if not isinstance(tool_response, StructuredToolResult):
        logger.error(f"Tool {tool_name} did not return StructuredToolResult, wrapping")
        tool_response = StructuredToolResult(
            status=StructuredToolResultStatus.SUCCESS,
            data=tool_response,
            params=tool_args,
        )

    return ToolCallResult(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        description=str(tool.get_parameterized_one_liner(tool_args)),
        result=tool_response,
    )


def _re_invoke_approved(
    tool_executor,
    holmes_llm,
    original_result: ToolCallResult,
    request_context: Optional[Dict[str, Any]] = None,
) -> ToolCallResult:
    """Re-invoke a tool after user approval."""
    tool = tool_executor.get_tool_by_name(original_result.tool_name)
    if not tool:
        return original_result

    context = ToolInvokeContext(
        tool_number=None,
        user_approved=True,
        llm=holmes_llm,
        max_token_count=holmes_llm.get_max_token_count_for_single_tool(),
        tool_name=original_result.tool_name,
        tool_call_id=original_result.tool_call_id,
        session_approved_prefixes=[],
        request_context=request_context,
    )

    try:
        tool_response = tool.invoke(original_result.result.params or {}, context=context)
    except Exception as e:
        tool_response = StructuredToolResult(
            status=StructuredToolResultStatus.ERROR,
            error=f"Approved tool call failed: {e}",
            params=original_result.result.params,
        )

    return ToolCallResult(
        tool_call_id=original_result.tool_call_id,
        tool_name=original_result.tool_name,
        description=original_result.description,
        result=tool_response,
    )
