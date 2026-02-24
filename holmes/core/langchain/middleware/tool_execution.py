"""Holmes Tool Execution Middleware for LangChain create_agent().

Intercepts tool calls via wrap_tool_call to bypass the default LangChain
ToolNode handler and execute Holmes tools directly with:
- Holmes ToolInvokeContext (native execution)
- Repeated call safeguards
- Response size limiting
- Approval handling
- Runbook activation tracking
- TodoWrite state synchronization
"""

import logging
from typing import Any, Dict, List, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

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


class HolmesToolExecutionMiddleware(AgentMiddleware):
    """Middleware that intercepts tool execution to use Holmes' native tools.

    wrap_tool_call bypasses the default LangChain handler and invokes
    Holmes tools directly via ToolExecutor, preserving all safeguards.
    """

    name = "holmes_tool_execution"

    def wrap_tool_call(self, request, handler) -> ToolMessage:
        """Execute Holmes tool directly, bypassing default handler.

        Args:
            request: ToolCallRequest with tool_call dict, tool, state, runtime
            handler: Default handler (NOT called - we bypass it)

        Returns:
            ToolMessage with the tool execution result
        """
        tool_call = request.tool_call
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call["id"]

        # Access configurable from ToolRuntime (which has config field)
        config = request.runtime.config
        configurable = config.get("configurable", {})
        tool_executor = configurable["tool_executor"]
        holmes_llm = configurable["holmes_llm"]
        investigation_mw = configurable["investigation_middleware"]
        approval_callback = configurable.get("approval_callback")
        request_context = configurable.get("request_context")

        # 1. Find Holmes tool
        tool = tool_executor.get_tool_by_name(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return ToolMessage(
                content=f"Error: Failed to find tool {tool_name}",
                tool_call_id=tool_call_id,
                name=tool_name,
                status="error",
            )

        # 2. Repeated call safeguard
        repeated_result = prevent_overly_repeated_tool_call(
            tool_name=tool_name,
            tool_params=tool_args,
            tool_calls=investigation_mw.tool_history,
        )
        if repeated_result:
            result = ToolCallResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                description=str(tool.get_parameterized_one_liner(tool_args)),
                result=repeated_result,
            )
            content = format_tool_result_data(
                tool_result=result.result,
                tool_call_id=result.tool_call_id,
                tool_name=result.tool_name,
            )
            investigation_mw.record_tool_result(result.as_tool_result_response())
            return ToolMessage(
                content=content,
                tool_call_id=tool_call_id,
                name=tool_name,
            )

        # 3. Invoke with Holmes ToolInvokeContext
        tool_number = investigation_mw.next_tool_number()
        session_approved_prefixes: List[str] = []  # TODO: extract from state if needed

        context = ToolInvokeContext(
            tool_number=tool_number,
            user_approved=False,
            llm=holmes_llm,
            max_token_count=holmes_llm.get_max_token_count_for_single_tool(),
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            session_approved_prefixes=session_approved_prefixes,
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

        # 4. Handle approval requirement
        if tool_response.status == StructuredToolResultStatus.APPROVAL_REQUIRED:
            if approval_callback:
                approved, feedback = approval_callback(tool_response)
                if approved:
                    tool_response = _re_invoke_approved(
                        tool, tool_args, holmes_llm, request_context
                    )
                else:
                    tool_response = StructuredToolResult(
                        status=StructuredToolResultStatus.ERROR,
                        error=f"User denied execution. {feedback or ''}",
                        params=tool_response.params,
                    )

        result = ToolCallResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            description=str(tool.get_parameterized_one_liner(tool_args)),
            result=tool_response,
        )

        # 5. Oversized response check
        prevent_overly_big_tool_response(tool_call_result=result, llm=holmes_llm)

        # 6. Track runbook activation
        if (
            tool_name == "fetch_runbook"
            and result.result.status == StructuredToolResultStatus.SUCCESS
        ):
            investigation_mw.activate_runbook()

        # 7. Track TodoWrite calls
        if (
            tool_name == TODO_WRITE_TOOL_NAME
            and result.result.status == StructuredToolResultStatus.SUCCESS
        ):
            if result.result.params and "todos" in result.result.params:
                investigation_mw.update_tasks(result.result.params["todos"])

        # 8. Record tool result in investigation middleware
        investigation_mw.record_tool_result(result.as_tool_result_response())

        # 9. Build ToolMessage for LangChain message history
        content = format_tool_result_data(
            tool_result=result.result,
            tool_call_id=result.tool_call_id,
            tool_name=result.tool_name,
        )
        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=tool_name,
        )


def _re_invoke_approved(
    tool,
    tool_args: dict,
    holmes_llm,
    request_context: Optional[Dict[str, Any]] = None,
) -> StructuredToolResult:
    """Re-invoke a tool after user approval."""
    context = ToolInvokeContext(
        tool_number=None,
        user_approved=True,
        llm=holmes_llm,
        max_token_count=holmes_llm.get_max_token_count_for_single_tool(),
        tool_name=tool.name,
        tool_call_id="",
        session_approved_prefixes=[],
        request_context=request_context,
    )

    try:
        return tool.invoke(tool_args, context=context)
    except Exception as e:
        return StructuredToolResult(
            status=StructuredToolResultStatus.ERROR,
            error=f"Approved tool call failed: {e}",
            params=tool_args,
        )
