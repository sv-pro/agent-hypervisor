"""ProxyMCPServer – MCP server with deterministic execution control."""

from __future__ import annotations

import json
from typing import Any


class ProxyMCPServer:
    """MCP server backed by SafeMCPProxy.

    Example::

        server = ProxyMCPServer(world="email_safe")
        server.run()
    """

    def __init__(self, world: str = "email_safe") -> None:
        from safe_agent_runtime_core import SafeMCPProxy  # type: ignore[import]
        from safe_agent_runtime_pro.worlds import load_world

        config = load_world(world)
        self._proxy = SafeMCPProxy(**config.to_proxy_kwargs())

    def handle(self, tool_name: str, params: dict[str, Any], *, taint: bool = False) -> Any:
        """Route a tool call through the proxy."""
        return self._proxy.handle(tool_name, params, source="mcp", taint=taint)

    def run(self) -> None:
        """Start the MCP server (requires fastmcp)."""
        try:
            from fastmcp import FastMCP  # type: ignore[import]
        except ImportError:
            raise RuntimeError("fastmcp is required: pip install fastmcp")

        mcp = FastMCP("safe-mcp-gateway")
        proxy = self._proxy

        @mcp.tool(name="read_data", description="Read data from source")
        def read_data(**kwargs: Any) -> str:
            result = proxy.handle("read_data", kwargs, source="mcp", taint=False)
            return json.dumps(result, default=str)

        @mcp.tool(name="summarize", description="Summarize content")
        def summarize(**kwargs: Any) -> str:
            result = proxy.handle("summarize", kwargs, source="mcp", taint=False)
            return json.dumps(result, default=str)

        @mcp.tool(name="send_email", description="Send email to recipient")
        def send_email(**kwargs: Any) -> str:
            result = proxy.handle("send_email", kwargs, source="mcp", taint=False)
            return json.dumps(result, default=str)

        mcp.run()


def run_mcp_gateway(world: str = "email_safe") -> None:
    """Start the MCP gateway with the given world policy."""
    ProxyMCPServer(world=world).run()


__all__ = ["ProxyMCPServer", "run_mcp_gateway"]
