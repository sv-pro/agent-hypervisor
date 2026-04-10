# Package: `control_plane`

**Source:** [`src/agent_hypervisor/control_plane/`](../../src/agent_hypervisor/control_plane/)

The `control_plane` package is the **World Authoring Console** backend — the operator-facing control layer that sits beside the MCP gateway data plane. It provides session lifecycle governance, action authorization, world augmentation, and a multi-scope approval system. Crucially, it never touches the enforcement pipeline: the data plane's deterministic checks remain unmodified.

Status: **Supported** (working and maintained; in-memory only — no disk persistence in current implementation).

---

## Purpose

The control plane separates two concerns that are often conflated:

| Concept | Actor | Effect |
|---------|-------|--------|
| **Act Authorization** (`ActionApproval`) | End user | Allow or deny one concrete action instance; no world mutation |
| **World Augmentation** (`SessionOverlay`) | Operator | Temporarily expand/restrict a session's visible world; base manifest is never mutated |

Neither mechanism weakens the enforcement pipeline. An approval that the data plane's policy engine would deny still requires the overlay or explicit allowance to succeed; the control plane surfaces these decisions to humans, it does not override them silently.

---

## Architecture

```
               ┌──────────────────────────────────────────────┐
               │           Control Plane (/control/*)          │
               │                                              │
               │  ControlPlaneState                           │
               │  ┌──────────────┐  ┌────────────────────┐   │
               │  │ SessionStore │  │    EventStore       │   │
               │  └──────────────┘  │  (append-only log)  │   │
               │  ┌──────────────┐  └────────────────────┘   │
               │  │ Approval     │  ┌────────────────────┐   │
               │  │ Service      │  │ ParticipantRegistry │   │
               │  └──────┬───────┘  └────────────────────┘   │
               │         │          ┌────────────────────┐   │
               │  ┌──────┴───────┐  │ ApprovalBroadcaster│   │
               │  │ OverlayServ. │  └────────────────────┘   │
               │  └──────────────┘  ┌────────────────────┐   │
               │  ┌──────────────┐  │ WorldStateResolver  │   │
               │  │              │  └────────────────────┘   │
               └──────────────────────────────────────────────┘
                          │  optional bridge
               ┌──────────▼───────────────────────────────────┐
               │         MCP Gateway (data plane)             │
               │  tools/call → ToolCallEnforcer               │
               │  ask verdict → ApprovalService               │
               │  active overlays → tools/list rendering       │
               └──────────────────────────────────────────────┘
```

---

## Public API

```python
from agent_hypervisor.control_plane import (
    # Domain types
    Session, SessionEvent, ActionApproval,
    SessionOverlay, OverlayChanges, WorldStateView,
    ScopedVerdict, ParticipantRegistration,
    # Domain functions
    compute_action_fingerprint,
    # Session state constants
    SESSION_MODE_BACKGROUND, SESSION_MODE_INTERACTIVE,
    SESSION_STATE_ACTIVE, SESSION_STATE_WAITING_APPROVAL,
    SESSION_STATE_BLOCKED, SESSION_STATE_CLOSED,
    # Approval status constants
    APPROVAL_STATUS_PENDING, APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED, APPROVAL_STATUS_EXPIRED,
    # Event type constants
    EVENT_TYPE_SESSION_CREATED, EVENT_TYPE_TOOL_CALL,
    EVENT_TYPE_APPROVAL_REQUESTED, EVENT_TYPE_APPROVAL_RESOLVED,
    EVENT_TYPE_OVERLAY_ATTACHED, EVENT_TYPE_OVERLAY_DETACHED,
    # Services
    SessionStore, EventStore, ApprovalService,
    OverlayService, WorldStateResolver,
    ParticipantRegistry,
    # Event factories
    make_session_created, make_tool_call,
    make_approval_requested, make_approval_resolved,
    make_overlay_attached, make_overlay_detached,
    # World state bridge
    world_state_to_manifest_dict,
    # API
    ControlPlaneState, create_control_plane_router,
    create_control_plane_app,
)
```

---

## Key Modules

