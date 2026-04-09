# World Authoring Console — Architecture Overview

**Agent Hypervisor v0.2.0+**  
**Status**: Phase 1 scaffolding complete (control plane domain model + services)

---

## What This Is

The **World Authoring Console** is the control plane for a live, session-bound Agent Hypervisor runtime. It is not an admin dashboard for viewing logs. It is a system for:

1. **Authorizing one-off actions** (end user: allow/deny one concrete action instance)
2. **Augmenting the live world** (operator: attach session-scoped overlays that temporarily widen or narrow capabilities)

These two operations are **architecturally distinct** and must not be collapsed.

---

## The Core Distinction

### Act Authorization (end user)
- Who: end user or human reviewer
- What: one concrete action instance, identified by fingerprint
- Effect: `allowed_once` or `denied` — no world mutation
- Scope: single approval record with TTL
- Invariant: **does not reveal hidden tools or widen capability classes**

### World Augmentation (operator)
- Who: admin / operator
- What: a session overlay attached to a live session
- Effect: modifies the local executable world for this session
- Scope: session-scoped, temporary, auditable
- Invariant: **base manifest is never mutated; only overlays are added/removed**

---

## Session Lifecycle

```
Session Created (background mode)
    ↓
Tool call arrives
    ↓
Manifest + overlay resolution → WorldStateView
    ↓
Enforcement (ToolCallEnforcer)
    ↓
[if verdict = ask] → ActionApproval created (pending)
    ↓
End user resolves approval → allowed_once or denied
    ↓
[operator attaches] → Session transitions to interactive mode
    ↓
Operator authors overlay → SessionOverlay attached
    ↓
WorldStateView recomputed (base manifest + active overlays)
    ↓
Session closed → overlays removed, audit log retained
```

---

## Modes

### Background Mode (default)
- No ASK path; undefined cases fail closed
- No operator authoring unless operator explicitly attaches
- Session state: `active` or `blocked`

### Interactive Mode
- Activated by operator attachment OR explicit mode transition
- Action approvals possible → session state transitions to `waiting_approval`
- Session overlay authoring possible
- Enforcement remains deterministic; mode does not weaken policy

---

## Architecture

```
Control Plane (this layer)
├── SessionStore          ← tracks all session state
├── EventStore            ← structured audit log per session
├── ApprovalService       ← one-off action authorization
├── OverlayService        ← session-scoped world augmentation
└── WorldStateResolver    ← computes visible world from base + overlays

Data Plane (existing MCP gateway)
├── ToolSurfaceRenderer   ← manifest → visible tools
├── ToolCallEnforcer      ← deterministic enforcement
└── SessionWorldResolver  ← session → manifest binding
```

The control plane **sits beside** the data plane. It does not replace enforcement.  
The `WorldStateResolver` produces a `WorldStateView` that the data plane uses to render tools and enforce calls.

---

## Invariants

1. No LLM in the enforcement path — ever.
2. Base manifest is never mutated during runtime authoring.
3. All runtime world changes are session-scoped overlays.
4. One-off approvals do NOT silently widen the world.
5. Operator world augmentation is explicit and auditable.
6. Unknown/undeclared capabilities still fail closed.
7. Control plane and data plane remain distinct layers.

---

## Implementation Location

```
src/agent_hypervisor/control_plane/
├── __init__.py
├── domain.py               # Session, ActionApproval, SessionOverlay, WorldStateView
├── session_store.py        # SessionStore (in-memory)
├── event_store.py          # EventStore (in-memory append-only)
├── approval_service.py     # ApprovalService (fingerprint-bound TTL approvals)
├── overlay_service.py      # OverlayService (session-scoped overlays)
└── world_state_resolver.py # WorldStateResolver (base manifest + overlays)

tests/control_plane/
├── __init__.py
└── test_control_plane.py   # invariant tests
```

---

## What Is Intentionally Not Implemented

- Durable base manifest mutation (future: manifest evolution)
- RBAC matrix for operator roles
- WebSocket live updates
- Full auth stack
- Persistent relational schema
- Visual workflow editors
- Analytics dashboards
- Enterprise tenancy

This is the **skeleton** — clean, inspectable, and resumable.

---

## Reference Docs

- `docs/implementation/CONTROL_PLANE_PLAN.md` — implementation phases and status
- `docs/implementation/IMPLEMENTATION_STATUS.md` — what is done per session
- `docs/implementation/ARCHITECTURAL_DECISIONS_LOG.md` — design decisions log
- `docs/implementation/HANDOFF_NOTE.md` — current session handoff
- `docs/implementation/control_plane_repo_audit.md` — Phase 0 audit findings
