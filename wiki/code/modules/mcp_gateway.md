# Module: `hypervisor/mcp_gateway`

**Source:** [`src/agent_hypervisor/hypervisor/mcp_gateway/`](../../../src/agent_hypervisor/hypervisor/mcp_gateway/)

The `mcp_gateway` sub-package is the **AH MCP Gateway** — a JSON-RPC 2.0 server that enforces manifest-driven tool visibility and execution governance for MCP clients (Claude Desktop, Cursor, or any LLM agent). It sits between an MCP client and the underlying tool ecosystem, controlling what tools exist in the agent's world and whether individual calls are permitted.

Status: **Supported** (working and maintained; PoC quality — not production hardened).

---

## Core Principle

> *Ontological absence, not runtime filtering.*

A tool that is not declared in the WorldManifest does not exist in this world. It is absent — not merely forbidden. The MCP client never learns of undeclared tools. There is nothing to call, nothing to refuse, and nothing to leak through error messages.

This is distinct from a runtime filter ("this tool exists but you may not call it"). Absence produces a smaller attack surface and eliminates entire categories of prompt-injection attacks that rely on the LLM knowing a tool exists.

---

## Architecture

```
MCP Client (Claude / Cursor / any agent)
    │
    │  JSON-RPC 2.0
    ▼
┌──────────────────────────────────────────────┐
│              AH MCP Gateway                  │
│                                              │
│  POST /mcp          (HTTP transport)         │
│  GET  /mcp/sse      (SSE transport: open)    │
│  POST /mcp/messages (SSE transport: send)    │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │         SessionWorldResolver           │  │
│  │  session_id → WorldManifest binding    │  │
│  └────────────────────────────────────────┘  │
│           │                                  │
│  ┌────────┴───────────────────────────────┐  │
│  │  tools/list → ToolSurfaceRenderer      │  │
│  │  tools/call → ToolCallEnforcer         │  │
│  └────────────────────────────────────────┘  │
│           │                                  │
│  ┌────────┴───────────────────────────────┐  │
│  │          ToolRegistry (adapters)       │  │
│  │   send_email  read_file  http_post …   │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## File Map

| File | Key Symbols | Description |
|------|-------------|-------------|
| `__init__.py` | `create_mcp_app` | Public API; re-exports all key symbols |
| `protocol.py` | `JSONRPCRequest`, `JSONRPCResponse`, `MCPTool`, `MCPToolResult`, error codes | JSON-RPC 2.0 wire types and MCP-specific error codes |
| `tool_surface_renderer.py` | `ToolSurfaceRenderer` | Renders the visible tool surface for `tools/list` |
| `tool_call_enforcer.py` | `ToolCallEnforcer`, `EnforcementDecision`, `InvocationProvenance` | 4-stage deterministic enforcement pipeline |
| `session_world_resolver.py` | `SessionWorldResolver` | Maps session IDs to WorldManifest instances |
| `mcp_server.py` | `create_mcp_app`, `MCPGatewayState` | FastAPI app factory; all HTTP and SSE endpoints |
| `sse_transport.py` | `SSESessionStore` | Registry of active SSE sessions and stream helpers |

---

## Enforcement Pipeline

When `tools/call` is received, `ToolCallEnforcer.enforce()` runs four deterministic stages in order:

```
tools/call {name, arguments}
    │
    ▼  Stage 1: Manifest declaration check
    │  Is tool_name in manifest.tool_names()?
    │  No → deny, rule=manifest:tool_not_declared
    │         ("tool does not exist in this world")
    │
    ▼  Stage 2: Registry check
    │  Does a tool adapter exist for tool_name?
    │  No → deny, rule=registry:no_adapter
    │
    ▼  Stage 3: Policy engine check (optional)
    │  PolicyEngine.evaluate() returns deny or ask?
    │  Yes → deny, rule=policy:<matched_rule>
    │         (ask is treated as deny — fail closed)
    │
    ▼  Stage 4: Manifest constraint check
    │  cap.allows(tool_name, arguments)?
    │  No → deny, rule=manifest:constraint_violated
    │
    ▼  All stages passed
       allow, rule=manifest:allowed
