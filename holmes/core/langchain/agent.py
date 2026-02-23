"""HolmesReActAgent - LangGraph-based drop-in replacement for ToolCallingLLM.

Provides identical interface to ToolCallingLLM so it can be swapped via feature flag
without changing any calling code.
"""

import json
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Type, Union

from pydantic import BaseModel

from holmes.core.issue import Issue
from holmes.core.langchain.callbacks import HolmesCostTracker
from holmes.core.langchain.graph import build_holmes_graph
from holmes.core.langchain.llm_adapter import HolmesChatModelFactory
from holmes.core.langchain.message_converter import langchain_to_openai, openai_to_langchain
from holmes.core.langchain.state import HolmesAgentState
from holmes.core.langchain.todo_middleware import TodoListMiddleware
from holmes.core.llm import LLM
from holmes.core.models import ToolApprovalDecision, ToolCallResult
from holmes.core.tool_calling_llm import LLMResult
from holmes.core.tools import StructuredToolResult, StructuredToolResultStatus
from holmes.core.tools_utils.tool_executor import ToolExecutor
from holmes.core.tracing import DummySpan
from holmes.utils.stream import StreamEvents, StreamMessage

logger = logging.getLogger(__name__)


class HolmesReActAgent:
    """LangGraph-based ReAct agent. Drop-in replacement for ToolCallingLLM.

    Uses LangGraph StateGraph for the agent loop while reusing Holmes'
    native tool execution, safeguards, and context window management.
    """

    llm: LLM  # Matches ToolCallingLLM attribute

    def __init__(
        self, tool_executor: ToolExecutor, max_steps: int, llm: LLM, tracer=None
    ):
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.llm = llm
        self.tracer = tracer
        self.approval_callback: Optional[
            Callable[[StructuredToolResult], tuple[bool, Optional[str]]]
        ] = None
        self._runbook_in_use: bool = False
        self._todo_middleware = TodoListMiddleware()

        # Create LangChain chat model from Holmes LLM config
        self._chat_model = HolmesChatModelFactory.create(llm)

        # Build the compiled graph
        graph_builder = build_holmes_graph()
        self._graph = graph_builder.compile()

    def reset_interaction_state(self) -> None:
        """Reset state for interactive loop (matches ToolCallingLLM interface)."""
        self._runbook_in_use = False
        self._todo_middleware.reset()

    def prompt_call(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Union[dict, Type[BaseModel]]] = None,
        sections=None,
        trace_span=DummySpan(),
        request_context: Optional[Dict[str, Any]] = None,
    ) -> LLMResult:
        """Matches ToolCallingLLM.prompt_call() interface."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.call(
            messages,
            response_format=response_format,
            user_prompt=user_prompt,
            sections=sections,
            trace_span=trace_span,
            request_context=request_context,
        )

    def messages_call(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Union[dict, Type[BaseModel]]] = None,
        trace_span=DummySpan(),
        request_context: Optional[Dict[str, Any]] = None,
    ) -> LLMResult:
        """Matches ToolCallingLLM.messages_call() interface."""
        return self.call(
            messages,
            response_format=response_format,
            trace_span=trace_span,
            request_context=request_context,
        )

    def call(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Union[dict, Type[BaseModel]]] = None,
        user_prompt: Optional[str] = None,
        sections=None,
        trace_span=DummySpan(),
        tool_number_offset: int = 0,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> LLMResult:
        """Run the LangGraph agent and return LLMResult.

        Matches ToolCallingLLM.call() interface exactly.
        """
        lc_messages = openai_to_langchain(messages)

        initial_state: HolmesAgentState = {
            "messages": lc_messages,
            "tool_calls_history": [],
            "all_tool_call_results": [],
            "tool_number_offset": tool_number_offset,
            "step_count": 0,
            "max_steps": self.max_steps,
            "total_cost": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "runbook_in_use": self._runbook_in_use,
            "tasks": [],
            "pending_approvals": [],
            "metadata": {},
        }

        config = {
            "configurable": {
                "chat_model": self._chat_model,
                "holmes_llm": self.llm,
                "tool_executor": self.tool_executor,
                "approval_callback": self.approval_callback,
                "todo_middleware": self._todo_middleware,
                "request_context": request_context,
                "response_format": response_format,
                "sections": sections,
            }
        }

        # Run the graph to completion
        final_state = self._graph.invoke(initial_state, config)

        # Update persistent state from graph result
        self._runbook_in_use = final_state.get("runbook_in_use", False)

        # Extract final text response
        last_message = final_state["messages"][-1]
        text_response = getattr(last_message, "content", None)
        if isinstance(text_response, list):
            # Handle content arrays (vision/cache_control)
            text_response = " ".join(
                item.get("text", "") for item in text_response if isinstance(item, dict)
            )

        # Convert messages back to OpenAI format for LLMResult
        openai_messages = langchain_to_openai(final_state["messages"])

        # Build tool_calls list from accumulated results
        tool_calls = _build_tool_call_results(final_state.get("all_tool_call_results", []))

        return LLMResult(
            result=text_response,
            tool_calls=tool_calls,
            num_llm_calls=final_state.get("step_count", 0),
            prompt=json.dumps(openai_messages, indent=2),
            messages=openai_messages,
            total_cost=final_state.get("total_cost", 0.0),
            prompt_tokens=final_state.get("prompt_tokens", 0),
            completion_tokens=final_state.get("completion_tokens", 0),
            total_tokens=final_state.get("total_tokens", 0),
            metadata=final_state.get("metadata"),
        )

    def call_stream(
        self,
        system_prompt: str = "",
        user_prompt: Optional[str] = None,
        response_format: Optional[Union[dict, Type[BaseModel]]] = None,
        sections=None,
        msgs: Optional[list[dict]] = None,
        enable_tool_approval: bool = False,
        tool_decisions: Optional[List[ToolApprovalDecision]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Generator[StreamMessage, None, None]:
        """Stream agent execution, yielding StreamMessage events.

        Matches ToolCallingLLM.call_stream() interface.
        """
        # Process tool decisions if provided (resume from approval)
        if msgs and tool_decisions:
            logger.info(f"Processing {len(tool_decisions)} tool decisions")
            msgs, events = self.process_tool_decisions(msgs, tool_decisions, request_context)
            yield from events

        # Build messages
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if msgs:
            messages.extend(msgs)

        lc_messages = openai_to_langchain(messages)

        initial_state: HolmesAgentState = {
            "messages": lc_messages,
            "tool_calls_history": [],
            "all_tool_call_results": [],
            "tool_number_offset": 0,
            "step_count": 0,
            "max_steps": self.max_steps,
            "total_cost": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "runbook_in_use": self._runbook_in_use,
            "tasks": [],
            "pending_approvals": [],
            "metadata": {},
        }

        config = {
            "configurable": {
                "chat_model": self._chat_model,
                "holmes_llm": self.llm,
                "tool_executor": self.tool_executor,
                "approval_callback": self.approval_callback if not enable_tool_approval else None,
                "todo_middleware": self._todo_middleware,
                "request_context": request_context,
                "response_format": response_format,
                "sections": sections,
            }
        }

        # Stream graph execution, converting events to StreamMessages
        for event in self._graph.stream(initial_state, config, stream_mode="updates"):
            yield from _convert_graph_event_to_stream(event)

        # After streaming completes, update persistent state
        # Note: final state is available from the last event

    def process_tool_decisions(
        self,
        messages: List[Dict[str, Any]],
        tool_decisions: List[ToolApprovalDecision],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], list[StreamMessage]]:
        """Process tool approval decisions (matches ToolCallingLLM interface).

        Delegates to the same logic as the original implementation.
        """
        events: list[StreamMessage] = []
        if not tool_decisions:
            return messages, events

        decisions_by_id = {d.tool_call_id: d for d in tool_decisions}

        for i in reversed(range(len(messages))):
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tool_call in msg.get("tool_calls", []):
                    decision = decisions_by_id.get(tool_call.get("id"))
                    if tool_call.get("pending_approval") and decision:
                        del tool_call["pending_approval"]

                        if decision.approved:
                            result = self._directly_invoke_tool(
                                tool_name=tool_call["function"]["name"],
                                tool_args=json.loads(tool_call["function"].get("arguments", "{}")),
                                tool_call_id=tool_call["id"],
                                user_approved=True,
                                request_context=request_context,
                            )
                        else:
                            result = ToolCallResult(
                                tool_call_id=tool_call["id"],
                                tool_name=tool_call["function"]["name"],
                                description=tool_call["function"]["name"],
                                result=StructuredToolResult(
                                    status=StructuredToolResultStatus.ERROR,
                                    error="Tool execution was denied by the user.",
                                ),
                            )

                        events.append(
                            StreamMessage(
                                event=StreamEvents.TOOL_RESULT,
                                data=result.as_streaming_tool_result_response(),
                            )
                        )

                        extra_metadata = None
                        if decision.approved and decision.save_prefixes:
                            extra_metadata = {"bash_session_approved_prefixes": decision.save_prefixes}

                        messages.insert(i + 1, result.as_tool_call_message(extra_metadata=extra_metadata))

        return messages, events

    def _directly_invoke_tool(
        self,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        user_approved: bool = False,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> ToolCallResult:
        """Directly invoke a single tool (for approval processing)."""
        from holmes.core.tools import ToolInvokeContext

        tool = self.tool_executor.get_tool_by_name(tool_name)
        if not tool:
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

        context = ToolInvokeContext(
            tool_number=None,
            user_approved=user_approved,
            llm=self.llm,
            max_token_count=self.llm.get_max_token_count_for_single_tool(),
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            session_approved_prefixes=[],
            request_context=request_context,
        )

        try:
            tool_response = tool.invoke(tool_args, context=context)
        except Exception as e:
            tool_response = StructuredToolResult(
                status=StructuredToolResultStatus.ERROR,
                error=f"Tool call failed: {e}",
                params=tool_args,
            )

        return ToolCallResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            description=str(tool.get_parameterized_one_liner(tool_args)),
            result=tool_response,
        )


class LangChainIssueInvestigator(HolmesReActAgent):
    """LangGraph-based issue investigator. Replaces IssueInvestigator.

    Provides the same investigate() interface for issue analysis.
    """

    def __init__(
        self,
        tool_executor: ToolExecutor,
        max_steps: int,
        llm: LLM,
        cluster_name: Optional[str] = None,
        tracer=None,
    ):
        super().__init__(tool_executor, max_steps, llm, tracer)
        self.cluster_name = cluster_name

    def investigate(
        self,
        issue: Issue,
        prompt: str,
        console: Optional[Any] = None,
        global_instructions: Optional[Any] = None,
        sections=None,
        trace_span=DummySpan(),
        runbooks=None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> LLMResult:
        """Investigate an issue (matches IssueInvestigator.investigate() interface).

        Uses the same prompt rendering as the original, then delegates to
        the LangGraph agent for execution.
        """
        import logging
        import textwrap

        from holmes.core.investigation_structured_output import (
            DEFAULT_SECTIONS,
            REQUEST_STRUCTURED_OUTPUT_FROM_LLM,
            get_output_format_for_investigation,
        )
        from holmes.core.prompt import generate_user_prompt, load_and_render_prompt
        from holmes.utils.global_instructions import generate_runbooks_args

        request_structured_output_from_llm = True
        response_format = None

        if not sections or len(sections) == 0:
            sections = DEFAULT_SECTIONS
            request_structured_output_from_llm = False

        elif self.llm.model and self.llm.model.startswith("bedrock"):
            request_structured_output_from_llm = False

        if not REQUEST_STRUCTURED_OUTPUT_FROM_LLM:
            request_structured_output_from_llm = False

        if request_structured_output_from_llm:
            response_format = get_output_format_for_investigation(sections)

        # Build system prompt using the same template as IssueInvestigator
        system_prompt = load_and_render_prompt(
            prompt,
            {
                "issue": issue,
                "sections": sections,
                "structured_output": request_structured_output_from_llm,
                "toolsets": self.tool_executor.toolsets,
                "cluster_name": self.cluster_name,
                "runbooks_enabled": True if runbooks else False,
            },
        )

        # Build user prompt
        base_user = f"\n #This is context from the issue:\n{issue.raw}"
        runbooks_ctx = generate_runbooks_args(
            runbook_catalog=runbooks,
            global_instructions=global_instructions,
        )
        user_prompt = generate_user_prompt(base_user, runbooks_ctx)

        logging.debug("Rendered system prompt:\n%s", textwrap.indent(system_prompt, "    "))
        logging.debug("Rendered user prompt:\n%s", textwrap.indent(user_prompt, "    "))

        return self.prompt_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            sections=sections,
            trace_span=trace_span,
            request_context=request_context,
        )


def _build_tool_call_results(results_dicts: List[dict]) -> List[ToolCallResult]:
    """Reconstruct ToolCallResult objects from accumulated dict results."""
    tool_calls = []
    for r in results_dicts:
        result_data = r.get("result", {})
        tool_calls.append(
            ToolCallResult(
                tool_call_id=r.get("tool_call_id", ""),
                tool_name=r.get("tool_name", ""),
                description=r.get("description", ""),
                result=StructuredToolResult(
                    status=StructuredToolResultStatus(result_data.get("status", "SUCCESS")),
                    data=result_data.get("data"),
                    error=result_data.get("error"),
                    params=result_data.get("params"),
                    invocation=result_data.get("invocation"),
                ),
            )
        )
    return tool_calls


def _convert_graph_event_to_stream(event: dict) -> Generator[StreamMessage, None, None]:
    """Convert LangGraph stream events to Holmes StreamMessage format."""
    for node_name, state_update in event.items():
        if node_name == "execute_tools":
            # Tool execution completed - emit tool result events
            messages = state_update.get("messages", [])
            for msg in messages:
                if hasattr(msg, "name") and hasattr(msg, "content"):
                    yield StreamMessage(
                        event=StreamEvents.TOOL_RESULT,
                        data={
                            "tool_name": msg.name or "",
                            "tool_call_id": getattr(msg, "tool_call_id", ""),
                            "result": msg.content[:500] if msg.content else "",
                        },
                    )
        elif node_name == "call_model":
            messages = state_update.get("messages", [])
            for msg in messages:
                content = getattr(msg, "content", "")
                if content and not getattr(msg, "tool_calls", None):
                    yield StreamMessage(
                        event=StreamEvents.AI_MESSAGE,
                        data={"message": content},
                    )
