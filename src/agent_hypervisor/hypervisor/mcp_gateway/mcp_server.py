"""
mcp_server.py — Agent Hypervisor MCP Gateway.

Implements a JSON-RPC 2.0 server that speaks the Model Context Protocol.

Endpoints:
  POST /mcp          — JSON-RPC 2.0 dispatcher (tools/list, tools/call, initialize)
  GET  /mcp/health   — health check + world summary
  POST /mcp/reload   — hot-reload manifest from disk

MCP methods handled:
  initialize         — MCP handshake (returns server capabilities)
  tools/list         — returns only manifest-declared tools (world rendering)
  tools/call         — deterministic enforcement, then adapter dispatch

Request flow:
  Client → POST /mcp → dispatch_jsonrpc()
    ├── method=tools/list
    │     → SessionWorldResolver.resolve()
    │     → ToolSurfaceRenderer.render()
    │     → [MCPTool, ...]  (only manifest-visible tools)
    │
    └── method=tools/call
          → SessionWorldResolver.resolve()
          → ToolCallEnforcer.enforce()  (manifest check → policy → allow/deny)
          → ToolRegistry.get_tool().adapter(args)  (only on allow)
          → MCPToolResult

Usage::

    from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import create_mcp_app
    import uvicorn
    uvicorn.run(
        create_mcp_app("manifests/example_world.yaml"),
        host="127.0.0.1",
        port=8090,
    )
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..gateway.tool_registry import ToolRegistry, build_default_registry
from .protocol import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    MCP_MANIFEST_ERROR,
    MCP_TOOL_DENIED,
    MCP_TOOL_NOT_FOUND,
    JSONRPCRequest,
    MCPContent,
    MCPToolResult,
    make_error,
    make_result,
)
from .session_world_resolver import SessionWorldResolver
from .tool_call_enforcer import InvocationProvenance, ToolCallEnforcer
from .tool_surface_renderer import ToolSurfaceRenderer


# ---------------------------------------------------------------------------
# Gateway state
# ---------------------------------------------------------------------------

class MCPGatewayState:
    """
    Immutable-after-init gateway state.

    Holds the three core components:
      - SessionWorldResolver  — manifest binding
      - ToolSurfaceRenderer   — tools/list rendering
      - ToolCallEnforcer      — tools/call enforcement
      - ToolRegistry          — adapter dispatch

    ToolSurfaceRenderer and ToolCallEnforcer are rebuilt on manifest reload.
    """

    def __init__(
        self,
        manifest_path: Path,
        registry: Optional[ToolRegistry] = None,
        policy_engine: Optional[Any] = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.registry = registry or build_default_registry()
        self.policy_engine = policy_engine

        self.resolver = SessionWorldResolver(self.manifest_path)
        self._rebuild_components()

        self.started_at = datetime.now(timezone.utc).isoformat()

    def _rebuild_components(self) -> None:
        """Rebuild renderer and enforcer from the current manifest."""
        manifest = self.resolver.manifest
        self.renderer = ToolSurfaceRenderer(manifest, self.registry)
        self.enforcer = ToolCallEnforcer(manifest, self.registry, self.policy_engine)

    def reload_manifest(self) -> bool:
        """
        Hot-reload the manifest from disk and rebuild components.

        Returns True if reload succeeded, False otherwise.
        On failure, existing manifest/components are retained.
        """
        ok = self.resolver.reload()
        if ok:
            self._rebuild_components()
        return ok


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_mcp_app(
    manifest_path: str | Path = "manifests/example_world.yaml",
    registry: Optional[ToolRegistry] = None,
    policy_engine: Optional[Any] = None,
) -> FastAPI:
    """
    Build and return the FastAPI MCP gateway application.

    Args:
        manifest_path: Path to the WorldManifest YAML file.
                       Gateway will not start if this file cannot be loaded.
        registry:      ToolRegistry to use. Defaults to build_default_registry().
        policy_engine: Optional PolicyEngine for secondary enforcement.
                       If None, only manifest + constraint checks run.

    Returns:
        FastAPI app ready to serve with uvicorn.

    Raises:
        FileNotFoundError: If manifest_path does not exist.
        jsonschema.ValidationError: If the manifest YAML is invalid.
    """
    manifest_path = Path(manifest_path)
    state = MCPGatewayState(
        manifest_path=manifest_path,
        registry=registry,
        policy_engine=policy_engine,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.gw = state
        yield

    app = FastAPI(
        title="Agent Hypervisor — MCP Gateway",
        description=(
            "Manifest-driven MCP gateway. "
            "tools/list returns only world-manifest-declared tools. "
            "tools/call is deterministically enforced against the manifest. "
            "Undeclared tools are absent, not merely forbidden."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    # Attach state early for sync test access
    app.state.gw = state

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 dispatcher
    # ------------------------------------------------------------------

    @app.post("/mcp")
    async def dispatch_jsonrpc(request: Request) -> JSONResponse:
        """
        Main JSON-RPC 2.0 dispatcher.

        Parses the request body as a JSON-RPC 2.0 request and dispatches
        to the appropriate handler. Returns a JSON-RPC 2.0 response.
        """
        gw: MCPGatewayState = app.state.gw

        # Parse body
        try:
            body = await request.json()
        except Exception:
            resp = make_error(None, JSONRPC_PARSE_ERROR, "Parse error: body is not valid JSON")
            return JSONResponse(content=resp.model_dump(exclude_none=True), status_code=400)

        # Validate JSON-RPC envelope
        try:
            rpc = JSONRPCRequest.model_validate(body)
        except Exception as exc:
            resp = make_error(
                body.get("id") if isinstance(body, dict) else None,
                JSONRPC_PARSE_ERROR,
                f"Invalid JSON-RPC request: {exc}",
            )
            return JSONResponse(content=resp.model_dump(exclude_none=True), status_code=400)

        # Extract provenance metadata from request headers / params
        provenance = _extract_provenance(request, rpc)

        # Dispatch
        try:
            if rpc.method == "initialize":
                result = _handle_initialize(gw, rpc.params or {})
                resp = make_result(rpc.id, result)

            elif rpc.method == "tools/list":
                result = _handle_tools_list(gw, rpc.params or {}, provenance)
                resp = make_result(rpc.id, result)

            elif rpc.method == "tools/call":
                resp = _handle_tools_call(gw, rpc.id, rpc.params or {}, provenance)

            else:
                resp = make_error(
                    rpc.id,
                    JSONRPC_METHOD_NOT_FOUND,
                    f"Method not found: {rpc.method!r}",
                )
        except Exception as exc:
            resp = make_error(rpc.id, JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}")

        return JSONResponse(content=resp.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/mcp/health")
    async def health() -> JSONResponse:
        """Gateway health check and world summary."""
        gw: MCPGatewayState = app.state.gw
        manifest = gw.resolver.manifest
        visible_tools = [t.name for t in gw.renderer.render()]
        return JSONResponse({
            "status": "running",
            "started_at": gw.started_at,
            "manifest": {
                "path": str(gw.manifest_path),
                "workflow_id": manifest.workflow_id if manifest else None,
                "version": manifest.version if manifest else None,
                "declared_capabilities": [c.tool for c in manifest.capabilities] if manifest else [],
            },
            "visible_tools": visible_tools,
        })

    # ------------------------------------------------------------------
    # Manifest hot-reload
    # ------------------------------------------------------------------

    @app.post("/mcp/reload")
    async def reload_manifest() -> JSONResponse:
        """Hot-reload the WorldManifest from disk."""
        gw: MCPGatewayState = app.state.gw
        ok = gw.reload_manifest()
        manifest = gw.resolver.manifest
        return JSONResponse({
            "status": "reloaded" if ok else "failed",
            "manifest_path": str(gw.manifest_path),
            "workflow_id": manifest.workflow_id if manifest else None,
            "visible_tools": [t.name for t in gw.renderer.render()] if ok else [],
        })

    return app


# ---------------------------------------------------------------------------
# Method handlers (pure functions — no side effects on state)
# ---------------------------------------------------------------------------

def _handle_initialize(state: MCPGatewayState, params: dict) -> dict:
    """
    Handle MCP initialize handshake.

    Returns server capabilities. The MCP client sends this first and uses
    the capabilities to know what the server supports.
    """
    manifest = state.resolver.manifest
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "agent-hypervisor-mcp-gateway",
            "version": "0.2.0",
        },
        "instructions": (
            f"World manifest: {manifest.workflow_id!r} (v{manifest.version}). "
            f"Only {len(manifest.capabilities)} tool(s) exist in this world."
        ),
    }


def _handle_tools_list(
    state: MCPGatewayState,
    params: dict,
    provenance: InvocationProvenance,
) -> dict:
    """
    Handle tools/list.

    Returns only the tools visible in the current manifest world.
    The MCP client will see only these tools — undeclared tools do not exist.
    """
    tools = state.renderer.render()
    return {
        "tools": [t.model_dump() for t in tools],
    }


def _handle_tools_call(
    state: MCPGatewayState,
    request_id: Any,
    params: dict,
    provenance: InvocationProvenance,
) -> Any:
    """
    Handle tools/call.

    Enforces the call against the manifest. On denial, returns a JSON-RPC
    error response (the tool is absent or forbidden). On allow, dispatches
    to the registered adapter and returns the result.
    """
    # Validate params
    tool_name = params.get("name")
    if not tool_name:
        return make_error(
            request_id,
            JSONRPC_INVALID_PARAMS,
            "tools/call requires 'name' parameter",
        )
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return make_error(
            request_id,
            JSONRPC_INVALID_PARAMS,
            "'arguments' must be an object",
        )

    # Enforce
    decision = state.enforcer.enforce(tool_name, arguments, provenance)

    if decision.denied:
        # Choose error code: not-in-world vs. policy-denied
        if "not_declared" in decision.matched_rule or "no_adapter" in decision.matched_rule:
            code = MCP_TOOL_NOT_FOUND
            message = f"Tool not found: {tool_name!r}"
        else:
            code = MCP_TOOL_DENIED
            message = f"Tool call denied: {decision.reason}"
        return make_error(
            request_id,
            code,
            message,
            data={"reason": decision.reason, "rule": decision.matched_rule},
        )

    # Dispatch to adapter
    tool_def = state.registry.get_tool(tool_name)
    try:
        raw_result = tool_def.adapter(arguments)
    except Exception as exc:
        # Adapter error — protocol-level success, tool-level error
        result_obj = MCPToolResult(
            content=[MCPContent(type="text", text=f"Tool error: {exc}")],
            isError=True,
        )
        return make_result(request_id, result_obj.model_dump())

    # Format result
    if isinstance(raw_result, str):
        text = raw_result
    else:
        text = json.dumps(raw_result, default=str)

    result_obj = MCPToolResult(
        content=[MCPContent(type="text", text=text)],
        isError=False,
    )
    return make_result(request_id, result_obj.model_dump())


# ---------------------------------------------------------------------------
# Provenance extraction
# ---------------------------------------------------------------------------

def _extract_provenance(request: Request, rpc: JSONRPCRequest) -> InvocationProvenance:
    """
    Extract provenance metadata from request headers and RPC params.

    This is the Phase 5 provenance hook. It captures source metadata
    without modifying enforcement logic. Future phases can use this
    metadata for taint-aware enforcement.
    """
    headers = dict(request.headers)
    params = rpc.params or {}
    meta = params.get("_meta", {}) or {}

    session_id = (
        meta.get("session_id")
        or headers.get("x-mcp-session-id")
        or headers.get("x-session-id")
        or ""
    )
    source = (
        meta.get("source")
        or headers.get("x-mcp-client")
        or "mcp_client"
    )
    trust_level = meta.get("trust_level", "untrusted")

    return InvocationProvenance(
        source=source,
        session_id=session_id,
        trust_level=trust_level,
        timestamp=datetime.now(timezone.utc).isoformat(),
        extra={k: v for k, v in meta.items()
               if k not in ("session_id", "source", "trust_level")},
    )
