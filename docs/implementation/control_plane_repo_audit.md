# Control Plane — Repository Audit (Phase 0)

**Date**: 2026-04-09  
**Auditor**: Claude Code (session: control-plane-scaffolding)

---

## Purpose

Identify the existing runtime/gateway/policy boundaries and determine exactly where the control plane components should live without breaking the existing data plane.

---

## Existing Boundaries

### Data Plane (existing, do not break)

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ToolSurfaceRenderer` | `hypervisor/mcp_gateway/tool_surface_renderer.py` | manifest → visible tools for tools/list |
| `ToolCallEnforcer` | `hypervisor/mcp_gateway/tool_call_enforcer.py` | deterministic enforcement (manifest + registry + policy + constraints) |
| `SessionWorldResolver` | `hypervisor/mcp_gateway/session_world_resolver.py` | session_id → WorldManifest (static per-session binding) |
| `MCPGatewayState` | `hypervisor/mcp_gateway/mcp_server.py` | immutable gateway state; renderer + enforcer built from manifest |
| `PolicyEngine` | `hypervisor/policy_engine.py` | declarative rule evaluation (allow/deny/ask) |
| `ProvenanceFirewall` | `hypervisor/firewall.py` | structural provenance chain validation |
| `ApprovalStore` | `hypervisor/storage/approval_store.py` | file-backed approval records (legacy; one JSON per approval_id) |
| `TraceStore` | `hypervisor/storage/trace_store.py` | append-only audit log |
| `WorldManifest` | `compiler/schema.py` | declarative boundary spec (tool names + constraints) |

### Control Plane (new, additive)

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `SessionStore` | `control_plane/session_store.py` | tracks session state machine |
| `EventStore` | `control_plane/event_store.py` | structured per-session audit log |
| `ApprovalService` | `control_plane/approval_service.py` | fingerprint-bound, TTL-governed one-off approvals |
| `OverlayService` | `control_plane/overlay_service.py` | session-scoped world augmentation overlays |
| `WorldStateResolver` | `control_plane/world_state_resolver.py` | computes resolved WorldStateView from base manifest + active overlays |

---

## Insertion Points

### Where Session State Should Live

**Now**: `SessionWorldResolver._session_registry` holds `session_id → WorldManifest` — static, no lifecycle state.

**Control Plane addition**: `SessionStore` owns the session lifecycle (created, active, waiting_approval, blocked, closed). The session record includes `manifest_id`, `overlay_ids`, `mode`, and timestamps.

**Bridge**: When the control plane needs to change the visible world for a session, it calls `SessionWorldResolver.register_session(session_id, manifest_path)` — or, once overlays are wired in, `MCPGatewayState.enforcer_for(resolved_manifest)` uses the overlay-resolved manifest.

### Where Approval State Should Live

**Now**: `ApprovalStore` (legacy REST gateway, file-backed JSON per approval). Not wired to MCP gateway.

**Control Plane addition**: `ApprovalService` owns approval lifecycle with:
- in-memory pending queue (fast path for real-time decisions)
- fingerprint-based binding (not session-only)
- TTL enforcement (expired approvals are invalid)
- event emission to `EventStore`

**Bridge**: The MCP gateway's `ToolCallEnforcer` currently returns `verdict = ask` when policy says ASK. The control plane `ApprovalService` should handle these ASK verdicts. The MCP gateway needs a future hook to:
1. Emit an `approval_requested` event when verdict is `ask`
2. Hold the response or return `pending` status to caller
3. Resume when approval is resolved

This wiring is deferred to Phase 5 (API surface). In Phase 1, `ApprovalService` is a clean standalone service.

### Where Overlay Resolution Should Live

**Now**: No overlay concept exists. `SessionWorldResolver` only knows about static manifests.

**Control Plane addition**: `OverlayService` manages per-session overlays. `WorldStateResolver` applies active overlays on top of a base manifest to produce a `WorldStateView`.

**Bridge**: The `WorldStateView.visible_tools` can be used to synthesize a `WorldManifest` that `SessionWorldResolver.register_session()` ingests. This is the planned evolution path:
```
OverlayService.get_active_overlays(session_id)
    → WorldStateResolver.resolve(session_id, base_manifest)
    → WorldStateView (visible_tools, constraints)
    → synthesize overlay WorldManifest
    → SessionWorldResolver.register_session(session_id, ...)
```

### What Must NOT Be Rewritten Now

- `ToolCallEnforcer` — the enforcement pipeline is stable and tested (83 tests)
- `ToolSurfaceRenderer` — correct manifest rendering, stable
- `SessionWorldResolver` — clean interface; add to it, don't replace it
- `PolicyEngine` — tested, declarative, correct
- `WorldManifest` / `CapabilityConstraint` — canonical schema; only add fields via overlays
- All test infrastructure in `tests/hypervisor/`

---

## Data Flow After Control Plane Is Wired

```
MCP Client (tools/call)
    ↓
MCPGatewayState._dispatch_rpc_body()
    ↓
_extract_provenance() → InvocationProvenance
    ↓
SessionWorldResolver.resolve(session_id)
    ↓ [future: WorldStateResolver feeds this]
WorldManifest (base + overlays resolved)
    ↓
ToolCallEnforcer.enforce(tool, args, provenance)
    ↓
EnforcementDecision (allow | deny | [future: ask])
    ↓ if ask:
    ApprovalService.request_approval(...)
    EventStore.append(approval_requested)
    ↓ if allow:
    tool_def.adapter(arguments)
    EventStore.append(tool_executed)
    ↓
TaintedValue(result, taint_state)
```

---

## Key Gaps Identified

| Gap | Severity | Plan |
|-----|----------|------|
| No session lifecycle state (created/active/closed) | High | `SessionStore` in Phase 1 |
| No fingerprint-based approval with TTL | High | `ApprovalService` in Phase 1/2 |
| No session overlays | High | `OverlayService` in Phase 1/3 |
| No resolved world state view | High | `WorldStateResolver` in Phase 1/4 |
| ASK verdict not plumbed into gateway | Medium | Phase 5 (wiring) |
| No control plane API endpoints | Medium | Phase 5 |
| Economic layer not wired to gateway | Low | Future |

---

## Conclusion

The control plane can be introduced as a **pure additive module** at `src/agent_hypervisor/control_plane/`. No existing data plane files need modification in Phase 1. The domain model and service layer can be implemented and tested independently. Wiring to the MCP gateway happens in Phase 5.
