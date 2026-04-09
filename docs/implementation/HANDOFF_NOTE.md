# Handoff Note — Session 8

**Date**: 2026-04-09  
**Branch**: `claude/control-plane-scaffolding-ugZhz`  
**Session**: Control Plane Scaffolding (Phases 0–4)

---

## What Was Done

Introduced the first World Authoring Control Plane as a new module `src/agent_hypervisor/control_plane/`. This is additive — no existing data plane code was modified.

### Files Created (control plane)

```
src/agent_hypervisor/control_plane/
├── __init__.py               ← clean public API exports
├── domain.py                 ← Session, ActionApproval, SessionOverlay, WorldStateView, ...
├── session_store.py          ← SessionStore (in-memory session lifecycle)
├── event_store.py            ← EventStore (append-only audit log + event factories)
├── approval_service.py       ← ApprovalService (fingerprint-bound TTL approvals)
├── overlay_service.py        ← OverlayService (session-scoped world augmentation)
└── world_state_resolver.py   ← WorldStateResolver + world_state_to_manifest_dict

tests/control_plane/
├── __init__.py
├── conftest.py
└── test_control_plane.py     ← 57 tests, all passing

docs/implementation/
├── CONTROL_PLANE_PLAN.md
├── control_plane_repo_audit.md
WORLD_AUTHORING.md            ← project root, architecture overview
```

### pyproject.toml change

Added `src` to `pythonpath = ["src/agent_hypervisor", "src"]`.
- Reason: makes `agent_hypervisor` importable as a top-level package in tests.
- Backwards compatible: `src/agent_hypervisor` still present.

---

## Current State

57 control plane tests pass.

```
pytest tests/control_plane/  → 57 passed
```

The MCP gateway (Sessions 1–7) still works; its tests require `pip install -e .` to run.

---

## What Remains

### Phase 5 — Control Plane API Surface
Create `src/agent_hypervisor/control_plane/api.py` with a FastAPI router:

```python
from fastapi import APIRouter
router = APIRouter(prefix="/control")

GET  /control/sessions
GET  /control/sessions/{session_id}
GET  /control/sessions/{session_id}/world
GET  /control/approvals?session_id=...
POST /control/approvals/{approval_id}/resolve
POST /control/sessions/{session_id}/overlays
DELETE /control/sessions/{session_id}/overlays/{overlay_id}
```

Mount with: `app.include_router(router)` on the existing MCP gateway app.

### Phase 6 — Demo and Docs
Create `docs/implementation/control_plane_demo.md` with the full walkthrough:
1. Session starts in background mode
2. Agent requests send_email approval
3. Operator approves (once)
4. Operator attaches session overlay (reveals write_file)
5. World state is inspected and reflects the overlay
6. Overlay is detached; world reverts to base manifest

### Wiring into Gateway (future)
The bridge is already designed in `world_state_to_manifest_dict()`. The next step:
1. In `_handle_tools_call()` (mcp_server.py), when `ToolCallEnforcer` returns verdict=`ask`:
   - Call `ApprovalService.request_approval()`
   - Store the pending approval
   - Return a pending response to the caller (or block)
2. In `_handle_tools_list()`, call `WorldStateResolver.resolve()` and use the result
   to feed a synthetic manifest into `ToolSurfaceRenderer`.

---

## Key Invariants the Next Session Must Preserve

1. **Base manifest is never mutated** — overlays are separate; `OverlayService.attach()` does not touch `WorldManifest`.
2. **Approvals do not widen the world** — `ApprovalService.resolve()` does not affect `visible_tools`.
3. **`compute_action_fingerprint()` must remain deterministic** — do not change the hash algorithm or JSON serialization without updating all callers.
4. **`check_expired()` on `ApprovalService`** must be called before listing pending approvals in production (not automatically called by `list_pending()`).
5. **`WorldStateResolver` is stateless** — it reads from stores but never writes. Keep it pure.
6. **overlay_ids in Session** is ordered — append order matters for overlay precedence.

---

## Architecture Summary

```
Control Plane (session_store, event_store, approval_service, overlay_service)
    ↓
WorldStateResolver
    ↓ world_state_to_manifest_dict()
    ↓
SessionWorldResolver.register_session()  [existing MCP gateway]
    ↓
ToolSurfaceRenderer / ToolCallEnforcer   [existing enforcement pipeline]
```

The bridge is `world_state_to_manifest_dict()` in `world_state_resolver.py`. It converts a `WorldStateView` (control plane) into a manifest dict the data plane can ingest.

---

## Do Not Touch

- `src/agent_hypervisor/hypervisor/mcp_gateway/` — data plane, stable
- `src/agent_hypervisor/runtime/` — canonical, do not break
- `tests/control_plane/test_control_plane.py` — encodes core invariants; only extend, don't weaken
