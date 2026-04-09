# AH MCP Gateway — Master Implementation Plan

**Created**: 2026-04-09  
**Current version**: 0.2.0  
**Branch**: `claude/ah-mcp-gateway-impl-HLm5f`

---

## Vision

Deploy Agent Hypervisor as a **remote MCP gateway** — a world boundary layer that controls the visible tool universe, enforces deterministic execution boundaries, and makes undeclared capabilities non-existent to the agent.

```
MCP Client (Claude)
    ↓ JSON-RPC 2.0
AH MCP Gateway
    ├── tools/list → WorldManifest → visible tool surface (undeclared = non-existent)
    ├── tools/call → ToolCallEnforcer → manifest check → policy check → adapter
    └── provenance metadata hooks (source, taint, lineage)
        ↓
Real tool adapters (downstream systems)
```

---

## Scope

### In Scope
- MCP-protocol-compliant gateway (JSON-RPC 2.0 over HTTP POST)
- `tools/list` virtualization: only manifest-declared tools are visible
- `tools/call` deterministic enforcement: undeclared tools fail closed
- Static file-backed manifest binding (one manifest per gateway instance)
- Provenance source metadata capture on tool calls
- Tests covering key safety invariants
- Example manifest and demo documentation

### Out of Scope (this phase)
- SSE transport (streaming responses)
- Multi-tenant / per-session manifest selection
- Full taint propagation integration
- Approval UX / human-in-the-loop workflow (already in existing gateway)
- Distributed registry / global tool catalog
- Production hardening (auth, TLS, rate limiting)

---

## Phase Breakdown

### Phase 0 — Repository Audit ✅
**Deliverable**: `docs/implementation/repo_audit_mcp_gateway.md`  
**Status**: Complete

Identified existing components, gaps, and insertion points. Key finding: the existing `hypervisor/gateway/` is a working PoC with custom REST protocol. The new `mcp_gateway/` module is additive.

---

### Phase 1 — MCP Gateway Architecture Skeleton ✅
**Deliverable**: `src/agent_hypervisor/hypervisor/mcp_gateway/` module structure  
**Status**: Complete

New module with five files:
- `protocol.py` — JSON-RPC 2.0 models and MCP types
- `tool_surface_renderer.py` — manifest → visible tool surface
- `tool_call_enforcer.py` — deterministic tool call enforcement
- `session_world_resolver.py` — session → WorldManifest binding
- `mcp_server.py` — FastAPI app, JSON-RPC 2.0 endpoint

---

### Phase 2 — tools/list Virtualization ✅
**Deliverable**: Working `tools/list` that returns only manifest-declared tools  
**Status**: Complete

- `ToolSurfaceRenderer.render()` — filters tool registry by manifest
- Undeclared tools are absent from the response (not just forbidden)
- Static manifest loaded at startup from YAML file
- `manifests/example_world.yaml` — example manifest

---

### Phase 3 — tool/call Deterministic Enforcement ✅
**Deliverable**: Working `tools/call` with fail-closed enforcement  
**Status**: Complete

- `ToolCallEnforcer.enforce()` — manifest check, then optional policy engine
- Undeclared tool → `manifest:tool_not_declared` → deny
- Unknown adapter → `registry:no_adapter` → deny
- Policy engine consulted for declared tools (allow/deny/ask)
- All decisions are deterministic, no LLM in path

---

### Phase 4 — Manifest Binding and Session Context ✅
**Deliverable**: Clean session → manifest binding mechanism  
**Status**: Complete

- `SessionWorldResolver` — loads manifest from YAML at startup
- Single static manifest per gateway instance (clearly documented)
- Extension point: `resolve(session_id, context)` signature ready for future per-session binding

---

### Phase 5 — Provenance / Taint Hooks ✅
**Deliverable**: Provenance metadata on all tool invocations  
**Status**: Complete

- Source metadata captured from request headers / request body
- `InvocationProvenance` dataclass records: source, session_id, timestamp, trust_level
- Provenance attached to `EnforcementDecision` (available in trace log)
- Extension point: `trust_level` field ready for taint-aware enforcement

---

### Phase 6 — Docs, Tests, Demo Path ✅
**Deliverable**: Tests, demo docs, handoff note  
**Status**: Complete

- `tests/hypervisor/test_mcp_gateway.py` — invariant tests
- `docs/implementation/mcp_gateway_demo.md` — demo walkthrough
- All status files updated

---

## Target Architecture

```
manifests/example_world.yaml
    ↓ load_manifest()
SessionWorldResolver
    ↓ .resolve(session_id)
WorldManifest
    ├── ToolSurfaceRenderer.render() → [MCPTool, ...]  (for tools/list)
    └── ToolCallEnforcer.enforce()                     (for tools/call)
            ↓ manifest check (ontological absence)
            ↓ registry check (adapter exists)
            ↓ PolicyEngine.evaluate() (optional)
            ↓ verdict: allow | deny
        ToolRegistry adapter → result
```

---

## Acceptance Criteria

### Phase 1-3 (Core)
- [x] `tools/list` returns only manifest-declared tools
- [x] Undeclared tool does NOT appear in tool discovery
- [x] `tools/call` to undeclared tool fails closed with clear reason
- [x] `tools/call` to declared tool forwards to adapter successfully
- [x] Same input → same decision (deterministic)
- [x] Manifest load failure does not fail open

### Phase 4-6 (Supporting)
- [x] Manifest binding is clearly documented
- [x] Provenance metadata is captured per invocation
- [x] Tests cover all acceptance criteria above
- [x] Demo path is documented

---

## Key Invariants (Non-Negotiable)

1. No LLM in the enforcement path
2. Runtime decisions are deterministic
3. WorldManifest defines what may exist
4. Unknown/undeclared capabilities fail closed
5. Prefer ontological absence over behavioral filtering
6. Provenance metadata preserved directionally
7. Each component has a clearly bounded responsibility
