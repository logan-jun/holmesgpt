"""LangGraph state definition for the Holmes ReAct agent."""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class HolmesAgentState(TypedDict):
    """State schema for the Holmes LangGraph agent.

    This tracks everything the agent needs across iterations:
    messages, tool history, costs, and control flow state.
    """

    # Conversation history (LangChain messages with automatic appending)
    messages: Annotated[list[BaseMessage], add_messages]

    # Tool tracking
    tool_calls_history: list[dict]  # For repeated-call safeguard
    all_tool_call_results: list[dict]  # Accumulated for LLMResult.tool_calls
    tool_number_offset: int  # Sequential numbering across iterations

    # Loop control
    step_count: int
    max_steps: int

    # Cost tracking
    total_cost: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # Feature flags
    runbook_in_use: bool  # Enables restricted tools after fetch_runbook

    # TodoList state (managed by TodoListMiddleware)
    tasks: list[dict]

    # Approval flow
    pending_approvals: list[dict]

    # Metadata passthrough
    metadata: dict
