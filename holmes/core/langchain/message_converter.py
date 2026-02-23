"""Bidirectional message conversion between OpenAI format and LangChain BaseMessage."""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)


def openai_to_langchain(messages: List[Dict[str, Any]]) -> List[BaseMessage]:
    """Convert OpenAI-format message dicts to LangChain BaseMessage objects.

    Handles:
    - system, user, assistant, tool roles
    - AIMessage with tool_calls
    - Content as string or list (vision/cache_control format)
    """
    result: List[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                lc_tool_calls = _convert_openai_tool_calls(tool_calls)
                result.append(AIMessage(content=content, tool_calls=lc_tool_calls))
            else:
                result.append(AIMessage(content=content))
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                    name=msg.get("name", ""),
                )
            )
        else:
            logger.warning(f"Unknown message role: {role}, treating as human message")
            result.append(HumanMessage(content=content))

    return result


def langchain_to_openai(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Convert LangChain BaseMessage objects back to OpenAI-format dicts.

    This is needed for Holmes' context window limiter and LLMResult output.
    """
    result: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            entry: Dict[str, Any] = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = _convert_langchain_tool_calls(msg.tool_calls)
            result.append(entry)
        elif isinstance(msg, ToolMessage):
            result.append(
                {
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                    "name": msg.name or "",
                }
            )
        else:
            logger.warning(f"Unknown message type: {type(msg).__name__}")
            result.append({"role": "user", "content": str(msg.content)})

    return result


def _convert_openai_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI-format tool_calls to LangChain format.

    OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
    LangChain format: {"name": "...", "args": {...}, "id": "...", "type": "tool_call"}
    """
    lc_calls = []
    for tc in tool_calls:
        func = tc.get("function", {})
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}
        lc_calls.append(
            {
                "name": func.get("name", ""),
                "args": args,
                "id": tc.get("id", ""),
                "type": "tool_call",
            }
        )
    return lc_calls


def _convert_langchain_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert LangChain-format tool_calls back to OpenAI format."""
    openai_calls = []
    for tc in tool_calls:
        args = tc.get("args", {})
        openai_calls.append(
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": json.dumps(args) if isinstance(args, dict) else str(args),
                },
            }
        )
    return openai_calls
