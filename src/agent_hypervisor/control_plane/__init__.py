"""
control_plane — World Authoring Console backend scaffolding.

This package implements the control plane for the Agent Hypervisor's
session-bound world authoring system. It is distinct from the data plane
(MCP gateway enforcement layer).

Two core concepts:

1. Act Authorization (ActionApproval)
   - End user allows or denies a single concrete action instance.
   - No world mutation; bound to action fingerprint; governed by TTL.

2. World Augmentation (SessionOverlay)
   - Operator attaches a temporary overlay to a live session.
   - Base manifest is never mutated.
   - Overlay can reveal/hide tools and widen/narrow scope.

Public API::

    from agent_hypervisor.control_plane import (
        # Domain
        Session, SessionEvent, ActionApproval,
        SessionOverlay, OverlayChanges, WorldStateView,
        compute_action_fingerprint,
        # Constants
        SESSION_MODE_BACKGROUND, SESSION_MODE_INTERACTIVE,
        SESSION_STATE_ACTIVE, SESSION_STATE_CLOSED,
        APPROVAL_STATUS_PENDING, APPROVAL_STATUS_ALLOWED, APPROVAL_STATUS_DENIED,
        # Services
        SessionStore, EventStore, ApprovalService, OverlayService,
        WorldStateResolver,
        # Event factories
        make_session_created, make_tool_call,
        make_approval_requested, make_approval_resolved,
        make_overlay_attached, make_overlay_detached,
        # World state bridge
        world_state_to_manifest_dict,
    )
"""

from .domain import (
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    APPROVAL_STATUS_EXPIRED,
    APPROVAL_STATUS_PENDING,
    EVENT_TYPE_APPROVAL_REQUESTED,
    EVENT_TYPE_APPROVAL_RESOLVED,
    EVENT_TYPE_MODE_CHANGED,
    EVENT_TYPE_OVERLAY_ATTACHED,
    EVENT_TYPE_OVERLAY_DETACHED,
    EVENT_TYPE_SESSION_CLOSED,
    EVENT_TYPE_SESSION_CREATED,
    EVENT_TYPE_TOOL_CALL,
    SESSION_MODE_BACKGROUND,
    SESSION_MODE_INTERACTIVE,
    SESSION_STATE_ACTIVE,
    SESSION_STATE_BLOCKED,
    SESSION_STATE_CLOSED,
    SESSION_STATE_WAITING_APPROVAL,
    ActionApproval,
    OverlayChanges,
    Session,
    SessionEvent,
    SessionOverlay,
    WorldStateView,
    compute_action_fingerprint,
)
from .event_store import (
    EventStore,
    make_approval_requested,
    make_approval_resolved,
    make_mode_changed,
    make_overlay_attached,
    make_overlay_detached,
    make_session_closed,
    make_session_created,
    make_tool_call,
)
from .approval_service import ApprovalService
from .overlay_service import OverlayService
from .session_store import SessionStore
from .world_state_resolver import WorldStateResolver, world_state_to_manifest_dict
from .api import ControlPlaneState, create_control_plane_router, create_control_plane_app

__all__ = [
    # Domain types
    "Session",
    "SessionEvent",
    "ActionApproval",
    "SessionOverlay",
    "OverlayChanges",
    "WorldStateView",
    # Domain functions
    "compute_action_fingerprint",
    # Constants — session state
    "SESSION_MODE_BACKGROUND",
    "SESSION_MODE_INTERACTIVE",
    "SESSION_STATE_ACTIVE",
    "SESSION_STATE_WAITING_APPROVAL",
    "SESSION_STATE_BLOCKED",
    "SESSION_STATE_CLOSED",
    # Constants — approval status
    "APPROVAL_STATUS_PENDING",
    "APPROVAL_STATUS_ALLOWED",
    "APPROVAL_STATUS_DENIED",
    "APPROVAL_STATUS_EXPIRED",
    # Constants — event types
    "EVENT_TYPE_SESSION_CREATED",
    "EVENT_TYPE_SESSION_CLOSED",
    "EVENT_TYPE_MODE_CHANGED",
    "EVENT_TYPE_TOOL_CALL",
    "EVENT_TYPE_APPROVAL_REQUESTED",
    "EVENT_TYPE_APPROVAL_RESOLVED",
    "EVENT_TYPE_OVERLAY_ATTACHED",
    "EVENT_TYPE_OVERLAY_DETACHED",
    # Services
    "SessionStore",
    "EventStore",
    "ApprovalService",
    "OverlayService",
    "WorldStateResolver",
    # Event factories
    "make_session_created",
    "make_session_closed",
    "make_mode_changed",
    "make_tool_call",
    "make_approval_requested",
    "make_approval_resolved",
    "make_overlay_attached",
    "make_overlay_detached",
    # World state bridge
    "world_state_to_manifest_dict",
    # API
    "ControlPlaneState",
    "create_control_plane_router",
    "create_control_plane_app",
]