```

**Invariants:**
- No LLM in this path.
- Same input → same output (deterministic).
- Unknown tool → deny, never allow.
- If `manifest is None` (startup failure) → deny all.
- Policy engine errors → deny (fail closed, not fail open).

---

## ToolSurfaceRenderer

`ToolSurfaceRenderer.render()` produces the `tools/list` response. Two sources of truth must agree for a tool to appear:

1. **WorldManifest declares it** — ontological inclusion.
2. **ToolRegistry has an adapter** — implementation exists.

Tools in the registry but not in the manifest are invisible. Tools declared in the manifest but lacking an adapter are silently skipped (allows manifests to declare intent before adapters exist). Order follows the manifest's capability list.

```python
renderer = ToolSurfaceRenderer(manifest, registry)
tools: list[MCPTool] = renderer.render()
# → only manifest-declared tools with adapters
```

---

## SessionWorldResolver

Each gateway has a **default manifest** loaded at startup. Individual sessions can be bound to a different manifest, letting multiple agents operate in different worlds simultaneously without restarting the gateway.

```python
resolver = SessionWorldResolver(Path("manifests/example_world.yaml"))

# All sessions default to the gateway manifest
manifest = resolver.resolve(session_id="s1")

# Bind a session to a different world
resolver.register_session("s1", Path("manifests/read_only_world.yaml"))
manifest = resolver.resolve(session_id="s1")  # → read_only_world

# Revert to default
resolver.unregister_session("s1")
```

**Fail-closed startup:** If the default manifest cannot be loaded, `__init__` raises immediately. The gateway never starts with a missing or invalid manifest.

**Reload safety:** `reload()` retains the existing manifest if reload fails (fail safe, not fail open). Per-session bindings are unaffected.

---

## Taint Propagation Bridge

Every `EnforcementDecision` carries a `TaintContext` derived from `InvocationProvenance.trust_level`. This bridges the MCP gateway's provenance metadata with the runtime taint system:

| `trust_level` | `TaintContext` | Meaning |
|---------------|----------------|---------|
| `"trusted"` | `CLEAN` | Authorised orchestrator; result may flow to external actions |
| `"derived"` | `TAINTED` | Value derived from LLM / external source |
| `"untrusted"` (default) | `TAINTED` | Unknown or external caller |

Taint is never removed. Even allowed calls from untrusted sources carry `TAINTED` through to the tool result, which is wrapped in a `TaintedValue` before being returned to the caller.

```python
decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"}, provenance)
if decision.allowed:
    raw = adapter(arguments)
    tainted = TaintedValue(value=raw, taint=decision.taint_state)
    # tainted.taint is CLEAN only if provenance.trust_level == "trusted"
```

The `_taint` field is included in the JSON-RPC `tools/call` result so callers can inspect taint state without parsing tool output.

---

## Transport Protocols

### HTTP POST (default)

```
POST /mcp
Content-Type: application/json

