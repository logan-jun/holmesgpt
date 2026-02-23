"""MCP adapter using langchain-mcp-adapters.

Bridges Holmes' MCP server configuration into langchain-mcp-adapters'
MultiServerMCPClient for standardized MCP tool integration.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HolmesMCPManager:
    """Manages MCP servers via langchain-mcp-adapters.

    Converts Holmes-style MCP config into langchain-mcp-adapters format
    and provides tools as LangChain-compatible objects.
    """

    def __init__(self, mcp_configs: Dict[str, Dict[str, Any]]):
        self.server_configs = self._build_server_configs(mcp_configs)

    def _build_server_configs(self, mcp_configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Convert Holmes MCP config to langchain-mcp-adapters format.

        Holmes format:
            {"server_name": {"url": "...", "mode": "sse|streamable_http|stdio", ...}}

        langchain-mcp-adapters format:
            {"server_name": {"transport": "sse|http|stdio", "url": "...", ...}}
        """
        servers: Dict[str, Dict[str, Any]] = {}

        for name, config in mcp_configs.items():
            mode = config.get("mode", "sse")

            if mode == "stdio":
                servers[name] = {
                    "transport": "stdio",
                    "command": config["command"],
                    "args": config.get("args", []),
                }
                if config.get("env"):
                    servers[name]["env"] = config["env"]
            elif mode == "streamable_http":
                servers[name] = {
                    "transport": "streamable_http",
                    "url": str(config["url"]),
                }
                if config.get("headers"):
                    servers[name]["headers"] = config["headers"]
            else:
                # Default: SSE
                servers[name] = {
                    "transport": "sse",
                    "url": str(config["url"]),
                }
                if config.get("headers"):
                    servers[name]["headers"] = config["headers"]

        return servers

    async def _get_tools_async(self) -> list:
        """Async method to get tools from all MCP servers."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            logger.warning(
                "langchain-mcp-adapters not installed. "
                "Install with: pip install langchain-mcp-adapters"
            )
            return []

        async with MultiServerMCPClient(self.server_configs) as client:
            return client.get_tools()

    def get_tools(self) -> list:
        """Get LangChain-compatible tools from all configured MCP servers.

        Returns empty list if langchain-mcp-adapters is not installed.
        """
        if not self.server_configs:
            return []

        try:
            return asyncio.run(self._get_tools_async())
        except Exception as e:
            logger.error(f"Failed to get MCP tools: {e}")
            return []
