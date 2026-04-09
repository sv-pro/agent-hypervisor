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

### Phase 5 — Control Plane API Surface ⬜
- FastAPI router: `/control_plane/sessions`, `/control_plane/approvals`, etc.
- Mount on existing MCP gateway or standalone app
- Deferred: implement when UI or integration needs it

### Phase 6 — Demo Path and Docs ⬜
- `docs/implementation/control_plane_demo.md`
- Walkthrough: session starts → approval requested → operator attaches → overlay attached → world state inspected

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
