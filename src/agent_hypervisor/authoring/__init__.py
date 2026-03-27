"""Safe MCP Gateway – secure MCP server for LLM tool execution."""

from safe_agent_runtime_pro.integrations.mcp.server import ProxyMCPServer, run_mcp_gateway

__version__ = "0.1.0"

__all__ = ["ProxyMCPServer", "run_mcp_gateway"]
