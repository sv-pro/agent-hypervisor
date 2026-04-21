"""
domain.py — Control plane domain model for the World Authoring Console.

This module defines the core data types for the Agent Hypervisor control plane.
These types are distinct from the data plane (MCP gateway) and represent
the operator/user-facing concepts of session governance.

Two fundamental concepts:

1. Act Authorization (ActionApproval)
   - Actor: end user
   - Effect: allow or deny one concrete action instance
   - No world mutation; hidden tools remain hidden
   - Bound to action fingerprint (deterministic hash of tool + args)
   - Governed by TTL

2. World Augmentation (SessionOverlay)
   - Actor: operator
   - Effect: temporary session-scoped augmentation of the executable world
   - Base manifest is NEVER mutated
   - Overlay can reveal/hide tools and widen/narrow scope
   - Explicit, inspectable, and removable

Both are session-scoped. Neither replaces nor weakens the enforcement pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations (string literals — no enum class; matches existing style)
# ---------------------------------------------------------------------------

# Session state machine
SESSION_STATE_ACTIVE = "active"
SESSION_STATE_WAITING_APPROVAL = "waiting_approval"
SESSION_STATE_BLOCKED = "blocked"
SESSION_STATE_CLOSED = "closed"

# Session mode
SESSION_MODE_BACKGROUND = "background"
SESSION_MODE_INTERACTIVE = "interactive"

# Approval status
APPROVAL_STATUS_PENDING = "pending"
APPROVAL_STATUS_ALLOWED = "allowed"
APPROVAL_STATUS_DENIED = "denied"
APPROVAL_STATUS_EXPIRED = "expired"
APPROVAL_STATUS_PARTIALLY_RESOLVED = "partially_resolved"
APPROVAL_STATUS_RESOLVED = "resolved"

# Approval scopes (multi-scope approval system)
APPROVAL_SCOPE_ONE_OFF = "one_off"    # user role: allow/deny this fingerprint once (TTL-bound)
APPROVAL_SCOPE_SESSION = "session"    # operator role: allow/deny for this session (SessionOverlay)
APPROVAL_SCOPE_WORLD = "world"        # admin role: allow/deny globally (stub)


# ---------------------------------------------------------------------------
# ScopedVerdict
# ---------------------------------------------------------------------------

@dataclass
class ScopedVerdict:
    """
    A single verdict for one approval scope from one participant.

    Scopes:
    - one_off:  User role — allow/deny this exact fingerprint once (TTL-bound).
                Side effect: marks the ActionApproval as fingerprint-approved.
    - session:  Operator role — allow/deny for the lifetime of this session.
                Side effect: creates a SessionOverlay (reveal_tool) on allow.
    - world:    Admin role — allow/deny globally.
                Side effect: stub (no-op) for now.

    Invariants:
    - scope must be one of APPROVAL_SCOPE_*.
    - verdict must be "allow" or "deny".
    - timestamp is set at creation time (immutable after creation).
    """

    scope: str                   # one_off | session | world
    verdict: str                 # allow | deny
    participant_id: str = ""     # identity of the participant making this decision
    timestamp: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "verdict": self.verdict,
            "participant_id": self.participant_id,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# ParticipantRegistration
# ---------------------------------------------------------------------------

@dataclass
class ParticipantRegistration:
    """
    A registered participant that can respond to approval requests.

    A participant holds a set of roles which map to approval scopes:
      user     → one_off scope
      operator → session scope
      admin    → world scope

    A single participant may hold multiple roles simultaneously and can
    respond with verdicts for all applicable scopes in one PATCH request.

    Invariants:
    - participant_id is the session_id of the participant's SSE connection.
    - roles is a set; duplicates are ignored.
    - Registered participants receive "approval_requested" SSE events.
    """

    participant_id: str          # SSE session_id used to route events
    session_id: str              # same as participant_id (SSE session)
    roles: set                   # {"user", "operator", "admin"} — any subset
    registered_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict:
        return {
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "roles": sorted(self.roles),
            "registered_at": self.registered_at,
        }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """
    A governed runtime session.

    Tracks the lifecycle of a single agent session from creation through
    closure. Sessions start in background mode and can transition to
    interactive mode when an operator attaches.

    Invariants:
    - session_id is immutable after creation.
    - mode transitions are explicit (background → interactive only; never auto).
    - overlay_ids is an ordered list; last-applied overlay takes precedence
      when there are conflicts.
    """

    session_id: str
    manifest_id: str
    mode: str = SESSION_MODE_BACKGROUND          # "background" | "interactive"
    state: str = SESSION_STATE_ACTIVE            # "active" | "waiting_approval" | "blocked" | "closed"
    overlay_ids: list[str] = field(default_factory=list)
    principal: Optional[str] = None              # user/agent identity if known
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "manifest_id": self.manifest_id,
            "mode": self.mode,
            "state": self.state,
            "overlay_ids": list(self.overlay_ids),
            "principal": self.principal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# SessionEvent
# ---------------------------------------------------------------------------

@dataclass
class SessionEvent:
    """
    A structured event in a session's audit log.

    Events are append-only. No event is ever deleted or mutated.
    The event log provides a complete, ordered history of what happened
    in a session, including decisions and rule matches.
    """

    event_id: str
    session_id: str
    timestamp: str
    type: str                           # see EVENT_TYPE_* constants below
    payload: dict[str, Any] = field(default_factory=dict)
    decision: Optional[str] = None      # "allow" | "deny" | "pending" (if applicable)
    rule_hit: Optional[str] = None      # matched_rule identifier (if applicable)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "payload": self.payload,
            "decision": self.decision,
            "rule_hit": self.rule_hit,
        }


# Event type constants
EVENT_TYPE_SESSION_CREATED = "session_created"
EVENT_TYPE_SESSION_CLOSED = "session_closed"
EVENT_TYPE_MODE_CHANGED = "mode_changed"
EVENT_TYPE_TOOL_CALL = "tool_call"
EVENT_TYPE_APPROVAL_REQUESTED = "approval_requested"
EVENT_TYPE_APPROVAL_RESOLVED = "approval_resolved"
EVENT_TYPE_OVERLAY_ATTACHED = "overlay_attached"
EVENT_TYPE_OVERLAY_DETACHED = "overlay_detached"
EVENT_TYPE_PROFILE_SWITCHED = "profile_switched"  # Phase 4: taint-triggered profile change


# ---------------------------------------------------------------------------
# ActionApproval
# ---------------------------------------------------------------------------

@dataclass
class ActionApproval:
    """
    A one-off action authorization request.

    Represents a single end-user decision about one concrete action instance.
    The decision is bound to the action_fingerprint — a deterministic hash of
    (tool_name, arguments). It does NOT apply to the session generally or to
    other tool calls.

    Invariants:
    - An approval does NOT reveal hidden tools or widen capability classes.
    - An approval applies ONLY to the exact action_fingerprint.
    - An expired approval (now > expires_at) is treated as invalid (denied).
    - resolved_at and resolved_by are set only when status transitions out of pending.
    """

    approval_id: str
    session_id: str
    action_fingerprint: str             # deterministic hash of tool_name + args
    tool_name: str                      # human-readable tool name (for UI)
    arguments_summary: dict[str, Any]   # human-readable args snapshot (for UI)
    requested_by: str                   # who triggered the request (agent/system)
    status: str = APPROVAL_STATUS_PENDING
    expires_at: str = ""                # ISO-8601; empty = no expiry (use with caution)
    rationale: Optional[str] = None     # human-readable reason for the request
    created_at: str = field(default_factory=lambda: _now())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    scoped_verdicts: list = field(default_factory=list)  # list[ScopedVerdict]

    def is_expired(self) -> bool:
        """Return True if this approval has passed its expiry time."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except ValueError:
            return True  # malformed expiry → treat as expired (fail closed)

    def is_valid(self) -> bool:
        """Return True if this approval is still pending and not expired."""
        return self.status == APPROVAL_STATUS_PENDING and not self.is_expired()

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "action_fingerprint": self.action_fingerprint,
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "requested_by": self.requested_by,
            "status": self.status,
            "expires_at": self.expires_at,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "scoped_verdicts": [sv.to_dict() for sv in self.scoped_verdicts],
        }


