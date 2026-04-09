"""
protocol.py — MCP JSON-RPC 2.0 wire types.

Defines the data models for:
  - JSON-RPC 2.0 request/response envelope
  - MCP tool descriptor (tools/list shape)
  - MCP tool call parameters (tools/call shape)
  - MCP tool result (tools/call response shape)

Standard error codes follow JSON-RPC 2.0 spec.
MCP-specific error codes are defined as constants below.

Reference: https://spec.modelcontextprotocol.io/
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 standard error codes
# ---------------------------------------------------------------------------

JSONRPC_PARSE_ERROR      = -32700
JSONRPC_INVALID_REQUEST  = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS   = -32602
JSONRPC_INTERNAL_ERROR   = -32603

# MCP-specific application error codes (in the -32000 to -32099 range)
MCP_TOOL_NOT_FOUND       = -32001   # tool not in manifest world
MCP_TOOL_DENIED          = -32002   # tool exists but call was denied by policy
MCP_MANIFEST_ERROR       = -32003   # manifest could not be loaded or is invalid


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JSONRPCRequest(BaseModel):
    """Incoming JSON-RPC 2.0 request from an MCP client."""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[dict[str, Any]] = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error object embedded in an error response."""
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    """Outgoing JSON-RPC 2.0 response (result XOR error)."""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# MCP tool descriptor (tools/list)
# ---------------------------------------------------------------------------

class MCPTool(BaseModel):
    """
    One tool as returned by tools/list.

    inputSchema follows JSON Schema (object with properties).
    Only tools that appear in the active WorldManifest are returned.
    """
    name: str
    description: str
    inputSchema: dict[str, Any] = {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# MCP tool call (tools/call params)
# ---------------------------------------------------------------------------

class MCPToolCallParams(BaseModel):
    """
    Parameters for a tools/call JSON-RPC request.

    name:       tool name (must exist in manifest world or call fails closed)
    arguments:  raw argument dict passed to the tool adapter
    _meta:      optional metadata (session_id, source, etc.)
    """
    name: str
    arguments: dict[str, Any] = {}
    _meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# MCP tool result (tools/call response)
# ---------------------------------------------------------------------------

class MCPContent(BaseModel):
    """One content block in a tool result."""
    type: str = "text"
    text: str


class MCPToolResult(BaseModel):
    """
    Tool call result as returned by tools/call.

    content:  list of content blocks (text, image, etc.)
    isError:  True when the call succeeded at the protocol level but
              the tool itself reported a failure (adapter-level error).
              Distinct from a JSON-RPC error response (which indicates
              the call was blocked before reaching the adapter).
    """
    content: list[MCPContent]
    isError: bool = False


# ---------------------------------------------------------------------------
# Helper constructors
# ---------------------------------------------------------------------------

def make_result(request_id: Optional[Union[str, int]], result: Any) -> JSONRPCResponse:
    """Build a successful JSON-RPC 2.0 response."""
    return JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)


def make_error(
    request_id: Optional[Union[str, int]],
    code: int,
    message: str,
    data: Any = None,
) -> JSONRPCResponse:
    """Build a JSON-RPC 2.0 error response."""
    return JSONRPCResponse(
        jsonrpc="2.0",
        id=request_id,
        error=JSONRPCError(code=code, message=message, data=data),
    )
