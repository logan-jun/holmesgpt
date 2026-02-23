"""LangGraph StateGraph definition for the Holmes ReAct agent.

Defines the graph structure:
  START → call_model → [route] → execute_tools → [route] → call_model (loop)
                          └─ force_continue ─┘      └─ END (approval_required)
                          └─ END (done / max_steps)
"""

import logging
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from holmes.core.langchain.nodes.model_node import call_model, call_model_force_continue
from holmes.core.langchain.nodes.tool_node import execute_tools
from holmes.core.langchain.state import HolmesAgentState

logger = logging.getLogger(__name__)


def route_after_model(state: HolmesAgentState, config: RunnableConfig) -> Literal["tools", "force_continue", "end"]:
    """Route after model response.

    Returns:
        "tools"          - Model requested tool calls
        "force_continue" - No tool calls, but TodoList has incomplete tasks
        "end"            - Final answer (or max_steps reached)
    """
    # Max steps check
    if state["step_count"] >= state["max_steps"]:
        logger.warning(f"Max steps reached: {state['step_count']}/{state['max_steps']}")
        return "end"

    # Check if model wants to call tools
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # TodoList enforcement: if tasks exist and not all completed, force continue
    todo_middleware = config.get("configurable", {}).get("todo_middleware")
    if todo_middleware and todo_middleware.should_force_continue():
        return "force_continue"

    return "end"


def route_after_tools(state: HolmesAgentState) -> Literal["continue", "approval_required"]:
    """Route after tool execution.

    Returns:
        "continue"          - Normal flow, go back to model
        "approval_required" - Tools need user approval, pause execution
    """
    if state.get("pending_approvals"):
        return "approval_required"
    return "continue"


def build_holmes_graph() -> StateGraph:
    """Build the Holmes ReAct agent graph.

    The graph implements a ReAct loop:
    1. call_model: Invoke LLM with tools
    2. route_after_model: Check if tools requested or done
    3. execute_tools: Run tools in parallel (ThreadPoolExecutor)
    4. route_after_tools: Check for approvals
    5. Loop back to call_model

    TodoListMiddleware enforces task completion via force_continue route.
    """
    graph = StateGraph(HolmesAgentState)

    # Nodes
    graph.add_node("call_model", call_model)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("force_continue", call_model_force_continue)

    # Entry edge
    graph.add_edge(START, "call_model")

    # After model: route to tools, force_continue, or end
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "tools": "execute_tools",
            "force_continue": "force_continue",
            "end": END,
        },
    )

    # After force_continue: always go back to model
    graph.add_edge("force_continue", "call_model")

    # After tools: continue loop or pause for approval
    graph.add_conditional_edges(
        "execute_tools",
        route_after_tools,
        {
            "continue": "call_model",
            "approval_required": END,
        },
    )

    return graph
