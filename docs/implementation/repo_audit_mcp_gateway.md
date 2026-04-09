# Repository Audit: MCP Gateway Insertion Points

**Date**: 2026-04-09  
**Purpose**: Identify existing components, gaps, and optimal insertion points for AH as MCP Gateway.

---

## 1. Relevant Existing Files

### MCP / Gateway Entry Points

| File | Status | Notes |
|------|--------|-------|
| `src/agent_hypervisor/hypervisor/gateway/gateway_server.py` | Exists | FastAPI HTTP gateway, custom REST protocol (not MCP JSON-RPC) |
| `src/agent_hypervisor/hypervisor/gateway/execution_router.py` | Exists | Provenance + policy enforcement router |
| `src/agent_hypervisor/hypervisor/gateway/tool_registry.py` | Exists | `ToolRegistry` with adapters (send_email, http_post, read_file) |
| `src/agent_hypervisor/hypervisor/gateway/config_loader.py` | Exists | Gateway YAML config loader |
| `src/agent_hypervisor/authoring/integrations/mcp/server.py` | Exists (stub) | References non-existent packages (`safe_agent_runtime_core`) — non-functional |

### Manifest / Policy / Provenance

| File | Status | Notes |
|------|--------|-------|
| `src/agent_hypervisor/compiler/schema.py` | Stable | `WorldManifest`, `CapabilityConstraint`, `manifest_from_dict` — usable directly |
| `src/agent_hypervisor/compiler/manifest.py` | Stable | `load_manifest()`, `save_manifest()` — usable directly |
| `src/agent_hypervisor/hypervisor/policy_engine.py` | Supported | `PolicyEngine.from_yaml()`, rule-based verdict |
| `src/agent_hypervisor/hypervisor/firewall.py` | Supported | `ProvenanceFirewall` — structural provenance rules |
| `src/agent_hypervisor/runtime/configs/default_policy.yaml` | Exists | Default policy rules (deny > ask > allow) |

### Core Runtime (do not break)

| File | Status | Notes |
|------|--------|-------|
| `src/agent_hypervisor/runtime/proxy.py` | Canonical | `SafeMCPProxy` — in-path enforcement, subprocess boundary |
| `src/agent_hypervisor/runtime/ir.py` | Canonical | `IRBuilder`, sealed `IntentIR` |
| `src/agent_hypervisor/runtime/taint.py` | Canonical | `TaintContext`, `TaintedValue` |
| `src/agent_hypervisor/runtime/executor.py` | Canonical | Subprocess dispatch |

---

## 2. Current Architecture Gaps

### Gap 1: No MCP Protocol Compliance
The existing gateway (`gateway_server.py`) uses a custom REST API (`POST /tools/execute`), not the MCP JSON-RPC 2.0 protocol. Claude and other MCP clients cannot connect to it as-is.

### Gap 2: No Manifest-Driven tools/list
`POST /tools/list` returns all registered tools unconditionally. It does not filter by manifest. Any tool in the registry is visible to all clients, regardless of their declared world.

### Gap 3: No Manifest Binding
There is no mechanism to bind a request/session to a `WorldManifest`. Tools exist globally in the registry, not per-world.

### Gap 4: Non-Functional MCP Stub
`authoring/integrations/mcp/server.py` references `safe_agent_runtime_core` and `safe_agent_runtime_pro` — packages that do not exist in this repo. It is dead code.

---

## 3. Recommended Insertion Points

### New Module: `hypervisor/mcp_gateway/`

This is the correct insertion point for the MCP-compliant gateway. It should:
- Live alongside the existing `hypervisor/gateway/` (do not replace it)
- Reuse `WorldManifest` from `compiler/` and `ToolRegistry` from `hypervisor/gateway/`
- Add new classes with clearly bounded responsibilities

**New files:**
```
src/agent_hypervisor/hypervisor/mcp_gateway/
├── __init__.py
├── protocol.py            # JSON-RPC 2.0 models (MCPTool, MCPRequest, MCPResponse)
├── tool_surface_renderer.py  # WorldManifest → visible tool surface
├── tool_call_enforcer.py  # Deterministic enforcement (manifest → policy → allow/deny)
├── session_world_resolver.py # Session → WorldManifest binding
└── mcp_server.py          # FastAPI app, JSON-RPC 2.0 endpoint
```

**Example manifest:**
```
manifests/example_world.yaml
```

**Tests:**
```
tests/hypervisor/test_mcp_gateway.py
```

### Why Not Modify the Existing Gateway?
The existing `gateway_server.py` is a working PoC that exercises provenance firewall logic. Modifying it risks breaking that logic. The new `mcp_gateway/` module is additive, non-destructive, and has a clearly bounded scope.

---

## 4. Reuse Plan

| Existing component | Reuse in mcp_gateway |
|---|---|
| `compiler.schema.WorldManifest` | Directly — it's the core of tools/list virtualization |
| `compiler.manifest.load_manifest` | Directly — load manifest from YAML |
| `hypervisor.gateway.tool_registry.ToolRegistry` | Directly — adapter dispatch |
| `hypervisor.policy_engine.PolicyEngine` | Optionally — secondary enforcement layer |
| `hypervisor.models.ProvenanceClass` | For provenance metadata on tool calls |

---

## 5. Anti-Goals (Do Not Touch Now)

- `runtime/` — the canonical core; do not add MCP calls here
- `archive/`, `lab/` — frozen
- `authoring/integrations/mcp/server.py` — leave as-is (dead code, but harmless)
- `hypervisor/gateway/gateway_server.py` — do not modify; work alongside it
- Full SSE transport — out of scope for Phase 1
- Multi-tenant manifest selection — out of scope for now
