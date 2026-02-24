"""HolmesReActAgent - LangChain create_agent()-based agent.

Drop-in replacement for ToolCallingLLM, using create_agent() with custom middleware
instead of a hand-built StateGraph. Provides identical interface so it can be
swapped via feature flag without changing any calling code.
"""

import json
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Type, Union

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from holmes.core.issue import Issue
from holmes.core.langchain.llm_adapter import HolmesChatModelFactory
from holmes.core.langchain.message_converter import langchain_to_openai, openai_to_langchain
from holmes.core.langchain.middleware.investigation import HolmesInvestigationMiddleware
from holmes.core.langchain.middleware.tool_execution import HolmesToolExecutionMiddleware
from holmes.core.langchain.tool_adapter import create_langchain_tools
from holmes.core.llm import LLM
from holmes.core.models import ToolApprovalDecision, ToolCallResult
from holmes.core.tool_calling_llm import LLMResult
from holmes.core.tools import StructuredToolResult, StructuredToolResultStatus
from holmes.core.tools_utils.tool_executor import ToolExecutor
from holmes.core.tracing import DummySpan
from holmes.utils.stream import StreamEvents, StreamMessage

logger = logging.getLogger(__name__)


class HolmesReActAgent:
    """LangChain create_agent()-based ReAct agent.

    Drop-in replacement for ToolCallingLLM using LangChain's standard agent pattern
    with custom middleware for Holmes-specific logic.
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

        # Create LangChain chat model from Holmes LLM config
        self._chat_model = HolmesChatModelFactory.create(llm)

        # Create middleware instances
        self._investigation_mw = HolmesInvestigationMiddleware(
            max_steps=max_steps,
            tool_executor=tool_executor,
            holmes_llm=llm,
        )
        self._tool_execution_mw = HolmesToolExecutionMiddleware()

        # Create placeholder tools (schema only, execution in wrap_tool_call)
        self._base_tools = create_langchain_tools(tool_executor, llm.model)

        # Build the agent graph via create_agent()
        self._graph = create_agent(
            model=self._chat_model,
            tools=self._base_tools if self._base_tools else None,
            system_prompt=None,  # Dynamic injection via wrap_model_call
            middleware=[self._investigation_mw, self._tool_execution_mw],
        )

    def reset_interaction_state(self) -> None:
        """Reset state for interactive loop (matches ToolCallingLLM interface)."""
        self._investigation_mw.reset()

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
        """Run the agent and return LLMResult.

        Matches ToolCallingLLM.call() interface exactly.
        """
        # Reset middleware for fresh invocation
        self._investigation_mw.reset()

        # Extract system prompt for dynamic injection via middleware
        system_prompt = None
        non_system_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            else:
                non_system_messages.append(msg)

        # Convert to LangChain format (without system - injected by middleware)
        lc_messages = openai_to_langchain(non_system_messages)

        config = {
            "configurable": {
                "system_prompt": system_prompt,
                "tool_executor": self.tool_executor,
                "holmes_llm": self.llm,
                "investigation_middleware": self._investigation_mw,
                "approval_callback": self.approval_callback,
                "request_context": request_context,
                "response_format": response_format,
                "sections": sections,
            },
            "max_concurrency": 16,  # Parallel tool execution workers
        }

        # Run the graph to completion
        final_state = self._graph.invoke({"messages": lc_messages}, config)

        # Extract final text response
        last_message = final_state["messages"][-1]
        text_response = getattr(last_message, "content", None)
        if isinstance(text_response, list):
            text_response = " ".join(
                item.get("text", "") for item in text_response if isinstance(item, dict)
            )

        # Convert messages back to OpenAI format for LLMResult
        openai_messages = langchain_to_openai(final_state["messages"])

        # Build tool_calls list from middleware's accumulated results
        tool_calls = _build_tool_call_results(
            self._investigation_mw.get_tool_call_results()
        )

        costs = self._investigation_mw.costs

        return LLMResult(
            result=text_response,
            tool_calls=tool_calls,
            num_llm_calls=self._investigation_mw.step_count,
            prompt=json.dumps(openai_messages, indent=2),
            messages=openai_messages,
            total_cost=costs["total_cost"],
            prompt_tokens=costs["prompt_tokens"],
            completion_tokens=costs["completion_tokens"],
            total_tokens=costs["total_tokens"],
            metadata=self._investigation_mw._metadata,
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

        # Reset middleware for fresh invocation
        self._investigation_mw.reset()

        # Build messages
        messages: list[dict] = []
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if msgs:
            messages.extend(msgs)

        lc_messages = openai_to_langchain(messages)

        config = {
            "configurable": {
                "system_prompt": system_prompt if system_prompt else None,
                "tool_executor": self.tool_executor,
                "holmes_llm": self.llm,
                "investigation_middleware": self._investigation_mw,
                "approval_callback": self.approval_callback if not enable_tool_approval else None,
                "request_context": request_context,
                "response_format": response_format,
                "sections": sections,
            },
            "max_concurrency": 16,
        }

        # Stream graph execution
        final_content = ""
        for event in self._graph.stream({"messages": lc_messages}, config, stream_mode="updates"):
            yield from _convert_graph_event_to_stream(event)

            # Track last content for ANSWER_END
            for node_name, state_update in event.items():
                for msg in state_update.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and not getattr(msg, "tool_calls", None):
                        final_content = content

        # Build final messages for conversation_history
        all_messages = messages.copy()
        if system_prompt:
            all_messages.insert(0, {"role": "system", "content": system_prompt})

        yield StreamMessage(
            event=StreamEvents.ANSWER_END,
            data={
                "content": final_content,
                "messages": all_messages,
                "metadata": {},
            },
        )

    def process_tool_decisions(
        self,
        messages: List[Dict[str, Any]],
        tool_decisions: List[ToolApprovalDecision],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], list[StreamMessage]]:
        """Process tool approval decisions (matches ToolCallingLLM interface)."""
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
    """LangChain-based issue investigator. Replaces IssueInvestigator.

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
        """Investigate an issue (matches IssueInvestigator.investigate() interface)."""
        import textwrap

        from holmes.core.investigation_structured_output import (
            DEFAULT_SECTIONS,
            REQUEST_STRUCTURED_OUTPUT_FROM_LLM,
            get_output_format_for_investigation,
        )
        from holmes.core.prompt import generate_user_prompt
        from holmes.plugins.prompts import load_and_render_prompt
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
        messages = state_update.get("messages", [])
        for msg in messages:
            tool_calls = getattr(msg, "tool_calls", None)
            content = getattr(msg, "content", "")

            if hasattr(msg, "name") and hasattr(msg, "tool_call_id") and not tool_calls:
                # ToolMessage - emit tool result event
                yield StreamMessage(
                    event=StreamEvents.TOOL_RESULT,
                    data={
                        "tool_name": getattr(msg, "name", "") or "",
                        "tool_call_id": getattr(msg, "tool_call_id", ""),
                        "result": content[:500] if content else "",
                    },
                )
            elif tool_calls:
                # AIMessage with tool calls
                for tc in tool_calls:
                    yield StreamMessage(
                        event=StreamEvents.START_TOOL,
                        data={
                            "tool_name": tc.get("name", ""),
                            "id": tc.get("id", ""),
                        },
                    )
            elif content and isinstance(msg, type(msg)) and not hasattr(msg, "tool_call_id"):
                # AIMessage with text content (final answer)
                yield StreamMessage(
                    event=StreamEvents.AI_MESSAGE,
                    data={"message": content},
                )
