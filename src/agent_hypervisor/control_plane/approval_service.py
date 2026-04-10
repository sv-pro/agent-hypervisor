"""
approval_service.py — One-off action authorization service.

Handles the Act Authorization concept: end users can allow or deny a single
concrete action instance. This is distinct from world augmentation (overlays).

Core semantics:
- An approval is bound to an action_fingerprint (deterministic hash of tool + args).
- An approval applies ONLY to the exact action it was created for.
- An approval does NOT reveal hidden tools or widen the capability world.
- Approvals have a TTL; expired approvals are treated as denied.
- Resolved approvals (allowed/denied) are retained for audit.

Design notes:
- In-memory store; no disk persistence in Phase 1.
- Event emission is opt-in: callers pass an EventStore to receive events.
- The service is the single source of truth for approval state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .domain import (
    APPROVAL_SCOPE_ONE_OFF,
    APPROVAL_SCOPE_SESSION,
    APPROVAL_SCOPE_WORLD,
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    APPROVAL_STATUS_EXPIRED,
    APPROVAL_STATUS_PARTIALLY_RESOLVED,
    APPROVAL_STATUS_PENDING,
    APPROVAL_STATUS_RESOLVED,
    ActionApproval,
    OverlayChanges,
    ScopedVerdict,
    compute_action_fingerprint,
)
from .event_store import EventStore, make_approval_requested, make_approval_resolved


class ApprovalService:
    """
    Manages one-off action authorization requests.

    An approval request is created when an action requires explicit authorization
    (e.g. when the policy engine returns verdict=ask, or when background mode
    cannot proceed without human sign-off).

    Invariants:
    - Each approval is bound to a specific (tool_name, arguments) fingerprint.
    - Resolving an approval does not change the session's visible tool world.
    - Expired approvals are treated as denied, never as allowed.
    - Approval IDs are UUIDs; action fingerprints are SHA-256 truncated hashes.
    """

    def __init__(self, default_ttl_seconds: int = 300) -> None:
        """
        Args:
            default_ttl_seconds: Default TTL for pending approvals (default 5 min).
                                 Set to 0 for no expiry (not recommended).
        """
        self._approvals: dict[str, ActionApproval] = {}
        self._default_ttl = default_ttl_seconds

    def request_approval(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        requested_by: str,
        rationale: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        event_store: Optional[EventStore] = None,
    ) -> ActionApproval:
        """
        Create a new pending approval request.

        Args:
            session_id:   The session requesting authorization.
            tool_name:    The tool being called.
            arguments:    The exact arguments for the call.
            requested_by: Who triggered the request (agent name / system).
            rationale:    Human-readable reason (optional; shown in UI).
            ttl_seconds:  Time-to-live in seconds. Defaults to service default.
                          0 means no expiry (avoid in production).
            event_store:  If provided, an approval_requested event is emitted.

        Returns:
            The newly created ActionApproval (status=pending).
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        if ttl > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=ttl)
            ).isoformat()
        else:
            expires_at = ""

        fingerprint = compute_action_fingerprint(tool_name, arguments)
        approval_id = str(uuid.uuid4())

        approval = ActionApproval(
            approval_id=approval_id,
            session_id=session_id,
            action_fingerprint=fingerprint,
            tool_name=tool_name,
            arguments_summary=dict(arguments),
            requested_by=requested_by,
            status=APPROVAL_STATUS_PENDING,
            expires_at=expires_at,
            rationale=rationale,
        )
        self._approvals[approval_id] = approval

        if event_store is not None:
            event_store.append(
                make_approval_requested(
                    session_id=session_id,
                    approval_id=approval_id,
                    tool_name=tool_name,
                    action_fingerprint=fingerprint,
                )
            )

        return approval

    def resolve(
        self,
        approval_id: str,
        decision: str,
        resolved_by: str,
        event_store: Optional[EventStore] = None,
    ) -> ActionApproval:
        """
        Resolve a pending approval with an allow or deny decision.

        Resolving an expired approval always results in denied status
        (the expiry wins; the operator's intent is noted in resolved_by
        but the approval is not granted).

        Args:
            approval_id:  The approval to resolve.
            decision:     "allowed" or "denied".
            resolved_by:  Identity of the human/system making the decision.
            event_store:  If provided, an approval_resolved event is emitted.

        Returns:
            The updated ActionApproval.

        Raises:
            KeyError: If approval_id is not found.
            ValueError: If decision is not "allowed" or "denied".
            RuntimeError: If approval is already resolved (not pending).
        """
        if decision not in (APPROVAL_STATUS_ALLOWED, APPROVAL_STATUS_DENIED):
            raise ValueError(
                f"Invalid decision: {decision!r}. Must be 'allowed' or 'denied'."
            )

        approval = self._require(approval_id)

        if approval.status != APPROVAL_STATUS_PENDING:
            raise RuntimeError(
                f"Approval {approval_id!r} is already resolved "
                f"(status={approval.status!r})."
            )

        # If expired, override decision to denied (fail closed)
        effective_decision = decision
        if approval.is_expired():
            effective_decision = APPROVAL_STATUS_DENIED

        now = _now()
        approval.status = effective_decision
        approval.resolved_at = now
        approval.resolved_by = resolved_by

        if event_store is not None:
            event_store.append(
                make_approval_resolved(
                    session_id=approval.session_id,
                    approval_id=approval_id,
                    decision=effective_decision,
                    resolved_by=resolved_by,
                )
            )

        return approval

    def get(self, approval_id: str) -> Optional[ActionApproval]:
        """Return an approval by ID, or None."""
        return self._approvals.get(approval_id)

    def check_expired(self) -> list[ActionApproval]:
        """
        Scan for pending approvals that have expired and mark them as expired.

        Returns the list of newly expired approvals.
        This is a maintenance operation; callers may call it periodically
        or before listing pending approvals to ensure stale entries are cleared.
        """
        now = datetime.now(timezone.utc)
        expired = []
        _sweepable = {APPROVAL_STATUS_PENDING, APPROVAL_STATUS_PARTIALLY_RESOLVED}
        for approval in self._approvals.values():
            if approval.status not in _sweepable:
                continue
            if not approval.expires_at:
                continue
            try:
                expiry = datetime.fromisoformat(approval.expires_at)
                if now > expiry:
                    approval.status = APPROVAL_STATUS_EXPIRED
                    expired.append(approval)
            except ValueError:
                # Malformed expiry — mark as expired (fail closed)
                approval.status = APPROVAL_STATUS_EXPIRED
                expired.append(approval)
        return expired

    def list_pending(self, session_id: Optional[str] = None) -> list[ActionApproval]:
        """
        Return all pending approvals, optionally filtered by session.

        Expired pending approvals are NOT automatically cleaned up here;
        callers should call check_expired() periodically if they need
        real-time expiry enforcement.

        Returns approvals sorted by created_at ascending.
        """
        approvals = [
            a for a in self._approvals.values()
            if a.status == APPROVAL_STATUS_PENDING
        ]
        if session_id is not None:
            approvals = [a for a in approvals if a.session_id == session_id]
        return sorted(approvals, key=lambda a: a.created_at)

    def list_for_session(
        self,
        session_id: str,
        status: Optional[str] = None,
    ) -> list[ActionApproval]:
        """
        Return all approvals for a session, optionally filtered by status.

        Returns approvals sorted by created_at ascending.
        """
        approvals = [
            a for a in self._approvals.values()
            if a.session_id == session_id
        ]
        if status is not None:
            approvals = [a for a in approvals if a.status == status]
        return sorted(approvals, key=lambda a: a.created_at)

    def respond(
        self,
        approval_id: str,
        verdicts: list,
        overlay_service: Optional[Any] = None,
        session_store: Optional[Any] = None,
        event_store: Optional[EventStore] = None,
    ) -> ActionApproval:
        """
        Submit one or more scoped verdicts for a pending approval.

        Each entry in ``verdicts`` must be a ScopedVerdict. Verdicts are
        idempotent per scope: if a verdict for a scope is already recorded,
        the new verdict for that scope is ignored (no double side-effect).

        Side effects fired immediately on receipt (if not already fired):
          one_off allow  → marks the approval as fingerprint-approved so the
                           originating tool call can be retried.
          session allow  → creates a SessionOverlay (reveal_tool) for the session.
          world   allow  → no-op stub.
          any     deny   → recorded; no structural side effect.

        Status progression:
          pending            → partially_resolved (after first new verdict)
          partially_resolved → resolved (after all three scopes have verdicts)
          any status         → expired   (if TTL already passed when called)

        Fail-closed: expired approvals always result in the approval being
        marked expired and no side effects are applied.

        Args:
            approval_id:    The approval to respond to.
            verdicts:       List of ScopedVerdict objects.
            overlay_service: Required for session-scope allow side effect.
            session_store:  Required for session-scope allow side effect.
            event_store:    Optional; forwarded to overlay_service for audit.

        Returns:
            The updated ActionApproval.

        Raises:
            KeyError:    If approval_id is not found.
            RuntimeError: If the approval is already in a terminal state
                          (allowed/denied/expired/resolved) and not partially_resolved.
        """
        approval = self._require(approval_id)

        # Fail closed: expired approval → mark expired, apply no verdicts.
        if approval.is_expired():
            if approval.status not in (APPROVAL_STATUS_EXPIRED,):
                approval.status = APPROVAL_STATUS_EXPIRED
            return approval

        # Only pending and partially_resolved approvals can accept new verdicts.
        _active_statuses = {APPROVAL_STATUS_PENDING, APPROVAL_STATUS_PARTIALLY_RESOLVED}
        if approval.status not in _active_statuses:
            raise RuntimeError(
                f"Approval {approval_id!r} is already in terminal state "
                f"(status={approval.status!r})."
            )

        existing_scopes = {sv.scope for sv in approval.scoped_verdicts}

        for verdict in verdicts:
            # Idempotent: skip if this scope already has a recorded verdict.
            if verdict.scope in existing_scopes:
                continue

            # Record the verdict first.
            approval.scoped_verdicts.append(verdict)
            existing_scopes.add(verdict.scope)

            # Fire scope-specific side effects.
            if verdict.verdict == "allow":
                if verdict.scope == APPROVAL_SCOPE_ONE_OFF:
                    # Fingerprint approval: the tool call can be retried and will
                    # succeed. We rely on is_action_approved() checking scoped_verdicts.
                    pass  # side effect is is_action_approved() returning True

                elif verdict.scope == APPROVAL_SCOPE_SESSION:
                    # Create a SessionOverlay that reveals the tool for this session.
                    if overlay_service is not None and session_store is not None:
                        session = session_store.get(approval.session_id)
                        manifest_id = (
                            session.manifest_id if session is not None else "unknown"
                        )
                        changes = OverlayChanges(reveal_tools=[approval.tool_name])
                        overlay_service.attach(
                            session_id=approval.session_id,
                            parent_manifest_id=manifest_id,
                            created_by=verdict.participant_id or "approval_service",
                            changes=changes,
                            session_store=session_store,
                            event_store=event_store,
                        )

                elif verdict.scope == APPROVAL_SCOPE_WORLD:
                    # Stub: global approval is not yet implemented.
                    pass

        # Update status based on how many scopes now have verdicts.
        _all_scopes = {APPROVAL_SCOPE_ONE_OFF, APPROVAL_SCOPE_SESSION, APPROVAL_SCOPE_WORLD}
        recorded_scopes = {sv.scope for sv in approval.scoped_verdicts}
        if recorded_scopes:
            if _all_scopes <= recorded_scopes:
                approval.status = APPROVAL_STATUS_RESOLVED
            else:
                approval.status = APPROVAL_STATUS_PARTIALLY_RESOLVED

        return approval

    def is_action_approved(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """
        Check whether a concrete action has a valid (pending or allowed) approval.

        Returns True if there is a non-expired approval in either pending or
        allowed state for the exact fingerprint in the given session. This is
        the backward-compatible check used by callers that treat "a pending
        approval exists" as "this action is queued for authorization".

        Note: This is a point-in-time check. Callers must resolve the
        approval immediately after using it to prevent double-use.

        See also: has_explicit_allow() for the stricter check used by the
        gateway pre-check to determine if execution can actually proceed.
        """
        fingerprint = compute_action_fingerprint(tool_name, arguments)
        for approval in self._approvals.values():
            if (
                approval.session_id == session_id
                and approval.action_fingerprint == fingerprint
                and approval.status in (APPROVAL_STATUS_PENDING, APPROVAL_STATUS_ALLOWED)
                and not approval.is_expired()
            ):
                return True
        return False

    def has_explicit_allow(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """
        Check whether a concrete action has been explicitly allowed.

        Stricter than is_action_approved(): returns True only if an operator
        has affirmatively allowed the action via either:
          1. Old mechanism: resolve() setting status=allowed.
          2. New multi-scope mechanism: respond() with a one_off "allow" scoped
             verdict.

        Used by the gateway pre-check to determine if a tool call that would
        normally route to the approval workflow can instead proceed directly.

        Note: This is a point-in-time check. Callers must resolve the
        approval immediately after using it to prevent double-use.
        """
        fingerprint = compute_action_fingerprint(tool_name, arguments)
        for approval in self._approvals.values():
            if (
                approval.session_id != session_id
                or approval.action_fingerprint != fingerprint
                or approval.is_expired()
            ):
                continue
            # Old mechanism: explicit allow via resolve()
            if approval.status == APPROVAL_STATUS_ALLOWED:
                return True
            # New mechanism: one_off allow scoped verdict via respond()
            for sv in approval.scoped_verdicts:
                if sv.scope == APPROVAL_SCOPE_ONE_OFF and sv.verdict == "allow":
                    return True
        return False

    def count(self) -> int:
        """Return the total number of approval records."""
        return len(self._approvals)

    def _require(self, approval_id: str) -> ActionApproval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"Approval not found: {approval_id!r}")
        return approval


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
