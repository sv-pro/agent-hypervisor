# Control Plane Implementation Plan

**Project**: Agent Hypervisor — World Authoring Console  
**Version**: 0.2.0+  
**Started**: 2026-04-09  
**Branch**: `claude/control-plane-scaffolding-ugZhz`

---

## Purpose

This document tracks the implementation of the **World Authoring Control Plane** — the backend scaffolding for session-bound world authoring that sits beside the existing MCP gateway enforcement layer.

This is NOT a log viewer or admin dashboard.  
This is a **world authoring system** that makes the agent's runtime world explicit, inspectable, and temporarily mutable by authorized operators.

---

## Architecture Overview

```
Control Plane (new)                    Data Plane (existing MCP gateway)
─────────────────────────────────      ─────────────────────────────────
SessionStore                           ToolSurfaceRenderer
EventStore          ←→  bridges  →     ToolCallEnforcer
ApprovalService                        SessionWorldResolver
OverlayService
WorldStateResolver
```

The control plane **informs** the data plane but does not replace it. `WorldStateResolver` produces a `WorldStateView` that can feed into `SessionWorldResolver` and `ToolSurfaceRenderer`.

---

## The Two Core Concepts

### 1. Act Authorization (one-off approval)
- Actor: end user / human reviewer
- Effect: allow or deny **one concrete action instance**
- No world mutation — hidden tools remain hidden
- Bound to action fingerprint (deterministic hash of tool + args)
- Has TTL; expired approvals are invalid

### 2. World Augmentation (session overlay)
- Actor: operator / admin
- Effect: temporary session-scoped augmentation of the executable world
- Base manifest never mutated
- Overlay can: reveal_tool, hide_tool, widen_scope, narrow_scope
- Explicit, inspectable, removable

---

## Phases

### Phase 0 — Audit and Insertion Points ✅
- Identify runtime/gateway/policy boundaries
- Identify where session state, approval state, overlay resolution should live
- Create `docs/implementation/control_plane_repo_audit.md`

### Phase 1 — Domain Model and Services ✅
Files created:
- `src/agent_hypervisor/control_plane/__init__.py`
- `src/agent_hypervisor/control_plane/domain.py`
- `src/agent_hypervisor/control_plane/session_store.py`
- `src/agent_hypervisor/control_plane/event_store.py`
- `src/agent_hypervisor/control_plane/approval_service.py`
- `src/agent_hypervisor/control_plane/overlay_service.py`
- `src/agent_hypervisor/control_plane/world_state_resolver.py`

### Phase 2 — Action Approval Path ✅
- Domain objects (ActionApproval, ApprovalStatus)
- Fingerprint computation (deterministic hash)
- Service methods: request_approval, resolve_approval, check validity
- Tests: approval applies only to fingerprint, does not mutate world

### Phase 3 — Session Overlay Path ✅
- Domain objects (SessionOverlay, OverlayChanges)
- Overlay application logic
- Overlay attachment / detachment
- Tests: overlay reveals hidden tool, detachment restores state, base manifest unchanged

### Phase 4 — World State Resolution ✅
- `WorldStateResolver.resolve(session_id, base_manifest)` → `WorldStateView`
- Deterministic: same inputs → same output
- Computes visible_tools, active_constraints, active_overlay_ids, mode
- Tests: resolver is deterministic, expired overlays excluded

### Phase 5 — Control Plane API Surface ✅
- `src/agent_hypervisor/control_plane/api.py` — ControlPlaneState, router factory, standalone app
- 13 endpoints under `/control/*` prefix
- 44 tests in `tests/control_plane/test_api.py`

### Phase 6 — Demo Path and Docs ✅
- `docs/implementation/control_plane_demo.md` — 8-step curl walkthrough
- Covers: session creation → approval → operator attach → overlay → world state → detach → audit

### Phase 7 — Gateway Wiring ✅
Files modified:
- `src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py`
  - Added `EnforcementDecision.asked` property
  - Policy "ask" verdicts now return real `verdict="ask"` (previously collapsed to deny)
- `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py`
  - `MCPGatewayState` optionally holds `ControlPlaneState`
  - `create_mcp_app()` mounts `/control/*` router when control plane provided
  - SSE sessions auto-registered with `SessionStore`
  - `_handle_tools_list()` uses `WorldStateResolver` when overlays are active
  - `_handle_tools_call()` routes `ask` verdicts to `ApprovalService`

Files created:
- `tests/hypervisor/test_gateway_wiring.py` — 23 integration tests

### Phase 8 — Multi-Scope Approval System ✅
**Branch**: `claude/phase-8-multi-scope-approvals-irzP0`

Files modified:
- `src/agent_hypervisor/control_plane/domain.py`
  - Added `APPROVAL_SCOPE_ONE_OFF / SESSION / WORLD` constants
  - Added `APPROVAL_STATUS_PARTIALLY_RESOLVED / RESOLVED` constants
  - Added `ScopedVerdict` dataclass: `{scope, verdict, participant_id, timestamp}`
  - Added `ParticipantRegistration` dataclass: `{participant_id, session_id, roles}`
  - Extended `ActionApproval` with `scoped_verdicts: list[ScopedVerdict]`
- `src/agent_hypervisor/control_plane/approval_service.py`
  - Added `respond()`: scoped verdict processing with idempotency and side effects
  - Added `has_explicit_allow()`: stricter check for gateway pre-check
  - Updated `check_expired()` to sweep `partially_resolved` approvals
- `src/agent_hypervisor/control_plane/api.py`
  - `ControlPlaneState` now includes `participant_registry` and `broadcaster` fields
  - New endpoints: `POST/DELETE/GET /control/participants`, `PATCH /control/approvals/{id}/respond`
  - `POST /control/approvals/{id}/resolve` retained for backwards compat
- `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py`
  - `create_mcp_app()` wires `broadcaster.set_sse_store(sse_store)` when CP present
  - `_handle_tools_call()` pre-checks `has_explicit_allow()` before approval workflow
  - Broadcasts `approval_requested` to participants on new approval creation

Files created:
- `src/agent_hypervisor/control_plane/participant_registry.py` — ParticipantRegistry
- `src/agent_hypervisor/control_plane/approval_broadcaster.py` — ApprovalBroadcaster
- `tests/control_plane/test_phase8.py` — 52 new tests

**Test totals**: 176 passing across all control plane + gateway wiring suites.

---

## Non-Goals (this phase)

- Polished frontend
- WebSocket live updates
- RBAC matrix for roles
- Full auth stack
- Persistent relational schema migrations
- Visual workflow editors
- Analytics dashboards
- Enterprise tenancy

---

## Key Invariants

1. No LLM in enforcement path
2. Base manifest never mutated at runtime
3. All runtime world changes are session-scoped overlays
4. One-off approvals do not widen the world
5. Operator augmentation is explicit and auditable
6. Unknown capabilities still fail closed
7. Control plane ≠ data plane

---

## Module Location

```
src/agent_hypervisor/control_plane/
tests/control_plane/
docs/implementation/  (this file + audit + handoff)
WORLD_AUTHORING.md    (project root — architecture overview)
```
