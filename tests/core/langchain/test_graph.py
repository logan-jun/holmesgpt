"""Tests for LangGraph graph structure and routing."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from holmes.core.langchain.graph import build_holmes_graph, route_after_model, route_after_tools
from holmes.core.langchain.state import HolmesAgentState
from holmes.core.langchain.todo_middleware import TodoListMiddleware


def _make_state(**overrides) -> HolmesAgentState:
    """Create a minimal valid state dict with overrides."""
    base: HolmesAgentState = {
        "messages": [HumanMessage(content="test")],
        "tool_calls_history": [],
        "all_tool_call_results": [],
        "tool_number_offset": 0,
        "step_count": 0,
        "max_steps": 10,
        "total_cost": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "runbook_in_use": False,
        "tasks": [],
        "pending_approvals": [],
        "metadata": {},
    }
    base.update(overrides)
    return base


def _make_config(**configurable_overrides) -> RunnableConfig:
    return {"configurable": configurable_overrides}


class TestRouteAfterModel:
    def test_routes_to_end_at_max_steps(self):
        state = _make_state(step_count=10, max_steps=10, messages=[AIMessage(content="done")])
        result = route_after_model(state, _make_config())
        assert result == "end"

    def test_routes_to_tools_when_tool_calls(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_pods", "args": {}, "id": "tc1"}],
        )
        state = _make_state(messages=[ai_msg])
        result = route_after_model(state, _make_config())
        assert result == "tools"

    def test_routes_to_end_no_tools_no_tasks(self):
        state = _make_state(messages=[AIMessage(content="Final answer")])
        result = route_after_model(state, _make_config())
        assert result == "end"

    def test_routes_to_force_continue_with_incomplete_tasks(self):
        mw = TodoListMiddleware()
        mw.update_tasks([{"id": "1", "content": "Task", "status": "pending"}])
        state = _make_state(messages=[AIMessage(content="answer")])
        config = _make_config(todo_middleware=mw)
        result = route_after_model(state, config)
        assert result == "force_continue"

    def test_routes_to_end_with_completed_tasks(self):
        mw = TodoListMiddleware()
        mw.update_tasks([{"id": "1", "content": "Task", "status": "completed"}])
        state = _make_state(messages=[AIMessage(content="answer")])
        config = _make_config(todo_middleware=mw)
        result = route_after_model(state, config)
        assert result == "end"


class TestRouteAfterTools:
    def test_continue_no_approvals(self):
        state = _make_state(pending_approvals=[])
        assert route_after_tools(state) == "continue"

    def test_approval_required(self):
        state = _make_state(
            pending_approvals=[{"tool_call_id": "tc1", "tool_name": "bash"}]
        )
        assert route_after_tools(state) == "approval_required"


class TestGraphBuild:
    def test_graph_structure(self):
        graph = build_holmes_graph()
        assert "call_model" in graph.nodes
        assert "execute_tools" in graph.nodes
        assert "force_continue" in graph.nodes

    def test_graph_compiles(self):
        graph = build_holmes_graph()
        compiled = graph.compile()
        assert compiled is not None