{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
```

All JSON-RPC application errors (tool denied, method not found, etc.) return HTTP 200. Only transport-level parse failures return HTTP 400.

### SSE (Server-Sent Events)

```
# 1. Open stream
GET /mcp/sse
→ 200 OK  Content-Type: text/event-stream
→ event: endpoint
  data: /mcp/messages?session_id=<uuid>

# 2. Send requests
POST /mcp/messages?session_id=<uuid>
→ 202 Accepted

# 3. Receive responses on the open stream
→ event: message
  data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

A keep-alive comment is sent every ~25 s to prevent proxy timeouts.

---

## HTTP API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/mcp` | JSON-RPC 2.0 dispatcher (HTTP transport) |
| `GET` | `/mcp/sse` | Open SSE stream; server sends `endpoint` event |
| `POST` | `/mcp/messages?session_id=<uuid>` | Submit JSON-RPC request for SSE session |
| `GET` | `/mcp/health` | Health check + world summary (visible tools, manifest info) |
| `POST` | `/mcp/reload` | Hot-reload default manifest from disk |
| `POST` | `/mcp/sessions/{session_id}/bind` | Bind session to a specific manifest |
| `DELETE` | `/mcp/sessions/{session_id}` | Unbind session; revert to default |
| `GET` | `/mcp/sessions` | List all active per-session bindings |

### Per-session manifest binding

```
POST /mcp/sessions/my-agent/bind
Content-Type: application/json
{"manifest_path": "manifests/read_only_world.yaml"}

→ 200 OK
{"status": "bound", "session_id": "my-agent",
 "workflow_id": "read-only-v1", "visible_tools": ["read_file"]}
```

Returns HTTP 400 if the manifest file cannot be loaded (fail closed).

---

## MCP Methods

| Method | Description |
|--------|-------------|
| `initialize` | MCP handshake; returns server capabilities and manifest summary |
| `tools/list` | Returns only manifest-declared tools visible in the session's world |
| `tools/call` | Deterministic enforcement, then adapter dispatch |

Any other method returns JSON-RPC error `-32601` (Method not found).

---

## Error Codes

| Code | Constant | Condition |
|------|----------|-----------|
| `-32700` | `JSONRPC_PARSE_ERROR` | Request body is not valid JSON |
| `-32601` | `JSONRPC_METHOD_NOT_FOUND` | Unknown JSON-RPC method |
| `-32602` | `JSONRPC_INVALID_PARAMS` | Missing or malformed `tools/call` params |
| `-32603` | `JSONRPC_INTERNAL_ERROR` | Unhandled exception in handler |
| `-32001` | `MCP_TOOL_NOT_FOUND` | Tool not declared in manifest / no adapter |
| `-32002` | `MCP_TOOL_DENIED` | Tool exists but call denied by policy or constraint |
| `-32003` | `MCP_MANIFEST_ERROR` | Manifest could not be loaded or is invalid |

`-32001` and `-32002` are intentionally distinct: `-32001` means the tool does not exist in this world; `-32002` means it exists but the specific call was denied. Callers should not retry `-32001` — the tool is absent, not temporarily unavailable.

---

## Usage

```python
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
import uvicorn

# Minimal: single manifest, default policy
app = create_mcp_app("manifests/example_world.yaml")
uvicorn.run(app, host="127.0.0.1", port=8090)

# With bundled provenance firewall policy
app = create_mcp_app("manifests/example_world.yaml", use_default_policy=True)

# With a custom PolicyEngine
from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
engine = PolicyEngine.from_yaml("configs/my_policy.yaml")
app = create_mcp_app("manifests/example_world.yaml", policy_engine=engine)
```

**Quick test:**
```bash
# List visible tools
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq .

# Call a declared tool
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_file","arguments":{"path":"/etc/hostname"}}}'

# Call an undeclared tool — fails closed with -32001
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"http_post","arguments":{}}}'
# → {"error":{"code":-32001,"message":"Tool not found: 'http_post'"}}
```

---

## Security Invariants

| Invariant | Where enforced |
|-----------|----------------|
| Undeclared tools never appear in `tools/list` | `ToolSurfaceRenderer.render()` |
| Undeclared tool call always fails with `-32001` | `ToolCallEnforcer` Stage 1 |
| Missing adapter always fails with `-32001` | `ToolCallEnforcer` Stage 2 |
| Policy engine error → deny, not allow | `ToolCallEnforcer._evaluate_policy()` |
| Manifest load failure → gateway does not start | `SessionWorldResolver.__init__()` |
| Per-session bind failure → session not registered | `SessionWorldResolver.register_session()` |
| Reload failure → existing manifest retained | `SessionWorldResolver.reload()` |
| Taint context always set on `EnforcementDecision` | `ToolCallEnforcer.enforce()` |
| `trust_level` defaults to `"untrusted"` (TAINTED) | `InvocationProvenance` dataclass default |
| Tool results always wrapped in `TaintedValue` | `mcp_server._handle_tools_call()` |

---

## See Also

- [Package: hypervisor](../hypervisor.md) — parent package; PoC gateway, PolicyEngine, ProvenanceFirewall
- [Taint Engine](taint.md) — monotonic taint lattice that `taint_context` plugs into
- [ProvenanceFirewall](firewall.md) — structural provenance rules (the optional Stage 3 policy)
- [World Manifest](../../concepts/world-manifest.md) — the manifest that defines the agent's world
- [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md) — conceptual overview of the trust model
- [`examples/mcp_gateway/`](../../../examples/mcp_gateway/) — end-to-end runnable demo
