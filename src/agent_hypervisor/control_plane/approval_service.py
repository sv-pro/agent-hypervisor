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
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    APPROVAL_STATUS_EXPIRED,
    APPROVAL_STATUS_PENDING,
    ActionApproval,
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
        for approval in self._approvals.values():
            if approval.status != APPROVAL_STATUS_PENDING:
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

    def is_action_approved(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """
        Check whether a concrete action has a valid pending approval.

        This does NOT consume the approval. The approval remains pending
        until explicitly resolved. One approval = one authorization for
        the fingerprint, not unlimited reuse.

        Returns True only if there is a non-expired pending approval
        for the exact fingerprint in the given session.

        Note: This is a point-in-time check. Callers must resolve the
        approval immediately after using it to prevent double-use.
        """
        fingerprint = compute_action_fingerprint(tool_name, arguments)
        for approval in self._approvals.values():
            if (
                approval.session_id == session_id
                and approval.action_fingerprint == fingerprint
                and approval.status == APPROVAL_STATUS_PENDING
                and not approval.is_expired()
            ):
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
