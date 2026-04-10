# Handoff Note — Session 11

**Date**: 2026-04-10  
**Branch**: `claude/phase-8-multi-scope-approvals-irzP0`  
**Session**: Multi-Scope Approval System (Phase 8)

---

## What Was Done

Implemented the complete multi-scope approval system. A single approval request can
now receive verdicts at three scopes simultaneously (one_off / session / world), each
firing its own side effect immediately. The originating session receives an SSE
notification when any allow verdict arrives, enabling retry without polling.

### Files Modified

```
src/agent_hypervisor/control_plane/domain.py        ← ScopedVerdict, ParticipantRegistration, new constants
src/agent_hypervisor/control_plane/approval_service.py  ← respond(), has_explicit_allow()
src/agent_hypervisor/control_plane/api.py            ← participant endpoints, PATCH /respond, ControlPlaneState
src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py  ← broadcaster wiring, pre-check
```

### Files Created

```
src/agent_hypervisor/control_plane/participant_registry.py   ← ParticipantRegistry
src/agent_hypervisor/control_plane/approval_broadcaster.py   ← ApprovalBroadcaster
tests/control_plane/test_phase8.py                           ← 52 new tests, all passing
```

---

## Changes in Detail

### domain.py

- Added `APPROVAL_SCOPE_ONE_OFF`, `APPROVAL_SCOPE_SESSION`, `APPROVAL_SCOPE_WORLD` constants
- Added `APPROVAL_STATUS_PARTIALLY_RESOLVED`, `APPROVAL_STATUS_RESOLVED` constants
- Added `ScopedVerdict` dataclass: `{scope, verdict, participant_id, timestamp}`
- Added `ParticipantRegistration` dataclass: `{participant_id, session_id, roles, registered_at}`
- Extended `ActionApproval` with `scoped_verdicts: list[ScopedVerdict]` (default empty)
- Updated `ActionApproval.to_dict()` to include `scoped_verdicts`

### participant_registry.py (new)

- `ParticipantRegistry` — in-memory registry keyed by session_id (SSE session)
- `register(session_id, roles)` → ParticipantRegistration (upsert semantics)
- `unregister(session_id)` → bool
- `get(session_id)` → Optional[ParticipantRegistration]
- `list_all()` → list sorted by registered_at

### approval_broadcaster.py (new)

- `ApprovalBroadcaster` — fan-out to SSE queues via `put_nowait()` (sync-safe)
- `set_sse_store(sse_store)` — wired by `create_mcp_app()` after sse_store creation
- `broadcast_approval_requested(approval, participant_registry)` → int (count notified)
- `notify_originator(session_id, approval, effective_verdict)` → bool
- Fail-open: all queue write failures are logged and swallowed

### approval_service.py

- Added `respond(approval_id, verdicts, overlay_service, session_store, event_store)`:
  - Idempotent per scope (first verdict wins)
  - one_off allow → recorded; `has_explicit_allow()` returns True for retry
  - session allow → creates `SessionOverlay(reveal_tools=[tool_name])`
  - world allow → stub no-op
  - Expired approval → marks expired, applies no verdicts
  - Status: `pending` → `partially_resolved` (first verdict) → `resolved` (all 3 scopes)
  - Raises `RuntimeError` if called on terminal state (resolved/expired/etc.)
- Added `has_explicit_allow(session_id, tool_name, args)`:
  - Returns True if status=ALLOWED (old resolve() path) OR one_off allow scoped verdict
  - Used by gateway pre-check to determine if retry should skip approval workflow
- Updated `check_expired()` to sweep `partially_resolved` approvals too
- Preserved `is_action_approved()` (checks PENDING + ALLOWED, backward compat)

### api.py

- Added `participant_registry: ParticipantRegistry` and `broadcaster: ApprovalBroadcaster`
  to `ControlPlaneState` (with defaults via `field(default_factory=...)`)
- Updated `ControlPlaneState.create()` to initialize both
- Added Pydantic models: `RegisterParticipantRequest`, `ScopedVerdictItem`, `RespondToApprovalRequest`
- Added endpoints:
  - `POST /control/participants` — register session + roles (upsert)
  - `DELETE /control/participants/{session_id}` — unregister
  - `GET /control/participants` — list all
  - `PATCH /control/approvals/{id}/respond` — submit scoped verdicts; notifies originator on first allow
- Kept `POST /control/approvals/{id}/resolve` unchanged (backwards compat)
- Added `_has_allow_verdict()` internal helper

### mcp_server.py

- After mounting control plane router, calls `control_plane.broadcaster.set_sse_store(sse_store)`
  to wire the broadcaster to the SSE queue registry
- In `_handle_tools_call()` for `decision.asked`:
  - Pre-check `has_explicit_allow()` — if True, skip approval workflow and proceed to dispatch
  - If False, create approval, broadcast to all registered participants (`broadcast_approval_requested()`),
    return `pending_approval` to caller
  - Broadcaster failures are caught and swallowed (fail-open)

---

## Current Test Count

```
pytest tests/control_plane/test_control_plane.py  →  57 passed
pytest tests/control_plane/test_api.py            →  44 passed
pytest tests/control_plane/test_phase8.py         →  52 passed
pytest tests/hypervisor/test_gateway_wiring.py    →  23 passed
Total: 176 passed, 0 failed
```

Note: `tests/hypervisor/test_mcp_gateway.py` still has 21 pre-existing failures
(missing pytest-asyncio). Not caused by Phase 8 changes.

---

## Architecture (Final State — Phase 8)

```
HTTP Client (participant / operator)
        ↓
POST /control/participants  ←  register session_id + roles
PATCH /control/approvals/{id}/respond  ←  submit scoped verdicts

Approval Request Flow:
  MCP tool call → verdict=ask → ApprovalService.request_approval()
        ↓ broadcast_approval_requested()
  ApprovalBroadcaster → SSE queues of all registered participants
        ↓ (participants respond via PATCH /respond)
  ApprovalService.respond()
    one_off allow → has_explicit_allow() returns True on retry
    session allow → SessionOverlay created (reveal_tool)
    world allow   → stub no-op
        ↓ notify_originator()
  ApprovalBroadcaster → SSE queue of originating session
        ↓ (originator retries tool call)
  _handle_tools_call() → has_explicit_allow() → True → dispatch
```

---

## Key Invariants Preserved

1. No LLM in enforcement path ✅
2. Base manifest never mutated at runtime ✅
3. All runtime world changes are session-scoped overlays ✅
4. One-off approvals do not widen the world (one_off allow ≠ overlay) ✅
5. Operator augmentation is explicit and auditable ✅
6. Unknown capabilities still fail closed ✅
7. Control plane ≠ data plane ✅
8. "ask" without control plane still fails closed ✅
9. Broadcaster failures never crash the enforcement path (fail-open) ✅
10. Expired approvals always deny, even if scoped_verdicts contain allow ✅

---

## What Remains

1. **Persistent storage** — all stores are in-memory.
2. **Auth layer** — control plane endpoints have no auth.
3. **RBAC enforcement** — roles in ParticipantRegistration are informational; the
   endpoint does not verify that the participant actually holds the role they claim.
4. **World-scope allow implementation** — currently a stub no-op.
5. **WebSocket live updates** — operators must poll for overlay changes.

---

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