| Module | Key Symbols | Description |
|--------|-------------|-------------|
| [`domain.py`](../../src/agent_hypervisor/control_plane/domain.py) | `Session`, `ActionApproval`, `SessionOverlay`, `OverlayChanges`, `WorldStateView`, `ScopedVerdict`, `ParticipantRegistration`, `compute_action_fingerprint` | All domain types and string-literal constants |
| [`session_store.py`](../../src/agent_hypervisor/control_plane/session_store.py) | `SessionStore` | In-memory session lifecycle store (create/transition/close) |
| [`event_store.py`](../../src/agent_hypervisor/control_plane/event_store.py) | `EventStore`, `make_*` factories | Append-only structured audit log |
| [`approval_service.py`](../../src/agent_hypervisor/control_plane/approval_service.py) | `ApprovalService` | Fingerprint-bound, TTL-governed action approval with multi-scope verdict processing |
| [`overlay_service.py`](../../src/agent_hypervisor/control_plane/overlay_service.py) | `OverlayService` | Session-scoped world augmentation overlays (attach/detach/expire) |
| [`world_state_resolver.py`](../../src/agent_hypervisor/control_plane/world_state_resolver.py) | `WorldStateResolver`, `world_state_to_manifest_dict` | Deterministic WorldStateView: base manifest + active overlays |
| [`participant_registry.py`](../../src/agent_hypervisor/control_plane/participant_registry.py) | `ParticipantRegistry` | Registry of SSE sessions eligible to vote on approval requests |
| [`approval_broadcaster.py`](../../src/agent_hypervisor/control_plane/approval_broadcaster.py) | `ApprovalBroadcaster` | Fan-out of approval events to participant SSE queues |
| [`api.py`](../../src/agent_hypervisor/control_plane/api.py) | `ControlPlaneState`, `create_control_plane_router`, `create_control_plane_app` | FastAPI router with 16 endpoints; injectable into the MCP gateway |

---

## Domain Model

### `Session`

A governed runtime session tracking one agent from creation through closure.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Immutable unique identifier |
| `manifest_id` | `str` | WorldManifest this session operates under |
| `mode` | `str` | `"background"` or `"interactive"` |
| `state` | `str` | `"active"` / `"waiting_approval"` / `"blocked"` / `"closed"` |
| `overlay_ids` | `list[str]` | Ordered list of attached overlay IDs |
| `principal` | `Optional[str]` | User/agent identity if known |

### `ActionApproval`

A one-off authorization request bound to a specific `(tool_name, arguments)` fingerprint. An approval does **not** reveal hidden tools or widen the session's capability world — it authorizes exactly one concrete action instance.

| Field | Type | Description |
|-------|------|-------------|
| `approval_id` | `str` | UUID |
| `action_fingerprint` | `str` | SHA-256 (truncated 16 chars) of `tool + args` |
| `status` | `str` | `pending` / `partially_resolved` / `resolved` / `allowed` / `denied` / `expired` |
| `expires_at` | `str` | ISO-8601; empty = no expiry |
| `scoped_verdicts` | `list[ScopedVerdict]` | Multi-scope verdict records (Phase 8) |

### `ScopedVerdict` (Phase 8)

A single verdict for one approval scope from one participant. Three scopes:

| Scope | Actor Role | Effect |
|-------|-----------|--------|
| `one_off` | user | Marks the fingerprint explicitly allowed; call can be retried |
| `session` | operator | Creates a `SessionOverlay` (reveal_tool) for the session |
| `world` | admin | Global allow/deny (stub — not yet implemented) |

### `SessionOverlay`

An operator-authored temporary world augmentation for one session. The base manifest is never mutated.

| Field | Type | Description |
|-------|------|-------------|
| `overlay_id` | `str` | UUID |
| `changes` | `OverlayChanges` | `reveal_tools`, `hide_tools`, `widen_scope`, `narrow_scope` |
| `ttl_seconds` | `Optional[int]` | `None` = no expiry |
| `detached_at` | `Optional[str]` | Set when explicitly detached |

### `WorldStateView`

A computed, point-in-time view of a session's executable world: base manifest + all active overlays. Always deterministic: same inputs → same view.

### `ParticipantRegistration`

A registered SSE session that can vote on approval requests. Role set maps to approval scopes (`user → one_off`, `operator → session`, `admin → world`).

---

## Services

### `SessionStore`

In-memory session lifecycle store. Operations: `create()`, `get()`, `transition_state()`, `set_mode()`, `close()`, `list_active()`.

### `EventStore`

Append-only structured audit log. Events are never deleted or mutated. Factory helpers (`make_session_created()`, `make_tool_call()`, `make_approval_requested()`, etc.) construct well-typed `SessionEvent` records.

### `ApprovalService`

Core service for one-off action authorization.

Key methods:

| Method | Description |
|--------|-------------|
| `request_approval(session_id, tool_name, arguments, ...)` | Create a pending approval (emits `approval_requested` event if `event_store` provided) |
| `respond(approval_id, verdicts, ...)` | Submit `ScopedVerdict` list; fires scope-specific side effects; idempotent per scope |
| `resolve(approval_id, decision, resolved_by, ...)` | Legacy single-decision resolution; fail-closed on expiry |
| `has_explicit_allow(session_id, tool_name, arguments)` | Strict check: `one_off` allow verdict or `status=allowed` — used by gateway pre-check |
| `is_action_approved(session_id, tool_name, arguments)` | Broader check: pending or allowed, non-expired |
| `check_expired()` | Sweep pending approvals past TTL → mark `expired` |

**Invariants:**
- Resolved approvals are retained for audit; never deleted.
- Expired approvals fail closed even if the operator's decision arrives late.
- `respond()` is idempotent per scope: a scope already recorded is skipped.

### `OverlayService`

