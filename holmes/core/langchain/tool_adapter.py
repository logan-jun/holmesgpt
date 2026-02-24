"""Adapter to convert Holmes tools into LangChain StructuredTool placeholders.

These placeholder tools provide schema definitions (name, description, args_schema)
for create_agent()'s tool binding. Actual execution is bypassed in wrap_tool_call
which invokes Holmes ToolExecutor directly.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from holmes.core.tools_utils.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


def create_langchain_tools(
    tool_executor: ToolExecutor,
    target_model: str,
    include_restricted: bool = False,
) -> List[StructuredTool]:
    """Convert Holmes ToolExecutor's OpenAI-format tools to LangChain StructuredTools.

    Each tool has name, description, and args_schema for LLM tool binding.
    Actual execution is handled by HolmesToolExecutionMiddleware.wrap_tool_call.
    """
    openai_tools = tool_executor.get_all_tools_openai_format(
        target_model=target_model,
        include_restricted=include_restricted,
    )

    langchain_tools = []
    for tool_def in openai_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        description = func_def.get("description", "")
        parameters = func_def.get("parameters", {})

        args_schema = _json_schema_to_pydantic(name, parameters)

        langchain_tools.append(
            StructuredTool(
                name=name,
                description=description,
                args_schema=args_schema,
                func=_placeholder_func,
            )
        )

    logger.debug(f"Created {len(langchain_tools)} LangChain tool placeholders")
    return langchain_tools


def _placeholder_func(**kwargs: Any) -> str:
    """Placeholder function - actual execution happens in wrap_tool_call."""
    return "This tool is executed via HolmesToolExecutionMiddleware.wrap_tool_call"


def _json_schema_to_pydantic(tool_name: str, schema: Dict[str, Any]) -> type[BaseModel]:
    """Convert a JSON Schema (OpenAI function parameters) to a Pydantic model.

    Handles the common OpenAI tool parameter format:
    {"type": "object", "properties": {...}, "required": [...]}
    """
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    field_definitions: Dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        field_type = _json_type_to_python(field_schema)
        is_required = field_name in required_fields

        if is_required:
            field_definitions[field_name] = (field_type, ...)
        else:
            field_definitions[field_name] = (Optional[field_type], None)

    model_name = f"{_sanitize_name(tool_name)}Args"
    return create_model(model_name, **field_definitions)


def _json_type_to_python(field_schema: Dict[str, Any]) -> type:
    """Map JSON Schema type to Python type."""
    json_type = field_schema.get("type", "string")

    if json_type == "string":
        return str
    elif json_type == "integer":
        return int
    elif json_type == "number":
        return float
    elif json_type == "boolean":
        return bool
    elif json_type == "array":
        return list
    elif json_type == "object":
        return dict
    else:
        return str


def _sanitize_name(name: str) -> str:
    """Sanitize tool name for use as a Pydantic model name."""
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")