# ---------------------------------------------------------------------------
# SessionOverlay
# ---------------------------------------------------------------------------

@dataclass
class OverlayChanges:
    """
    The mutations a SessionOverlay applies to the base manifest's world.

    - reveal_tools: tool names to add to the visible world (must not exist in base manifest)
    - hide_tools: tool names to remove from the visible world (must exist in base manifest)
    - widen_scope: per-tool constraints to relax (dict of tool_name → constraint_delta)
    - narrow_scope: per-tool constraints to tighten (dict of tool_name → constraint_delta)
    - additional_constraints: arbitrary key/value constraints (for future extensions)

    Semantics:
    - reveal_tools and hide_tools are evaluated first.
    - narrow_scope takes precedence over widen_scope if both affect the same tool.
    - An overlay with empty changes is valid but has no effect.
    """

    reveal_tools: list[str] = field(default_factory=list)
    hide_tools: list[str] = field(default_factory=list)
    widen_scope: dict[str, Any] = field(default_factory=dict)
    narrow_scope: dict[str, Any] = field(default_factory=dict)
    additional_constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "reveal_tools": list(self.reveal_tools),
            "hide_tools": list(self.hide_tools),
            "widen_scope": dict(self.widen_scope),
            "narrow_scope": dict(self.narrow_scope),
            "additional_constraints": dict(self.additional_constraints),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OverlayChanges":
        return cls(
            reveal_tools=list(data.get("reveal_tools", [])),
            hide_tools=list(data.get("hide_tools", [])),
            widen_scope=dict(data.get("widen_scope", {})),
            narrow_scope=dict(data.get("narrow_scope", {})),
            additional_constraints=dict(data.get("additional_constraints", {})),
        )


