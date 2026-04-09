"""
mcp_gateway — Agent Hypervisor MCP Gateway.

Public API:
    create_mcp_app()           — build FastAPI app for the MCP gateway
    ToolSurfaceRenderer        — manifest-driven tool surface rendering
    ToolCallEnforcer           — deterministic tool call enforcement
    SessionWorldResolver       — session → WorldManifest binding
    EnforcementDecision        — result of enforcing a tool call
    InvocationProvenance       — provenance metadata for a tool invocation

Usage::

    from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
    import uvicorn
    uvicorn.run(create_mcp_app("manifests/my_world.yaml"), host="0.0.0.0", port=8090)
"""

from .mcp_server import create_mcp_app, MCPGatewayState
from .tool_surface_renderer import ToolSurfaceRenderer
from .tool_call_enforcer import ToolCallEnforcer, EnforcementDecision, InvocationProvenance
from .session_world_resolver import SessionWorldResolver
from .protocol import MCPTool, MCPToolResult, JSONRPCRequest, JSONRPCResponse

__all__ = [
    "create_mcp_app",
    "MCPGatewayState",
    "ToolSurfaceRenderer",
    "ToolCallEnforcer",
    "EnforcementDecision",
    "InvocationProvenance",
    "SessionWorldResolver",
    "MCPTool",
    "MCPToolResult",
    "JSONRPCRequest",
    "JSONRPCResponse",
]
