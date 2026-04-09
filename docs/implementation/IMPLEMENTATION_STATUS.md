# Implementation Status

**Last updated**: 2026-04-09  
**Session**: Session 9 — Control Plane API + Demo (Phases 5–6)  
**Branch**: `claude/control-plane-scaffolding-ugZhz`

---

## Session Summary

Session 8: Introduced the World Authoring Control Plane scaffolding — the backend layer for session-bound world authoring. 57 new tests, all passing.

---

## Completed

### Phase 0 — Repository Audit (MCP Gateway, Sessions 1–7)
- [x] Audited all existing relevant files
- [x] Identified gaps (no MCP protocol, no manifest-driven tool list)
- [x] Identified insertion point: `hypervisor/mcp_gateway/` (additive)
- [x] Created `docs/implementation/repo_audit_mcp_gateway.md`

### Phase 1 — Architecture Skeleton (MCP Gateway)
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/__init__.py`
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/protocol.py` — JSON-RPC 2.0 models
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/tool_surface_renderer.py`
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py`
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/session_world_resolver.py`
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py`

### Phase 2 — tools/list Virtualization
- [x] `ToolSurfaceRenderer.render()` returns only manifest-declared tools
- [x] Undeclared tools are absent (not filtered post-hoc — absent from response)
- [x] Order follows manifest declaration order (deterministic)
- [x] `manifests/example_world.yaml` created (email assistant world)
- [x] `manifests/read_only_world.yaml` created (minimal demo world)

### Phase 3 — tools/call Deterministic Enforcement
- [x] `ToolCallEnforcer.enforce()` checks manifest first, then registry, then policy, then constraints
- [x] Undeclared tool → `manifest:tool_not_declared` → deny
- [x] No adapter → `registry:no_adapter` → deny
- [x] Constraint violation → `manifest:constraint_violated` → deny
- [x] All decisions deterministic (same input → same output)
- [x] `enforce()` never raises

### Phase 4 — Manifest Binding
- [x] `SessionWorldResolver` loads manifest from YAML at startup
- [x] Single static manifest per gateway instance
- [x] `resolve(session_id, context)` signature ready for per-session evolution
- [x] `reload()` method for hot-reload (retains old manifest on failure)
- [x] Gateway startup fails (not fails open) if manifest cannot be loaded

### Phase 5 — Provenance / Taint Hooks
- [x] `InvocationProvenance` dataclass captures source, session_id, trust_level, timestamp
- [x] `_extract_provenance()` reads from request headers and `_meta` params
- [x] Provenance attached to every `EnforcementDecision`
- [x] `trust_level` wired to `TaintContext` — taint propagated through full enforcement pipeline

### Phase 7 — Taint Propagation
- [x] `_taint_context_from_provenance()` — `"trusted"` → CLEAN, all other trust levels → TAINTED
- [x] `EnforcementDecision.taint_context: TaintContext` — always set
- [x] `mcp_server.py` — tool results wrapped in `TaintedValue`, taint state emitted as `"_taint"` field
- [x] 20 taint propagation tests in `tests/hypervisor/test_taint_propagation.py`

### Phase 6 — Docs, Tests, Demo (MCP Gateway)
- [x] 83 tests (Sessions 1–7): all passing when environment has `agent_hypervisor` installed

---

## Session 8 — Control Plane Scaffolding (NEW)

### Phase 0 — Control Plane Repo Audit ✅
- [x] Identified runtime/gateway/policy insertion points
- [x] Identified where session state, approval state, overlay resolution should live
- [x] Created `docs/implementation/control_plane_repo_audit.md`
- [x] Created `WORLD_AUTHORING.md` (project root — architecture overview)
- [x] Created `docs/implementation/CONTROL_PLANE_PLAN.md`

### Phase 1 — Domain Model and Services ✅
- [x] `src/agent_hypervisor/control_plane/__init__.py` — clean public API
- [x] `src/agent_hypervisor/control_plane/domain.py` — Session, SessionEvent, ActionApproval, SessionOverlay, OverlayChanges, WorldStateView, compute_action_fingerprint
- [x] `src/agent_hypervisor/control_plane/session_store.py` — SessionStore (in-memory lifecycle)
- [x] `src/agent_hypervisor/control_plane/event_store.py` — EventStore (append-only audit log + factory helpers)
- [x] `src/agent_hypervisor/control_plane/approval_service.py` — ApprovalService (fingerprint-bound TTL approvals)
- [x] `src/agent_hypervisor/control_plane/overlay_service.py` — OverlayService (session-scoped world augmentation)
- [x] `src/agent_hypervisor/control_plane/world_state_resolver.py` — WorldStateResolver + world_state_to_manifest_dict bridge

### Phase 2 — Action Approval Path ✅
Implemented as part of ApprovalService:
- [x] ActionApproval domain object with fingerprint, TTL, status machine
- [x] Fingerprint = SHA-256[:16] of JSON-sorted (tool_name + arguments)
- [x] request_approval() / resolve() / is_action_approved() / check_expired()
- [x] Expired approvals fail closed (resolved as denied if expired at resolve time)
- [x] Approval does NOT mutate visible tool world — tested explicitly

### Phase 3 — Session Overlay Path ✅
Implemented as part of OverlayService + WorldStateResolver:
- [x] SessionOverlay with OverlayChanges (reveal_tools, hide_tools, widen_scope, narrow_scope)
- [x] attach() / detach() / get_active_overlays() / check_expired()
- [x] Session-scoped: overlays of one session don't affect others
- [x] Detached/expired overlays excluded from active set

