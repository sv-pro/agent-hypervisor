"""
event_store.py — Append-only event log for the control plane.

Events are structured records of things that happened in a session:
tool calls, approval requests, overlay attachments, mode changes, etc.

Design principles:
- Events are never deleted or mutated — append-only.
- Events are ordered by creation time within a session.
- The store is in-memory; persistence is out of scope for Phase 1.
- Callers should use the factory helpers (make_*) rather than constructing
  SessionEvent directly — this ensures consistent event types and payload schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .domain import (
    EVENT_TYPE_APPROVAL_REQUESTED,
    EVENT_TYPE_APPROVAL_RESOLVED,
    EVENT_TYPE_MODE_CHANGED,
    EVENT_TYPE_OVERLAY_ATTACHED,
    EVENT_TYPE_OVERLAY_DETACHED,
    EVENT_TYPE_SESSION_CLOSED,
    EVENT_TYPE_SESSION_CREATED,
    EVENT_TYPE_TOOL_CALL,
    SessionEvent,
)


class EventStore:
    """
    In-memory append-only event log.

    Events are indexed by event_id and grouped by session_id.
    Supports filtered queries by session and event type.
    """

    def __init__(self) -> None:
        self._events: dict[str, SessionEvent] = {}          # event_id → event
        self._by_session: dict[str, list[str]] = {}         # session_id → [event_id, ...]

    def append(self, event: SessionEvent) -> SessionEvent:
        """
        Append an event to the log.

        Args:
            event: The event to append. event_id must be unique.

        Returns:
            The appended event (same object).

        Raises:
            ValueError: If event_id already exists (duplicate).
        """
        if event.event_id in self._events:
            raise ValueError(f"Duplicate event_id: {event.event_id!r}")
        self._events[event.event_id] = event
        self._by_session.setdefault(event.session_id, []).append(event.event_id)
        return event

    def get(self, event_id: str) -> Optional[SessionEvent]:
        """Return an event by ID, or None."""
        return self._events.get(event_id)

    def get_session_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionEvent]:
        """
        Return events for a session, optionally filtered by type.

        Events are returned in append order (chronological).

        Args:
            session_id:  Session to query.
            event_type:  If set, only events of this type are returned.
            limit:       Maximum events to return (default 100).
            offset:      Skip this many events (for pagination).

        Returns:
            List of SessionEvent objects.
        """
        event_ids = self._by_session.get(session_id, [])
        events = [
            self._events[eid]
            for eid in event_ids
            if eid in self._events
        ]
        if event_type is not None:
            events = [e for e in events if e.type == event_type]
        return events[offset: offset + limit]

    def count(self, session_id: Optional[str] = None) -> int:
        """Return the total number of events, optionally for one session."""
        if session_id is not None:
            return len(self._by_session.get(session_id, []))
        return len(self._events)


# ---------------------------------------------------------------------------
# Event factory helpers
# ---------------------------------------------------------------------------

def make_session_created(session_id: str, manifest_id: str, mode: str) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_SESSION_CREATED,
        payload={"manifest_id": manifest_id, "mode": mode},
    )


def make_session_closed(session_id: str) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_SESSION_CLOSED,
        payload={},
    )


def make_mode_changed(session_id: str, old_mode: str, new_mode: str) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_MODE_CHANGED,
        payload={"old_mode": old_mode, "new_mode": new_mode},
    )


def make_tool_call(
    session_id: str,
    tool_name: str,
    decision: str,
    rule_hit: Optional[str] = None,
    arguments_summary: Optional[dict[str, Any]] = None,
) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_TOOL_CALL,
        payload={
            "tool_name": tool_name,
            "arguments_summary": arguments_summary or {},
        },
        decision=decision,
        rule_hit=rule_hit,
    )


def make_approval_requested(
    session_id: str,
    approval_id: str,
    tool_name: str,
    action_fingerprint: str,
) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_APPROVAL_REQUESTED,
        payload={
            "approval_id": approval_id,
            "tool_name": tool_name,
            "action_fingerprint": action_fingerprint,
        },
        decision="pending",
    )


def make_approval_resolved(
    session_id: str,
    approval_id: str,
    decision: str,
    resolved_by: str,
) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_APPROVAL_RESOLVED,
        payload={
            "approval_id": approval_id,
            "resolved_by": resolved_by,
        },
        decision=decision,
    )


def make_overlay_attached(
    session_id: str,
    overlay_id: str,
    created_by: str,
    changes_summary: dict[str, Any],
) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_OVERLAY_ATTACHED,
        payload={
            "overlay_id": overlay_id,
            "created_by": created_by,
            "changes_summary": changes_summary,
        },
    )


def make_overlay_detached(session_id: str, overlay_id: str) -> SessionEvent:
    return SessionEvent(
        event_id=_new_id(),
        session_id=session_id,
        timestamp=_now(),
        type=EVENT_TYPE_OVERLAY_DETACHED,
        payload={"overlay_id": overlay_id},
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