@dataclass
class SessionOverlay:
    """
    An operator-authored temporary world augmentation for one session.

    Overlays attach to a session, not to the base manifest. The base manifest
    is never mutated. Overlays can be attached and detached without affecting
    other sessions or the default world.

    Invariants:
    - overlay_id is immutable after creation.
    - parent_manifest_id records the base manifest at time of creation.
    - Overlays are session-scoped: removed when the session closes.
    - An expired overlay (now > expires_at) is treated as inactive.
    - Detaching an overlay is permanent for that overlay instance.
    """

    overlay_id: str
    session_id: str
    parent_manifest_id: str             # manifest this overlay is based on
    created_by: str                     # operator identity
    changes: OverlayChanges = field(default_factory=OverlayChanges)
    ttl_seconds: Optional[int] = None   # None = no expiry
    expires_at: Optional[str] = None    # computed from ttl_seconds at creation
    created_at: str = field(default_factory=lambda: _now())
    detached_at: Optional[str] = None   # set when overlay is explicitly detached

    def is_expired(self) -> bool:
        """Return True if this overlay has passed its expiry time."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except ValueError:
            return True  # malformed expiry → treat as expired (fail closed)

    def is_active(self) -> bool:
        """Return True if this overlay is still in effect."""
        return self.detached_at is None and not self.is_expired()

    def to_dict(self) -> dict:
        return {
            "overlay_id": self.overlay_id,
            "session_id": self.session_id,
            "parent_manifest_id": self.parent_manifest_id,
            "created_by": self.created_by,
            "changes": self.changes.to_dict(),
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "detached_at": self.detached_at,
        }


# ---------------------------------------------------------------------------
# WorldStateView
# ---------------------------------------------------------------------------

@dataclass
class WorldStateView:
    """
    A resolved, point-in-time view of a session's executable world.

    This is what future UI and enforcement hooks will query to understand
    what the agent can currently do. It is computed (not stored), derived
    from the base manifest + all active overlays for the session.

    Invariants:
    - Always deterministic: same manifest + same overlays → same view.
    - computed_at reflects when the view was generated (not when state changed).
    - visible_tools is the authoritative list for tools/list rendering.
    - active_overlay_ids is ordered: later entries take precedence.
    """

    session_id: str
    manifest_id: str
    mode: str                               # "background" | "interactive"
    visible_tools: list[str]                # resolved tool names (base + overlays)
    active_constraints: dict[str, Any]      # merged constraints from base + overlays
    active_overlay_ids: list[str]           # IDs of overlays applied, in order
    computed_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "manifest_id": self.manifest_id,
            "mode": self.mode,
            "visible_tools": list(self.visible_tools),
            "active_constraints": dict(self.active_constraints),
            "active_overlay_ids": list(self.active_overlay_ids),
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def compute_action_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    """
    Compute a deterministic fingerprint for a tool call.

    The fingerprint is used to bind an ActionApproval to a specific action
    instance. Two calls with the same tool_name and arguments produce the
    same fingerprint.

    Args:
        tool_name:  The name of the tool being called.
        arguments:  The arguments dict (JSON-serializable).

    Returns:
        A hex string (SHA-256, truncated to 16 chars for readability).
    """
    payload = json.dumps(
        {"tool": tool_name, "args": arguments},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
