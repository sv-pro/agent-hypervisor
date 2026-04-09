# Handoff Note — Session 10

**Date**: 2026-04-09  
**Branch**: `claude/control-plane-scaffolding-ugZhz`  
**Session**: Gateway Wiring (Phase 7)

---

## What Was Done

Wired the control plane into the MCP gateway enforcement loop. This is the bridge
between the data plane (`ToolCallEnforcer`, `ToolSurfaceRenderer`) and the control
plane services (`ApprovalService`, `OverlayService`, `WorldStateResolver`).

### Files Modified

```
src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py
src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py
```

### Files Created

```
tests/hypervisor/test_gateway_wiring.py   ← 23 integration tests, all passing
```

---

## Changes in Detail

### tool_call_enforcer.py

- Added `asked` property to `EnforcementDecision`:
  ```python
  @property
  def asked(self) -> bool:
      """True when the policy engine returned 'ask' and a control plane can handle it."""
      return self.verdict == "ask"
  ```
- Changed `_evaluate_policy()` to return a real `EnforcementDecision(verdict="ask")`
  instead of collapsing it to "deny". This is the key change that makes "ask" verdicts
  routable to an approval workflow rather than silently denied.

### mcp_server.py

- `MCPGatewayState.__init__` now accepts `control_plane: Optional[ControlPlaneState]`
- `create_mcp_app()` accepts `control_plane` and:
  - Auto-configures the `get_base_manifest` bridge if not already set
  - Mounts `create_control_plane_router(control_plane)` on the same FastAPI app
- `sse_endpoint` auto-registers new SSE sessions with `control_plane.session_store`
- `_handle_tools_list()` checks for active overlays via `WorldStateResolver` when
  a control plane is wired; if overlays are active, synthesizes a modified manifest
  via `world_state_to_manifest_dict()` and feeds it to `ToolSurfaceRenderer`
- `_handle_tools_call()` checks `decision.asked`:
  - With control plane + session_id: routes to `ApprovalService.request_approval()`,
    returns `{"status": "pending_approval", "approval_id": ...}` to caller
  - Without control plane or session_id: fails closed (deny)

---

## Current Test Count

```
pytest tests/control_plane/   →  101 passed (57 domain/service + 44 API)
pytest tests/hypervisor/test_gateway_wiring.py  →  23 passed
```

Note: `tests/hypervisor/test_mcp_gateway.py` has 21 pre-existing failures due to
`pytest-asyncio` not being installed (async test functions). These predate this
session and are not caused by our changes.

---

## Architecture (Final State)

```
HTTP Client (operator/UI)
        ↓
FastAPI Control Plane Router (/control/*)   ← mounted on same app
        ↓
ControlPlaneState
  ├── SessionStore       ← auto-populated by SSE session creation
  ├── EventStore         ← append-only audit log
  ├── ApprovalService    ← receives "ask" verdicts from enforcement
  ├── OverlayService     ← session-scoped world augmentation
  └── WorldStateResolver ← base_tools + overlays → WorldStateView
        ↓ get_base_manifest bridge
MCPGatewayState
  ├── resolver           → WorldManifest
  ├── enforcer           → EnforcementDecision (allow | deny | ask)
  └── control_plane      → ControlPlaneState (new)
        ↓
ToolSurfaceRenderer / ToolCallEnforcer   [data plane]
  ↑
  WorldStateView (via world_state_to_manifest_dict) when overlays active
```

---

## What Remains

### High Value

1. **Approval resolution feedback loop** — when an approval is resolved via
   `PATCH /control/approvals/{id}`, the MCP session should be notified so it can
   retry the tool call. Currently the caller must re-issue the tool call manually.

2. **Persistent storage** — all stores are in-memory. A SQLite or Redis backend
   would survive restarts.

### Lower Priority

3. **WebSocket live updates** — currently the operator must poll `/control/sessions/{id}/world`
   to see overlay changes reflected in real time.

4. **Auth layer** — control plane endpoints have no auth. Fine for local/demo; needs
   API key or JWT for production.

5. **RBAC** — distinguish "end user" (can resolve own approvals) from "operator"
   (can attach overlays and manage sessions).

---

## Key Invariants Preserved

1. No LLM in enforcement path ✅
2. Base manifest never mutated at runtime ✅
3. All runtime world changes are session-scoped overlays ✅
4. One-off approvals do not widen the world ✅
5. Operator augmentation is explicit and auditable ✅
6. Unknown capabilities still fail closed ✅
7. Control plane ≠ data plane ✅
8. "ask" without a control plane still fails closed ✅

---

## Do Not Touch

- `tests/control_plane/test_control_plane.py` — domain + service invariants
- `tests/control_plane/test_api.py` — API contract tests
- `domain.py` — stable types; downstream code imports from here
- `tests/hypervisor/test_gateway_wiring.py` — gateway wiring invariants
