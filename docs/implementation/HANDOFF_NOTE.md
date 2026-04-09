# Handoff Note — Session 9

**Date**: 2026-04-09  
**Branch**: `claude/control-plane-scaffolding-ugZhz`  
**Session**: Control Plane API + Demo (Phases 5–6)

---

## What Was Done

Added the control plane HTTP API (Phase 5) and demo documentation (Phase 6).

### Files Created

```
src/agent_hypervisor/control_plane/api.py   ← FastAPI router + ControlPlaneState
tests/control_plane/test_api.py             ← 44 API endpoint tests
docs/implementation/control_plane_demo.md   ← 8-step curl walkthrough
```

### api.py summary

- `ControlPlaneState` — dataclass holding SessionStore, EventStore, ApprovalService,
  OverlayService, WorldStateResolver, and optional `get_base_manifest` callback.
- `ControlPlaneState.create(...)` — factory for fresh in-memory state.
- `create_control_plane_router(state)` — returns `APIRouter(prefix="/control")`.
- `create_control_plane_app(...)` — standalone FastAPI app (for testing/demo).
- Endpoints: sessions CRUD, world state, event log, approval resolution, overlay attach/detach.

---

## Current Test Count

```
pytest tests/control_plane/  →  101 passed (57 domain/service + 44 API)
```

---

## What Remains

### 1. Gateway Wiring (highest value next step)

Connect the control plane to the MCP gateway enforcement loop.

**File to modify**: `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py`

**Changes needed**:
- `MCPGatewayState` should optionally hold a `ControlPlaneState`
- In `_handle_tools_call()`, when `ToolCallEnforcer` returns `verdict = ask`:
  ```python
  approval = cp_state.approval_service.request_approval(
      session_id=provenance.session_id,
      tool_name=tool_name,
      arguments=arguments,
      requested_by=provenance.source,
      event_store=cp_state.event_store,
  )
  # Return pending response to caller
  return make_result(request_id, {
      "status": "pending_approval",
      "approval_id": approval.approval_id,
  })
  ```
- In `_handle_tools_list()`, when a ControlPlaneState is present:
  ```python
  manifest = state.resolver.resolve(session_id)
  base_tools = manifest.tool_names()
  base_constraints = {c.tool: c.constraints for c in manifest.capabilities}
  view = cp_state.resolver.resolve(session_id, base_tools, base_constraints)
  # Use view.visible_tools to drive ToolSurfaceRenderer
  ```

**Note**: The `MCPGatewayState.policy_engine` can return `ask` verdicts. The existing
`ToolCallEnforcer` propagates the policy verdict but does not have a hook for ASK. The
simplest approach is to check `decision.verdict == "ask"` after `enforcer.enforce()`.

### 2. Mount on MCP Gateway App

In `create_mcp_app()` in `mcp_server.py`:

```python
from agent_hypervisor.control_plane.api import ControlPlaneState, create_control_plane_router

cp_state = ControlPlaneState.create(
    get_base_manifest=lambda sid: (
        state.resolver.resolve(sid).tool_names(),
        {c.tool: c.constraints for c in state.resolver.resolve(sid).capabilities},
    )
)
app.state.control_plane = cp_state
app.include_router(create_control_plane_router(cp_state))
```

This makes both `/mcp/*` and `/control/*` available on the same server.

### 3. Session Creation Hook

When a new SSE session is created in `GET /mcp/sse`, auto-register it with the control plane:

```python
# In sse_endpoint():
cp_state = app.state.control_plane
cp_state.session_store.create(
    manifest_id=gw.resolver.resolve(session_id).workflow_id,
    session_id=session_id,
)
```

---

## Key Invariants to Preserve

1. `ControlPlaneState` is a dataclass — do not add mutable default values.
2. `get_base_manifest` is a callable, not a stored manifest — keeps it lazy.
3. `list_pending_approvals` calls `check_expired()` — this is intentional (sweep before list).
4. `PATCH /control/sessions/{id}/mode` emits a `mode_changed` event — keep this.
5. The `/world` endpoint does not cache — always recomputes (deterministic resolver).
6. `DELETE /control/sessions/{id}/overlays/{oid}` returns 404 for already-detached — keep (idempotency would hide bugs).

---

## Architecture (Final Phase 5 state)

```
HTTP Client (operator/UI)
        ↓
FastAPI Control Plane Router (/control/*)
        ↓
ControlPlaneState
  ├── SessionStore       ← session lifecycle
  ├── EventStore         ← append-only audit log
  ├── ApprovalService    ← fingerprint-bound TTL approvals
  ├── OverlayService     ← session-scoped world augmentation
  └── WorldStateResolver ← base_tools + overlays → WorldStateView
        ↓ get_base_manifest (bridge)
MCPGatewayState.resolver.resolve(session_id) → WorldManifest
        ↓
ToolSurfaceRenderer / ToolCallEnforcer   [data plane, unchanged]
```

---

## Do Not Touch

- `tests/control_plane/test_control_plane.py` — domain + service invariants
- `tests/control_plane/test_api.py` — API contract tests
- `domain.py` — stable types; downstream code imports from here
- `src/agent_hypervisor/hypervisor/mcp_gateway/` — only ADD the wiring, don't rewrite
