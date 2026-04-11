"""
approval_broadcaster.py — Fan-out of approval events to SSE participants.

Two distinct event types are broadcast:

1. "approval_requested" — sent to ALL registered participants when an approval
   is created. Participants use this to know there is a pending decision waiting.

2. "approval_resolved" — sent to the ORIGINATOR (the session that triggered the
   tool call) when any approval scope returns "allow". This unblocks the client
   so it can retry the tool call.

SSE framing:
  Control-plane notifications use a named SSE event type so clients can
  distinguish them from JSON-RPC responses:

    event: approval
    data: {"type": "approval_requested", ...}

  Clients listen via:
    source.addEventListener("approval", (e) => { ... });

  Raw JSON-RPC responses pushed by the MCP layer use the default "message"
  event type and are unaffected.

Architecture:
- ApprovalBroadcaster holds an optional reference to the SSESessionStore.
- The SSESessionStore is wired in by create_mcp_app() after the sse_store is
  created, via set_sse_store(). Without it, broadcasts are silent no-ops.
- All queue writes use put_nowait() so they work from synchronous API handlers.
- Failures (full queue, missing session) are logged and swallowed — the
  enforcement path must never crash due to a notification failure.

Design notes:
- Fail-closed on enforcement; fail-open on notification (log + continue).
- The broadcaster is stateless except for the sse_store reference.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

_ALL_SCOPES = ["one_off", "session", "world"]


class ApprovalBroadcaster:
    """
    Routes approval events to SSE queues.

    Broadcast is fire-and-forget: failures are logged but never propagate.
    The broadcaster can be used before the SSE store is wired (it becomes
    a no-op) so that tests and standalone control-plane deployments work
    without the full gateway.
    """

    def __init__(self) -> None:
        self._sse_store: Optional[Any] = None  # SSESessionStore | None

    def set_sse_store(self, sse_store: Any) -> None:
        """
        Wire the broadcaster to the gateway's SSE session store.

        Called by create_mcp_app() after the SSESessionStore is created.
        Without this, all broadcasts are silent no-ops.

        Args:
            sse_store: An SSESessionStore instance.
        """
        self._sse_store = sse_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def broadcast_approval_requested(
        self,
        approval: Any,
        participant_registry: Any,
    ) -> int:
        """
        Fan out an "approval_requested" event to all registered participants.

        Each participant registered in the ParticipantRegistry receives the
        event on their SSE queue (if their queue is still alive). Participants
        that have disconnected (queue not found) are silently skipped.

        Args:
            approval:             The ActionApproval that was just created.
            participant_registry: The ParticipantRegistry holding registered
                                  participants and their session_ids.

        Returns:
            Number of participants successfully notified.
        """
        if self._sse_store is None:
            return 0

        ttl_remaining = _compute_ttl_remaining(approval.expires_at)
        payload = json.dumps({
            "type": "approval_requested",
            "approval_id": approval.approval_id,
            "tool_name": approval.tool_name,
            "arguments": approval.arguments_summary,
            "fingerprint": approval.action_fingerprint,
            "ttl_seconds": ttl_remaining,
            "scopes_available": _ALL_SCOPES,
        })

        count = 0
        for reg in participant_registry.list_all():
            if self._push_to_session(reg.session_id, payload):
                count += 1
        return count

    def notify_originator(
        self,
        originator_session_id: str,
        approval: Any,
        effective_verdict: str,
    ) -> bool:
        """
        Push an "approval_resolved" event to the originating session's SSE queue.

        Called when any approval scope returns "allow" so the client knows it can
        retry the tool call. If the originator has disconnected, this is a no-op.

        Args:
            originator_session_id: The session_id of the session that triggered
                                   the original tool call (approval.session_id).
            approval:              The ActionApproval with scoped_verdicts populated.
            effective_verdict:     "allow" or "deny" — the aggregate outcome.

        Returns:
            True if the event was successfully queued, False otherwise.
        """
        if self._sse_store is None or not originator_session_id:
            return False

        payload = json.dumps({
            "type": "approval_resolved",
            "approval_id": approval.approval_id,
            "effective_verdict": effective_verdict,
            "scoped_verdicts": [sv.to_dict() for sv in approval.scoped_verdicts],
        })
        return self._push_to_session(originator_session_id, payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _push_to_session(self, session_id: str, payload: str) -> bool:
        """
        Push a control-plane SSE frame to a session's queue.

        Frames use the named event type ``approval`` so clients can distinguish
        them from JSON-RPC ``message`` events::

            event: approval
            data: {"type": "approval_requested", ...}

        Uses put_nowait() so it is safe to call from synchronous handlers.
        Returns False and logs a warning on any failure.
        """
        if self._sse_store is None:
            return False
        queue = self._sse_store.get_queue(session_id)
        if queue is None:
            return False
        # Wrap payload in a named SSE event frame.
        frame = f"event: approval\ndata: {payload}\n\n"
        try:
            queue.put_nowait(frame)
            return True
        except Exception as exc:
            log.warning(
                "ApprovalBroadcaster: failed to push to session %r: %s",
                session_id,
                exc,
            )
            return False


def _compute_ttl_remaining(expires_at: str) -> Optional[int]:
    """Return seconds until expires_at, or None if no expiry."""
    if not expires_at:
        return None
    try:
        expiry = datetime.fromisoformat(expires_at)
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(remaining))
    except ValueError:
        return 0
