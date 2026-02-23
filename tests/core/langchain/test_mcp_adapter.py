"""Tests for HolmesMCPManager."""

import pytest

from holmes.core.langchain.mcp_adapter import HolmesMCPManager


class TestHolmesMCPManager:
    def test_empty_config(self):
        mgr = HolmesMCPManager({})
        assert mgr.server_configs == {}

    def test_sse_config(self):
        config = {
            "my_server": {
                "url": "http://localhost:8080/sse",
                "mode": "sse",
            }
        }
        mgr = HolmesMCPManager(config)
        assert "my_server" in mgr.server_configs
        assert mgr.server_configs["my_server"]["transport"] == "sse"
        assert mgr.server_configs["my_server"]["url"] == "http://localhost:8080/sse"

    def test_streamable_http_config(self):
        config = {
            "http_server": {
                "url": "http://localhost:9090/mcp",
                "mode": "streamable_http",
                "headers": {"Authorization": "Bearer token"},
            }
        }
        mgr = HolmesMCPManager(config)
        assert mgr.server_configs["http_server"]["transport"] == "streamable_http"
        assert mgr.server_configs["http_server"]["headers"]["Authorization"] == "Bearer token"

    def test_stdio_config(self):
        config = {
            "local_server": {
                "mode": "stdio",
                "command": "python",
                "args": ["-m", "my_mcp_server"],
                "env": {"DEBUG": "true"},
            }
        }
        mgr = HolmesMCPManager(config)
        assert mgr.server_configs["local_server"]["transport"] == "stdio"
        assert mgr.server_configs["local_server"]["command"] == "python"
        assert mgr.server_configs["local_server"]["args"] == ["-m", "my_mcp_server"]
        assert mgr.server_configs["local_server"]["env"] == {"DEBUG": "true"}

    def test_default_mode_is_sse(self):
        config = {
            "server": {
                "url": "http://localhost:8080/sse",
            }
        }
        mgr = HolmesMCPManager(config)
        assert mgr.server_configs["server"]["transport"] == "sse"

    def test_multiple_servers(self):
        config = {
            "server_a": {"url": "http://a:8080", "mode": "sse"},
            "server_b": {"mode": "stdio", "command": "node", "args": ["server.js"]},
        }
        mgr = HolmesMCPManager(config)
        assert len(mgr.server_configs) == 2
        assert "server_a" in mgr.server_configs
        assert "server_b" in mgr.server_configs

    def test_get_tools_empty_config(self):
        mgr = HolmesMCPManager({})
        tools = mgr.get_tools()
        assert tools == []