### Phase 4 — World State Resolution ✅
Implemented as WorldStateResolver:
- [x] resolve(session_id, base_tools, base_constraints) → WorldStateView
- [x] Deterministic: same inputs → same output
- [x] Overlays applied in creation order (oldest first)
- [x] narrow_scope wins over widen_scope for the same tool
- [x] resolve_from_manifest() convenience method for WorldManifest objects
- [x] world_state_to_manifest_dict() bridge (WorldStateView → manifest dict for SessionWorldResolver)

### Tests ✅
- [x] `tests/control_plane/__init__.py`
- [x] `tests/control_plane/conftest.py`
- [x] `tests/control_plane/test_control_plane.py` — 57 tests, all passing
  - Group 1: Domain (6 tests)
  - Group 2: SessionStore (11 tests)
  - Group 3: EventStore (6 tests)
  - Group 4: ApprovalService (13 tests)
  - Group 5: OverlayService (9 tests)
  - Group 6: WorldStateResolver (10 tests)
  - Group 7: Integration (3 tests)

### pyproject.toml change
- [x] Added `src` to `pythonpath` alongside existing `src/agent_hypervisor`
  - Reason: makes `agent_hypervisor` package importable as `from agent_hypervisor.xxx import ...`
  - This enables top-level test imports (vs deferred imports in existing test files)
  - Backwards compatible: `src/agent_hypervisor` still present; existing direct imports unaffected

---

## Session 9 — Control Plane API + Demo (NEW)

### Phase 5 — Control Plane API Surface ✅
- [x] `src/agent_hypervisor/control_plane/api.py` — FastAPI router + standalone app factory
- [x] `ControlPlaneState` dataclass holding all services; optional `get_base_manifest` callback
- [x] `create_control_plane_router(state)` — returns mounted APIRouter
- [x] `create_control_plane_app(...)` — returns standalone FastAPI app

Endpoints implemented:
- `POST /control/sessions` — create session (+ emits session_created event)
- `GET  /control/sessions` — list sessions (filter by state/mode)
- `GET  /control/sessions/{id}` — get session detail
- `PATCH /control/sessions/{id}/mode` — change mode (+ emits mode_changed event)
- `DELETE /control/sessions/{id}` — close session (+ emits session_closed event)
- `GET  /control/sessions/{id}/world` — resolved WorldStateView (base + overlays)
- `GET  /control/sessions/{id}/events` — structured audit log (filterable by type)
- `GET  /control/approvals` — list pending approvals (+ sweep expired; filter by session)
- `GET  /control/approvals/{id}` — get approval detail
- `POST /control/approvals/{id}/resolve` — resolve approval (allowed|denied)
- `GET  /control/sessions/{id}/overlays` — list overlays (active_only default)
- `POST /control/sessions/{id}/overlays` — attach overlay (+ emits overlay_attached)
- `DELETE /control/sessions/{id}/overlays/{oid}` — detach overlay (+ emits overlay_detached)
- `GET  /health` — service health check

### Phase 6 — Demo and Docs ✅
- [x] `docs/implementation/control_plane_demo.md` — 8-step walkthrough with curl examples
  - Step 1: session created (background)
  - Step 2: approval requested
  - Step 3: operator resolves once
  - Step 4: operator attaches (interactive)
  - Step 5: overlay attached
  - Step 6: world state inspected (write_file visible)
  - Step 7: overlay detached (world reverts)
  - Step 8: audit log viewed

### Tests ✅
- [x] `tests/control_plane/test_api.py` — 44 tests, all passing
  - Group 1: Health (1 test)
  - Group 2: Sessions (15 tests)
  - Group 3: World state (5 tests)
  - Group 4: Approvals (10 tests)
  - Group 5: Overlays (10 tests)
  - Group 6: Event log (3 tests)
  - Group 7: Integration (1 test — full 8-step scenario)

---

## Test Results

```
101 passed (control_plane/test_control_plane.py: 57 + test_api.py: 44)
```

Previous MCP gateway tests (83) require `pip install -e .` to run.

---

## Pending (next session)

### Gateway Wiring ⬜
Wire control plane into the MCP gateway enforcement loop:
1. When `ToolCallEnforcer.enforce()` returns verdict=`ask`, call `ApprovalService.request_approval()`
2. Return `{"status": "pending", "approval_id": "..."}` to MCP client
3. When operator resolves via `POST /control/approvals/{id}/resolve`, resume the blocked call
4. In `_handle_tools_list()`, use `WorldStateResolver.resolve()` to feed overlay-aware manifest

### MCP Gateway Mount ⬜
Add to `mcp_server.py` (or a wrapper):
```python
cp_state = ControlPlaneState.create(get_base_manifest=lambda sid: (
    gateway_state.resolver.resolve(sid).tool_names(), {}
))
app.include_router(create_control_plane_router(cp_state))
```

---

## What Must NOT Be Rewritten

- MCP gateway enforcement pipeline (`ToolCallEnforcer`, `ToolSurfaceRenderer`, `SessionWorldResolver`)
- All 101 control plane tests — they encode the core invariants
- `domain.py` types are stable — the public API for control plane consumers
- `api.py` endpoint contracts — tests and demo depend on them
