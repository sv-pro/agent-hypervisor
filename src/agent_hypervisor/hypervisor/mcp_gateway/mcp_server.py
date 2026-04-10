"""
mcp_server.py — Agent Hypervisor MCP Gateway.

Implements a JSON-RPC 2.0 server that speaks the Model Context Protocol.

Endpoints:
  POST /mcp                            — JSON-RPC 2.0 dispatcher (HTTP transport)
  GET  /mcp/sse                        — MCP SSE transport: opens stream, sends endpoint event
  POST /mcp/messages                   — MCP SSE transport: receives requests, routes over SSE
  GET  /mcp/health                     — health check + world summary
  POST /mcp/reload                     — hot-reload default manifest from disk
  POST /mcp/sessions/{session_id}/bind — bind a session to a specific manifest
  DELETE /mcp/sessions/{session_id}    — unbind a session (revert to default)
  GET  /mcp/sessions                   — list all active session bindings

MCP methods handled:
  initialize         — MCP handshake (returns server capabilities)
  tools/list         — returns only manifest-declared tools (world rendering)
  tools/call         — deterministic enforcement, then adapter dispatch

HTTP transport (POST /mcp):
  Client → POST /mcp → dispatch_jsonrpc() → JSONResponse

SSE transport (GET /mcp/sse + POST /mcp/messages):
  Client → GET /mcp/sse   → server sends endpoint event: "/mcp/messages?session_id=<uuid>"
        → POST /mcp/messages?session_id=<uuid>  → server returns 202, pushes response to SSE stream
        → SSE stream delivers "message" event with the JSON-RPC response

Per-session manifests:
  Sessions without an explicit binding use the gateway-level default manifest.
  Bind a session via POST /mcp/sessions/{session_id}/bind with a manifest_path
  in the request body. Different agents/users can operate in different worlds
  simultaneously without gateway restart.

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

# Path to the bundled default provenance firewall policy.
# Resolved relative to this file so it works both in-tree and when installed.
_DEFAULT_POLICY_PATH: Path = (
    Path(__file__).parent.parent.parent / "runtime" / "configs" / "default_policy.yaml"
)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from agent_hypervisor.runtime.taint import TaintedValue
from agent_hypervisor.compiler.schema import manifest_from_dict
from agent_hypervisor.control_plane.api import ControlPlaneState
from agent_hypervisor.control_plane.world_state_resolver import world_state_to_manifest_dict
from .sse_transport import SSESessionStore, sse_stream


class _BindSessionRequest(BaseModel):
    manifest_path: str

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
        control_plane: Optional[ControlPlaneState] = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.registry = registry or build_default_registry()
        self.policy_engine = policy_engine
        self.control_plane = control_plane

        self.resolver = SessionWorldResolver(self.manifest_path)
        self._rebuild_components()

        self.started_at = datetime.now(timezone.utc).isoformat()

    def _rebuild_components(self) -> None:
        """Rebuild default renderer and enforcer from the gateway-level manifest."""
        manifest = self.resolver.manifest
        self.renderer = ToolSurfaceRenderer(manifest, self.registry)
        self.enforcer = ToolCallEnforcer(manifest, self.registry, self.policy_engine)

    def renderer_for(self, manifest) -> "ToolSurfaceRenderer":
        """
        Return a ToolSurfaceRenderer for the given manifest.

        If manifest is the gateway-level default, returns the cached renderer.
        Otherwise builds a new one (lightweight).
        """
        if manifest is self.resolver.manifest:
            return self.renderer
        return ToolSurfaceRenderer(manifest, self.registry)

    def enforcer_for(self, manifest) -> "ToolCallEnforcer":
        """
        Return a ToolCallEnforcer for the given manifest.

        If manifest is the gateway-level default, returns the cached enforcer.
        Otherwise builds a new one (lightweight).
        """
        if manifest is self.resolver.manifest:
            return self.enforcer
        return ToolCallEnforcer(manifest, self.registry, self.policy_engine)

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
    use_default_policy: bool = False,
    control_plane: Optional[ControlPlaneState] = None,
) -> FastAPI:
    """
    Build and return the FastAPI MCP gateway application.

    Args:
        manifest_path:       Path to the WorldManifest YAML file.
                             Gateway will not start if this file cannot be loaded.
        registry:            ToolRegistry to use. Defaults to build_default_registry().
        policy_engine:       Optional PolicyEngine for secondary enforcement.
                             If None and use_default_policy is False, only manifest +
                             constraint checks run.
        use_default_policy:  If True and policy_engine is None, auto-load the bundled
                             default provenance firewall policy from
                             runtime/configs/default_policy.yaml. This enables
                             provenance-aware enforcement (external_document arguments
                             to side-effect tools are denied; read-only tools are
                             always allowed).
        control_plane:       Optional ControlPlaneState. When provided:
                             - The control plane router is mounted at /control/*.
                             - tools/call "ask" verdicts create approval requests
                               instead of failing closed.
                             - tools/list reflects active session overlays.
                             - New SSE sessions are auto-registered in the session store.

    Returns:
        FastAPI app ready to serve with uvicorn.

    Raises:
        FileNotFoundError: If manifest_path does not exist.
        jsonschema.ValidationError: If the manifest YAML is invalid.
    """
    manifest_path = Path(manifest_path)

    # Auto-load default policy engine when requested and none was provided.
    if use_default_policy and policy_engine is None:
        from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
        policy_engine = PolicyEngine.from_yaml(_DEFAULT_POLICY_PATH)

    # Wire the control plane manifest bridge (lazy — resolved per request).
    if control_plane is not None and control_plane.get_base_manifest is None:
        # Auto-configure the bridge so the control plane can resolve world state
        # from the gateway's manifest layer. The lambda captures `state` after it
        # is constructed below via a mutable cell to avoid forward-reference issues.
        _state_cell: list = []

        def _gateway_manifest_bridge(session_id: str):
            gw = _state_cell[0]
            manifest = gw.resolver.resolve(session_id)
            base_tools = manifest.tool_names()
            base_constraints = {
                c.tool: c.constraints
                for c in manifest.capabilities
                if c.constraints
            }
            return base_tools, base_constraints

        control_plane.get_base_manifest = _gateway_manifest_bridge
    else:
        _state_cell = []

    state = MCPGatewayState(
        manifest_path=manifest_path,
        registry=registry,
        policy_engine=policy_engine,
        control_plane=control_plane,
    )
    _state_cell.append(state)  # wire bridge to real state

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
    sse_store = SSESessionStore()
    app.state.sse_store = sse_store

    # Mount control plane router when a ControlPlaneState is provided
    if control_plane is not None:
        from agent_hypervisor.control_plane.api import create_control_plane_router
        app.state.control_plane = control_plane
        app.include_router(create_control_plane_router(control_plane))

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 dispatcher
    # ------------------------------------------------------------------

    @app.post("/mcp")
    async def dispatch_jsonrpc(request: Request) -> JSONResponse:
        """
        Main JSON-RPC 2.0 dispatcher (HTTP transport).

        Parses the request body as a JSON-RPC 2.0 request and dispatches
        to the appropriate handler. Returns a JSON-RPC 2.0 response.
        """
        gw: MCPGatewayState = app.state.gw
        resp = await _dispatch_rpc_body(gw, request)
        # Return 400 only for transport-level parse failures; all JSON-RPC
        # application errors (tool denied, method not found, etc.) are HTTP 200.
        is_parse_error = (
            resp.error is not None
            and resp.error.code == JSONRPC_PARSE_ERROR
        )
        return JSONResponse(
            content=resp.model_dump(exclude_none=True),
            status_code=400 if is_parse_error else 200,
        )

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
    # SSE transport  (GET /mcp/sse  +  POST /mcp/messages)
    # ------------------------------------------------------------------

    @app.get("/mcp/sse")
    async def sse_endpoint(request: Request) -> StreamingResponse:
        """
        MCP SSE transport — open a streaming connection.

        Protocol (MCP 2024-11-05 SSE transport):
          1. Server assigns a session UUID and returns a StreamingResponse
             with Content-Type: text/event-stream.
          2. The first event is 'endpoint'; its data is the URL the client
             must use to POST JSON-RPC requests, e.g.:
               /mcp/messages?session_id=<uuid>
          3. Subsequent 'message' events carry JSON-RPC responses.
          4. A keep-alive comment is sent every ~25 s to prevent proxy
             timeouts.

        The session UUID is distinct from a manifest-binding session. The
        client may pass it as X-MCP-Session-Id in POST /mcp/messages headers
        to also carry provenance through the manifest-binding layer.
        """
        store: SSESessionStore = app.state.sse_store
        session_id, queue = store.create_session()
        endpoint_url = f"/mcp/messages?session_id={session_id}"

        # Auto-register new SSE session with the control plane (if wired)
        if control_plane is not None:
            gw: MCPGatewayState = app.state.gw
            manifest = gw.resolver.resolve(session_id)
            try:
                control_plane.session_store.create(
                    manifest_id=manifest.workflow_id,
                    session_id=session_id,
                )
            except ValueError:
                pass  # already registered — safe to ignore

        return StreamingResponse(
            sse_stream(session_id, queue, endpoint_url, store),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.post("/mcp/messages")
    async def sse_messages(request: Request, session_id: str) -> JSONResponse:
        """
        MCP SSE transport — receive a JSON-RPC request for an SSE session.

        The client posts to this endpoint (URL received from the 'endpoint'
        event on GET /mcp/sse). The request is processed identically to
        POST /mcp, but the JSON-RPC response is pushed to the SSE stream
        rather than returned in the HTTP response body.

        Returns 202 Accepted if the request was queued, 404 if the session
        is not found (client disconnected or invalid session_id).
        """
        gw: MCPGatewayState = app.state.gw
        store: SSESessionStore = app.state.sse_store

        queue = store.get_queue(session_id)
        if queue is None:
            return JSONResponse(
                {"error": f"SSE session not found: {session_id!r}"},
                status_code=404,
            )

        resp = await _dispatch_rpc_body(gw, request, session_id_override=session_id)
        await queue.put(json.dumps(resp.model_dump(exclude_none=True)))
        return JSONResponse({"status": "accepted"}, status_code=202)

    # ------------------------------------------------------------------
    # Manifest hot-reload
    # ------------------------------------------------------------------

    @app.post("/mcp/reload")
    async def reload_manifest() -> JSONResponse:
        """Hot-reload the default WorldManifest from disk."""
        gw: MCPGatewayState = app.state.gw
        ok = gw.reload_manifest()
        manifest = gw.resolver.manifest
        return JSONResponse({
            "status": "reloaded" if ok else "failed",
            "manifest_path": str(gw.manifest_path),
            "workflow_id": manifest.workflow_id if manifest else None,
            "visible_tools": [t.name for t in gw.renderer.render()] if ok else [],
        })

    # ------------------------------------------------------------------
    # Per-session manifest management
    # ------------------------------------------------------------------

    @app.post("/mcp/sessions/{session_id}/bind")
    async def bind_session(session_id: str, body: _BindSessionRequest) -> JSONResponse:
        """
        Bind a session to a specific WorldManifest.

        After binding, tools/list and tools/call for this session_id will use
        the specified manifest instead of the gateway-level default.

        The manifest is loaded immediately. Returns 400 if the manifest file
        cannot be loaded (fail closed — no silent fallback to default).
        """
        gw: MCPGatewayState = app.state.gw
        try:
            manifest = gw.resolver.register_session(session_id, Path(body.manifest_path))
        except Exception as exc:
            return JSONResponse(
                {"status": "error", "session_id": session_id, "error": str(exc)},
                status_code=400,
            )
        renderer = gw.renderer_for(manifest)
        return JSONResponse({
            "status": "bound",
            "session_id": session_id,
            "manifest_path": body.manifest_path,
            "workflow_id": manifest.workflow_id,
            "visible_tools": [t.name for t in renderer.render()],
        })

    @app.delete("/mcp/sessions/{session_id}")
    async def unbind_session(session_id: str) -> JSONResponse:
        """
        Remove a session's manifest binding, reverting it to the default.

        Safe to call even if the session is not currently bound.
        """
        gw: MCPGatewayState = app.state.gw
        removed = gw.resolver.unregister_session(session_id)
        default_manifest = gw.resolver.manifest
        return JSONResponse({
            "status": "unbound" if removed else "not_bound",
            "session_id": session_id,
            "default_workflow_id": default_manifest.workflow_id if default_manifest else None,
        })

    @app.get("/mcp/sessions")
    async def list_sessions() -> JSONResponse:
        """
        List all active per-session manifest bindings.

        Returns a dict of session_id → workflow_id for all explicitly bound
        sessions. Sessions not listed are using the gateway-level default.
        """
        gw: MCPGatewayState = app.state.gw
        registry = gw.resolver.session_registry()
        default_manifest = gw.resolver.manifest
        return JSONResponse({
            "sessions": registry,
            "default_workflow_id": default_manifest.workflow_id if default_manifest else None,
            "session_count": len(registry),
        })

    return app


# ---------------------------------------------------------------------------
# Shared dispatch helper (used by both HTTP and SSE transports)
# ---------------------------------------------------------------------------

async def _dispatch_rpc_body(
    state: MCPGatewayState,
    request: Request,
    session_id_override: Optional[str] = None,
) -> Any:
    """
    Parse the request body and dispatch to the appropriate MCP handler.

    This is the shared core used by both POST /mcp (HTTP transport) and
    POST /mcp/messages (SSE transport). Returns a JSONRPCResponse object
    (result or error); the caller decides how to deliver it (HTTP body vs SSE
    event).

    Args:
        state:              The gateway state.
        request:            The FastAPI Request (for body + headers).
        session_id_override: If set, this session_id takes precedence over
                             whatever is extracted from headers/params. Used
                             by the SSE transport which carries the session_id
                             in the query parameter.

    Returns:
        A JSONRPCResponse (Pydantic model) — either make_result or make_error.
    """
    # Parse body
    try:
        body = await request.json()
    except Exception:
        return make_error(None, JSONRPC_PARSE_ERROR, "Parse error: body is not valid JSON")

    # Validate JSON-RPC envelope
    try:
        rpc = JSONRPCRequest.model_validate(body)
    except Exception as exc:
        return make_error(
            body.get("id") if isinstance(body, dict) else None,
            JSONRPC_PARSE_ERROR,
            f"Invalid JSON-RPC request: {exc}",
        )

    # Extract provenance; apply session_id override if provided
    provenance = _extract_provenance(request, rpc)
    if session_id_override:
        provenance = InvocationProvenance(
            source=provenance.source,
            session_id=session_id_override,
            trust_level=provenance.trust_level,
            timestamp=provenance.timestamp,
            extra=provenance.extra,
        )

    # Dispatch
    try:
        if rpc.method == "initialize":
            result = _handle_initialize(state, rpc.params or {})
            return make_result(rpc.id, result)

        elif rpc.method == "tools/list":
            result = _handle_tools_list(state, rpc.params or {}, provenance)
            return make_result(rpc.id, result)

        elif rpc.method == "tools/call":
            return _handle_tools_call(state, rpc.id, rpc.params or {}, provenance)

        else:
            return make_error(
                rpc.id,
                JSONRPC_METHOD_NOT_FOUND,
                f"Method not found: {rpc.method!r}",
            )
    except Exception as exc:
        return make_error(rpc.id, JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}")


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

    Returns only the tools visible in the session's manifest world.
    If the session has a registered manifest, that world is used; otherwise
    the gateway-level default is used. The MCP client sees only these tools —
    undeclared tools do not exist.

    When a control plane is wired, active session overlays are applied on top
    of the base manifest before rendering. A tool revealed by an overlay is
    visible only if the registry also has an adapter for it.
    """
    manifest = state.resolver.resolve(session_id=provenance.session_id)

    if state.control_plane is not None and provenance.session_id:
        # Apply session overlays: resolve world state, synthesise overlay manifest
        base_tools = manifest.tool_names()
        base_constraints = {
            c.tool: c.constraints
            for c in manifest.capabilities
            if c.constraints
        }
        view = state.control_plane.resolver.resolve(
            provenance.session_id, base_tools, base_constraints
        )
        if view.active_overlay_ids:
            overlay_manifest = manifest_from_dict(world_state_to_manifest_dict(view))
            tools = state.renderer_for(overlay_manifest).render()
            return {"tools": [t.model_dump() for t in tools]}

    tools = state.renderer_for(manifest).render()
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

    Enforces the call against the session's manifest. On denial, returns a
    JSON-RPC error response (the tool is absent or forbidden). On allow,
    dispatches to the registered adapter and returns the result.
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

    # Resolve per-session manifest and enforce
    manifest = state.resolver.resolve(session_id=provenance.session_id)
    decision = state.enforcer_for(manifest).enforce(tool_name, arguments, provenance)

    if decision.asked:
        # Policy engine returned "ask": route to approval workflow if control plane
        # is present; otherwise fail closed (treat as deny).
        if state.control_plane is not None and provenance.session_id:
            approval = state.control_plane.approval_service.request_approval(
                session_id=provenance.session_id,
                tool_name=tool_name,
                arguments=arguments,
                requested_by=provenance.source,
                event_store=state.control_plane.event_store,
            )
            return make_result(request_id, {
                "status": "pending_approval",
                "approval_id": approval.approval_id,
                "tool_name": tool_name,
                "message": (
                    f"Tool call '{tool_name}' requires operator approval. "
                    f"Resolve via POST /control/approvals/{approval.approval_id}/resolve"
                ),
            })
        else:
            # No control plane or no session → fail closed
            return make_error(
                request_id,
                MCP_TOOL_DENIED,
                f"Tool call denied: requires approval (no control plane configured)",
                data={"reason": decision.reason, "rule": decision.matched_rule},
            )

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
        # Adapter error — protocol-level success, tool-level error.
        # The result is still tainted by the invocation provenance.
        tainted = TaintedValue(value=f"Tool error: {exc}", taint=decision.taint_state)
        result_obj = MCPToolResult(
            content=[MCPContent(type="text", text=tainted.value)],
            isError=True,
        )
        return make_result(request_id, result_obj.model_dump())

    # Format result, wrapping it in TaintedValue to carry provenance taint.
    # taint_state reflects the trust level of the caller:
    #   CLEAN  — caller is trusted; result may be used in external operations
    #   TAINTED — caller is untrusted/derived; result must not flow unchecked
    if isinstance(raw_result, str):
        text = raw_result
    else:
        text = json.dumps(raw_result, default=str)

    tainted = TaintedValue(value=text, taint=decision.taint_state)

    result_obj = MCPToolResult(
        content=[MCPContent(type="text", text=tainted.value)],
        isError=False,
    )
    # Include taint metadata in the MCP result so callers can inspect it.
    result_dict = result_obj.model_dump()
    result_dict["_taint"] = tainted.taint.value  # "clean" | "tainted"
    return make_result(request_id, result_dict)


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
