"""
api.py — Control plane FastAPI router for the World Authoring Console.

Provides HTTP endpoints for:
  - Session lifecycle management
  - World state inspection
  - Action approval (one-off authorizations)
  - Session overlay management (world augmentation)

Usage — mount on the existing MCP gateway::

    from agent_hypervisor.control_plane.api import (
        ControlPlaneState, create_control_plane_router,
    )
    cp_state = ControlPlaneState.create()
    app.state.control_plane = cp_state
    app.include_router(create_control_plane_router(cp_state))

Usage — standalone app (for testing or demo)::

    from agent_hypervisor.control_plane.api import create_control_plane_app
    import uvicorn
    uvicorn.run(create_control_plane_app(), host="127.0.0.1", port=8091)

Endpoints::

    POST   /control/sessions                            — create session
    GET    /control/sessions                            — list sessions (filter by state/mode)
    GET    /control/sessions/{session_id}               — get session detail
    PATCH  /control/sessions/{session_id}/mode          — set session mode
    DELETE /control/sessions/{session_id}               — close session

    GET    /control/sessions/{session_id}/world         — get WorldStateView
    GET    /control/sessions/{session_id}/events        — get session event log

    GET    /control/approvals                           — list pending approvals
    GET    /control/approvals/{approval_id}             — get approval detail
    POST   /control/approvals/{approval_id}/resolve     — resolve approval

    GET    /control/sessions/{session_id}/overlays      — list session overlays
    POST   /control/sessions/{session_id}/overlays      — attach overlay
    DELETE /control/sessions/{session_id}/overlays/{overlay_id}  — detach overlay

Design notes:
  - All endpoints are synchronous (no async needed for in-memory services).
  - Request/response bodies use Pydantic models for validation.
  - HTTPException 404 for not-found; 400 for bad input; 409 for state conflicts.
  - The ControlPlaneState holds all service instances; it is injected into the
    router at construction time (not via FastAPI DI) to keep coupling explicit.
  - The optional `get_base_manifest` callback bridges to the MCP gateway's manifest
    layer for world state resolution. Without it, the world endpoint returns an
    empty base tool list and notes that no manifest resolver is configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .approval_broadcaster import ApprovalBroadcaster
from .approval_service import ApprovalService
from .domain import (
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    SESSION_MODE_BACKGROUND,
    SESSION_MODE_INTERACTIVE,
    OverlayChanges,
    ScopedVerdict,
)
from .event_store import EventStore, make_session_created, make_session_closed, make_mode_changed
from .overlay_service import OverlayService
from .participant_registry import ParticipantRegistry
from .session_store import SessionStore
from .world_state_resolver import WorldStateResolver


# ---------------------------------------------------------------------------
# Control plane state
# ---------------------------------------------------------------------------

@dataclass
class ControlPlaneState:
    """
    Holds all control plane service instances.

    Passed to the router factory at construction time. Callers that mount
    the control plane on an existing gateway should configure
    get_base_manifest to bridge to the gateway's manifest layer.

    Attributes:
        session_store:       Session lifecycle store.
        event_store:         Append-only audit log.
        approval_service:    One-off action approval service.
        overlay_service:     Session overlay service.
        resolver:            WorldStateResolver (stateless; reads from stores above).
        participant_registry: Registry of participants eligible to vote on approvals.
        broadcaster:         Fans out approval events to participant SSE queues.
        get_base_manifest:   Optional callable: (session_id) → (list[str], dict).
                             Returns (base_tools, base_constraints) for a session.
                             If None, world state endpoints return an empty base.
    """

    session_store: SessionStore
    event_store: EventStore
    approval_service: ApprovalService
    overlay_service: OverlayService
    resolver: WorldStateResolver
    participant_registry: ParticipantRegistry = field(default_factory=ParticipantRegistry)
    broadcaster: ApprovalBroadcaster = field(default_factory=ApprovalBroadcaster)
    get_base_manifest: Optional[Callable[[str], tuple[list[str], dict]]] = None

    @classmethod
    def create(
        cls,
        default_ttl_seconds: int = 300,
        get_base_manifest: Optional[Callable] = None,
    ) -> "ControlPlaneState":
        """
        Construct a ControlPlaneState with fresh in-memory services.

        Args:
            default_ttl_seconds: Default TTL for approval requests.
            get_base_manifest:   Optional manifest bridge callable.
        """
        session_store = SessionStore()
        event_store = EventStore()
        approval_service = ApprovalService(default_ttl_seconds=default_ttl_seconds)
        overlay_service = OverlayService()
        resolver = WorldStateResolver(session_store, overlay_service)
        participant_registry = ParticipantRegistry()
        broadcaster = ApprovalBroadcaster()
        return cls(
            session_store=session_store,
            event_store=event_store,
            approval_service=approval_service,
            overlay_service=overlay_service,
            resolver=resolver,
            participant_registry=participant_registry,
            broadcaster=broadcaster,
            get_base_manifest=get_base_manifest,
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    manifest_id: str
    mode: str = SESSION_MODE_BACKGROUND
    principal: Optional[str] = None
    session_id: Optional[str] = None


class SetModeRequest(BaseModel):
    mode: str  # "background" | "interactive"


class ResolveApprovalRequest(BaseModel):
    decision: str       # "allowed" | "denied"
    resolved_by: str


class AttachOverlayRequest(BaseModel):
    created_by: str
    ttl_seconds: Optional[int] = None
    reveal_tools: list[str] = []
    hide_tools: list[str] = []
    widen_scope: dict[str, Any] = {}
    narrow_scope: dict[str, Any] = {}
    additional_constraints: dict[str, Any] = {}


class RegisterParticipantRequest(BaseModel):
    session_id: str
    roles: list[str]   # e.g. ["user", "operator"]


class ScopedVerdictItem(BaseModel):
    scope: str     # "one_off" | "session" | "world"
    verdict: str   # "allow" | "deny"
    participant_id: str = ""


class RespondToApprovalRequest(BaseModel):
    verdicts: list[ScopedVerdictItem]


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_control_plane_router(state: ControlPlaneState) -> APIRouter:
    """
    Build and return the FastAPI control plane router.

    Args:
        state: The ControlPlaneState holding all service instances.

    Returns:
        An APIRouter with all control plane endpoints registered.
    """
    router = APIRouter(prefix="/control", tags=["control-plane"])

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    @router.post("/sessions", status_code=201)
    def create_session(body: CreateSessionRequest) -> JSONResponse:
        """
        Create a new governed session.

        Registers the session in the SessionStore and emits a
        session_created event to the EventStore.
        """
        try:
            session = state.session_store.create(
                manifest_id=body.manifest_id,
                mode=body.mode,
                principal=body.principal,
                session_id=body.session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        state.event_store.append(
            make_session_created(session.session_id, session.manifest_id, session.mode)
        )
        return JSONResponse(session.to_dict(), status_code=201)

    @router.get("/sessions")
    def list_sessions(
        state_filter: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> JSONResponse:
        """
        List all sessions, optionally filtered by state or mode.

        Query params:
            state_filter: active | waiting_approval | blocked | closed
            mode:         background | interactive
        """
        sessions = state.session_store.list(state=state_filter, mode=mode)
        return JSONResponse({
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions),
        })

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str) -> JSONResponse:
        """Get full session detail including overlay_ids and state."""
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")
        return JSONResponse(session.to_dict())

    @router.patch("/sessions/{session_id}/mode")
    def set_session_mode(session_id: str, body: SetModeRequest) -> JSONResponse:
        """
        Change a session's mode.

        background → interactive: operator attachment / human-in-the-loop enabled.
        interactive → background: operator detaches.
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        old_mode = session.mode
        try:
            updated = state.session_store.set_mode(session_id, body.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        state.event_store.append(
            make_mode_changed(session_id, old_mode, body.mode)
        )
        return JSONResponse(updated.to_dict())

    @router.delete("/sessions/{session_id}")
    def close_session(session_id: str) -> JSONResponse:
        """
        Close a session.

        The session record is retained for audit. Active overlays are
        NOT automatically detached (they will expire naturally or can
        be detached explicitly). The session can no longer be transitioned.
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        closed = state.session_store.close(session_id)
        state.event_store.append(make_session_closed(session_id))
        return JSONResponse(closed.to_dict())

    # ------------------------------------------------------------------
    # World state
    # ------------------------------------------------------------------

    @router.get("/sessions/{session_id}/world")
    def get_world_state(session_id: str) -> JSONResponse:
        """
        Get the resolved WorldStateView for a session.

        Returns the current visible tool world after applying all active
        overlays on top of the base manifest.

        If no manifest resolver is configured (get_base_manifest is None),
        returns the overlay-only view (base tools = empty).
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        if state.get_base_manifest is not None:
            try:
                base_tools, base_constraints = state.get_base_manifest(session_id)
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to resolve base manifest: {exc}",
                )
        else:
            base_tools = []
            base_constraints = {}

        view = state.resolver.resolve(session_id, base_tools, base_constraints)
        response = view.to_dict()
        if state.get_base_manifest is None:
            response["_note"] = (
                "No manifest resolver configured. "
                "base_tools is empty; only overlay effects are shown."
            )
        return JSONResponse(response)

    # ------------------------------------------------------------------
    # Session event log
    # ------------------------------------------------------------------

    @router.get("/sessions/{session_id}/events")
    def get_session_events(
        session_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> JSONResponse:
        """
        Return the structured event log for a session.

        Query params:
            event_type: Filter to a specific event type.
            limit:      Max events to return (default 100).
            offset:     Skip first N events (for pagination).
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        events = state.event_store.get_session_events(
            session_id, event_type=event_type, limit=limit, offset=offset
        )
        return JSONResponse({
            "session_id": session_id,
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    @router.get("/approvals")
    def list_pending_approvals(session_id: Optional[str] = None) -> JSONResponse:
        """
        List all pending approval requests, optionally filtered by session.

        Expired approvals are swept before returning (check_expired is called).
        """
        state.approval_service.check_expired()
        approvals = state.approval_service.list_pending(session_id=session_id)
        return JSONResponse({
            "approvals": [a.to_dict() for a in approvals],
            "count": len(approvals),
        })

    @router.get("/approvals/{approval_id}")
    def get_approval(approval_id: str) -> JSONResponse:
        """Get full detail for one approval record."""
        approval = state.approval_service.get(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id!r}")
        return JSONResponse(approval.to_dict())

    @router.post("/approvals/{approval_id}/resolve")
    def resolve_approval(approval_id: str, body: ResolveApprovalRequest) -> JSONResponse:
        """
        Resolve a pending approval.

        body.decision must be "allowed" or "denied".
        body.resolved_by identifies the human or system making the decision.

        An expired approval always resolves as "denied" regardless of the
        requested decision (fail-closed rule).
        """
        if body.decision not in (APPROVAL_STATUS_ALLOWED, APPROVAL_STATUS_DENIED):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid decision: {body.decision!r}. Must be 'allowed' or 'denied'.",
            )

        try:
            resolved = state.approval_service.resolve(
                approval_id,
                decision=body.decision,
                resolved_by=body.resolved_by,
                event_store=state.event_store,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id!r}")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        return JSONResponse(resolved.to_dict())

    # ------------------------------------------------------------------
    # Overlays
    # ------------------------------------------------------------------

    @router.get("/sessions/{session_id}/overlays")
    def list_overlays(
        session_id: str,
        active_only: bool = True,
    ) -> JSONResponse:
        """
        List overlays for a session.

        Query params:
            active_only: If true (default), return only active overlays.
                         If false, return all overlays including detached/expired.
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        if active_only:
            overlays = state.overlay_service.get_active_overlays(session_id)
        else:
            overlays = state.overlay_service.list_all_for_session(session_id)

        return JSONResponse({
            "session_id": session_id,
            "overlays": [o.to_dict() for o in overlays],
            "count": len(overlays),
            "active_only": active_only,
        })

    @router.post("/sessions/{session_id}/overlays", status_code=201)
    def attach_overlay(session_id: str, body: AttachOverlayRequest) -> JSONResponse:
        """
        Attach a world augmentation overlay to a session.

        The overlay immediately affects the session's world state view.
        The base manifest is never mutated.

        body fields:
            created_by:             Operator identity (required, for audit).
            ttl_seconds:            Time-to-live in seconds. None = no expiry.
            reveal_tools:           Tool names to add to the visible world.
            hide_tools:             Tool names to remove from the visible world.
            widen_scope:            Per-tool constraints to relax.
            narrow_scope:           Per-tool constraints to tighten.
            additional_constraints: Arbitrary top-level constraints.
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        changes = OverlayChanges(
            reveal_tools=body.reveal_tools,
            hide_tools=body.hide_tools,
            widen_scope=body.widen_scope,
            narrow_scope=body.narrow_scope,
            additional_constraints=body.additional_constraints,
        )
        overlay = state.overlay_service.attach(
            session_id=session_id,
            parent_manifest_id=session.manifest_id,
            created_by=body.created_by,
            changes=changes,
            ttl_seconds=body.ttl_seconds,
            session_store=state.session_store,
            event_store=state.event_store,
        )
        return JSONResponse(overlay.to_dict(), status_code=201)

    @router.delete("/sessions/{session_id}/overlays/{overlay_id}")
    def detach_overlay(session_id: str, overlay_id: str) -> JSONResponse:
        """
        Detach an overlay from a session.

        The overlay record is retained for audit (detached_at is set).
        The session's world state immediately reverts to the pre-overlay state
        for this overlay's contribution.

        Returns 404 if the overlay is not found or already detached.
        """
        session = state.session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")

        removed = state.overlay_service.detach(
            overlay_id,
            session_store=state.session_store,
            event_store=state.event_store,
        )
        if not removed:
            raise HTTPException(
                status_code=404,
                detail=f"Overlay not found or already detached: {overlay_id!r}",
            )

        return JSONResponse({
            "status": "detached",
            "overlay_id": overlay_id,
            "session_id": session_id,
        })

    # ------------------------------------------------------------------
    # Participants (multi-scope approval system)
    # ------------------------------------------------------------------

    @router.post("/participants", status_code=201)
    def register_participant(body: RegisterParticipantRequest) -> JSONResponse:
        """
        Register a participant that can respond to approval requests.

        A participant is an operator/user session identified by its SSE
        session_id. It holds one or more roles that determine which approval
        scopes it can vote on:
          user     → one_off scope
          operator → session scope
          admin    → world scope

        Registering the same session_id again updates the roles (upsert).
        Participants receive "approval_requested" SSE events when approvals
        are created.
        """
        reg = state.participant_registry.register(
            session_id=body.session_id,
            roles=set(body.roles),
        )
        return JSONResponse(reg.to_dict(), status_code=201)

    @router.delete("/participants/{session_id}")
    def unregister_participant(session_id: str) -> JSONResponse:
        """
        Unregister a participant.

        Safe to call even if the session is not currently registered.
        """
        removed = state.participant_registry.unregister(session_id)
        return JSONResponse({
            "status": "unregistered" if removed else "not_registered",
            "session_id": session_id,
        })

    @router.get("/participants")
    def list_participants() -> JSONResponse:
        """List all registered participants."""
        regs = state.participant_registry.list_all()
        return JSONResponse({
            "participants": [r.to_dict() for r in regs],
            "count": len(regs),
        })

    # ------------------------------------------------------------------
    # Multi-scope approval response (new in Phase 8)
    # ------------------------------------------------------------------

    @router.patch("/approvals/{approval_id}/respond")
    def respond_to_approval(
        approval_id: str,
        body: RespondToApprovalRequest,
    ) -> JSONResponse:
        """
        Submit scoped verdicts for a pending approval.

        Body::

            {
              "verdicts": [
                {"scope": "one_off",  "verdict": "allow", "participant_id": "..."},
                {"scope": "session",  "verdict": "allow", "participant_id": "..."},
                {"scope": "world",    "verdict": "deny",  "participant_id": "..."}
              ]
            }

        Each verdict fires its side effect immediately:
          one_off allow  → marks the fingerprint approved (tool call can be retried)
          session allow  → creates a SessionOverlay revealing the tool
          world   allow  → stub (no-op)

        Verdicts are idempotent per scope: duplicate scope submissions are ignored.

        The tool call UNBLOCKS as soon as any scope provides "allow".
        The originator receives an "approval_resolved" SSE event so the client
        knows to retry.

        An expired approval always results in denial regardless of verdict content.

        Returns 404 if approval not found; 409 if already in a terminal state.
        """
        approval = state.approval_service.get(approval_id)
        if approval is None:
            raise HTTPException(
                status_code=404,
                detail=f"Approval not found: {approval_id!r}",
            )

        # Snapshot pre-respond state to detect first allow.
        was_allowed_before = _has_allow_verdict(approval)

        # Build ScopedVerdict objects from the request body.
        verdicts = [
            ScopedVerdict(
                scope=v.scope,
                verdict=v.verdict,
                participant_id=v.participant_id,
            )
            for v in body.verdicts
        ]

        try:
            updated = state.approval_service.respond(
                approval_id=approval_id,
                verdicts=verdicts,
                overlay_service=state.overlay_service,
                session_store=state.session_store,
                event_store=state.event_store,
            )
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Approval not found: {approval_id!r}",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        # Notify the originator via SSE if an allow verdict was just received.
        is_allowed_now = _has_allow_verdict(updated)
        if is_allowed_now and not was_allowed_before:
            effective_verdict = "allow"
            state.broadcaster.notify_originator(
                originator_session_id=updated.session_id,
                approval=updated,
                effective_verdict=effective_verdict,
            )

        return JSONResponse(updated.to_dict())

    return router


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_allow_verdict(approval: Any) -> bool:
    """Return True if any scoped_verdict on the approval is an allow."""
    for sv in approval.scoped_verdicts:
        if sv.verdict == "allow":
            return True
    return False


# ---------------------------------------------------------------------------
# Standalone app factory
# ---------------------------------------------------------------------------

def create_control_plane_app(
    default_ttl_seconds: int = 300,
    get_base_manifest: Optional[Callable] = None,
) -> FastAPI:
    """
    Build a standalone FastAPI app with the control plane router mounted.

    Useful for testing, demos, and running the control plane separately
    from the MCP gateway.

    Args:
        default_ttl_seconds: Default TTL for approval requests.
        get_base_manifest:   Optional manifest bridge callable.

    Returns:
        A FastAPI app ready to serve with uvicorn.
    """
    cp_state = ControlPlaneState.create(
        default_ttl_seconds=default_ttl_seconds,
        get_base_manifest=get_base_manifest,
    )
    router = create_control_plane_router(cp_state)

    app = FastAPI(
        title="Agent Hypervisor — World Authoring Control Plane",
        description=(
            "Control plane for session-bound world authoring. "
            "Manage session lifecycle, action approvals, and session overlays."
        ),
        version="0.2.0",
    )
    app.state.control_plane = cp_state
    app.include_router(router)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({
            "status": "running",
            "sessions": cp_state.session_store.count(),
            "approvals": cp_state.approval_service.count(),
            "overlays": cp_state.overlay_service.count(),
            "participants": cp_state.participant_registry.count(),
        })

    return app