Session-scoped world augmentation. `attach()` creates a `SessionOverlay` and records the overlay ID on the session. `detach()` marks it inactive. Expired overlays are silently skipped by the resolver.

### `WorldStateResolver`

Stateless resolver. `resolve(session_id, base_tools, base_constraints)` computes the `WorldStateView` by applying all active overlays in creation order (last-applied wins for conflicts). The `world_state_to_manifest_dict()` bridge converts a view to a dict suitable for loading as a `WorldManifest`.

### `ParticipantRegistry`

In-memory registry of SSE sessions eligible to vote. Keyed by `session_id`; re-registration replaces roles (upsert semantics).

### `ApprovalBroadcaster`

Fire-and-forget SSE fan-out.

- **`approval_requested`** → sent to ALL registered participants when an approval is created.
- **`approval_resolved`** → sent to the ORIGINATOR session when any scope returns `allow`.

Broadcasts are non-blocking (`put_nowait()`). Failures are logged and swallowed — the enforcement path must never crash due to a notification failure.

---

## HTTP API

Mounted at `/control/*` when `create_mcp_app()` receives a `ControlPlaneState`.

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/control/sessions` | Create session |
| `GET` | `/control/sessions` | List sessions (filter by `state`, `mode`) |
| `GET` | `/control/sessions/{id}` | Get session detail |
| `PATCH` | `/control/sessions/{id}/mode` | Set mode (`background`/`interactive`) |
| `DELETE` | `/control/sessions/{id}` | Close session |

### World State & Audit

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/control/sessions/{id}/world` | Get `WorldStateView` (live overlay composite) |
| `GET` | `/control/sessions/{id}/events` | Get session event log |

### Approvals

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/control/approvals` | List pending approvals (sweeps expired before return) |
| `GET` | `/control/approvals/{id}` | Get approval detail |
| `POST` | `/control/approvals/{id}/resolve` | Resolve (legacy single-decision) |
| `PATCH` | `/control/approvals/{id}/respond` | Submit `ScopedVerdict` list (Phase 8 multi-scope) |

### Overlays

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/control/sessions/{id}/overlays` | List session overlays |
| `POST` | `/control/sessions/{id}/overlays` | Attach overlay |
| `DELETE` | `/control/sessions/{id}/overlays/{ov_id}` | Detach overlay |

### Participants (Phase 8)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/control/participants` | Register participant with roles |
| `DELETE` | `/control/participants/{id}` | Unregister participant |
| `GET` | `/control/participants` | List registered participants |

---

## Gateway Integration

To attach the control plane to the MCP gateway:

```python
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
from agent_hypervisor.control_plane import ControlPlaneState

cp = ControlPlaneState.create()
app = create_mcp_app("manifests/example_world.yaml", control_plane=cp)
```

When a `control_plane` is provided to `create_mcp_app()`:

1. The `/control/*` router is mounted on the FastAPI app.
2. The `get_base_manifest` bridge is auto-configured to read from the gateway's `SessionWorldResolver`.
3. SSE connections opened via `GET /mcp/sse` are automatically registered with `SessionStore`.
4. `tools/call` responses with verdict `ask` from the policy engine are routed to `ApprovalService.request_approval()` (instead of failing closed).
5. `tools/list` uses `WorldStateResolver` when any active overlay exists for the session, so the visible tool surface reflects the current overlay state.
6. A pre-check `has_explicit_allow()` before routing `ask` verdicts means that an already-approved action (via `one_off` scope) bypasses the approval workflow and executes directly.

---

## Security Invariants

| Invariant | Where enforced |
|-----------|----------------|
| An approval does not reveal hidden tools | `ApprovalService`; only `SessionOverlay` with `reveal_tools` changes visibility |
| An approval applies only to the exact fingerprint | `compute_action_fingerprint(tool_name, args)` → deterministic SHA-256 hash |
| Expired approvals fail closed | `ApprovalService.respond()`, `resolve()`, `has_explicit_allow()` |
| Base manifest is never mutated | `OverlayService.attach()` creates new overlay; `WorldStateResolver` composites non-destructively |
| `respond()` is idempotent per scope | `existing_scopes` set check skips already-recorded scopes |
| Broadcast failures do not affect enforcement | `put_nowait()` + logged swallow in `ApprovalBroadcaster` |
| Overlay detachment is permanent | `detached_at` is set; `is_active()` returns False; never reversed |

---

## See Also

- [Package: hypervisor](hypervisor.md) — parent package; the data plane this control plane sits beside
- [AH MCP Gateway](modules/mcp_gateway.md) — gateway integration details; enforcement pipeline with `ask` routing
- [World Manifest](../concepts/world-manifest.md) — the manifest that base world state comes from
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md) — conceptual overview of the trust model
- [`WORLD_AUTHORING.md`](../../WORLD_AUTHORING.md) — architecture overview for the World Authoring Console
- [`docs/implementation/CONTROL_PLANE_PLAN.md`](../../docs/implementation/CONTROL_PLANE_PLAN.md) — phase-by-phase implementation plan
