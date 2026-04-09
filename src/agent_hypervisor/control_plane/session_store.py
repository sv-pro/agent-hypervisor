"""
session_store.py — In-memory session registry for the control plane.

Tracks the lifecycle of all governed runtime sessions. Sessions are
created when an agent session begins and closed when it ends.

The store is the single source of truth for session state. All state
mutations go through the store's methods — callers do not mutate
Session objects directly.

Design notes:
- In-memory only; no disk persistence in this phase.
- Thread-safety is not required (single-threaded async FastAPI context).
- If persistence is needed, replace this with a file-backed or DB-backed
  implementation that implements the same interface.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .domain import (
    SESSION_MODE_BACKGROUND,
    SESSION_MODE_INTERACTIVE,
    SESSION_STATE_ACTIVE,
    SESSION_STATE_BLOCKED,
    SESSION_STATE_CLOSED,
    SESSION_STATE_WAITING_APPROVAL,
    Session,
)


class SessionStore:
    """
    In-memory store for Session lifecycle management.

    Methods follow a create / get / update / list pattern. All mutations
    return the updated Session so callers always have a fresh snapshot.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(
        self,
        manifest_id: str,
        mode: str = SESSION_MODE_BACKGROUND,
        principal: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        Create and register a new session.

        Args:
            manifest_id:  The ID of the WorldManifest this session operates under.
            mode:         "background" (default) or "interactive".
            principal:    Optional identity of the user/agent.
            session_id:   Optional explicit ID; auto-generated if not provided.

        Returns:
            The newly created Session.

        Raises:
            ValueError: If a session with the given session_id already exists,
                        or if mode is not a recognised value.
        """
        if mode not in (SESSION_MODE_BACKGROUND, SESSION_MODE_INTERACTIVE):
            raise ValueError(f"Invalid mode: {mode!r}. Must be 'background' or 'interactive'.")

        sid = session_id or str(uuid.uuid4())
        if sid in self._sessions:
            raise ValueError(f"Session {sid!r} already exists.")

        session = Session(
            session_id=sid,
            manifest_id=manifest_id,
            mode=mode,
            state=SESSION_STATE_ACTIVE,
            overlay_ids=[],
            principal=principal,
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Return the session by ID, or None if not found."""
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        """
        Return the session by ID, raising KeyError if not found.

        Use this when a missing session is a programming error, not a user error.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id!r}")
        return session

    def list(
        self,
        state: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> list[Session]:
        """
        Return all sessions, optionally filtered.

        Args:
            state: Filter by session state (e.g. "active", "closed").
            mode:  Filter by session mode (e.g. "background", "interactive").

        Returns:
            Sessions sorted by created_at ascending.
        """
        sessions = list(self._sessions.values())
        if state is not None:
            sessions = [s for s in sessions if s.state == state]
        if mode is not None:
            sessions = [s for s in sessions if s.mode == mode]
        return sorted(sessions, key=lambda s: s.created_at)

    def transition_state(self, session_id: str, new_state: str) -> Session:
        """
        Transition a session to a new state.

        Valid states: active, waiting_approval, blocked, closed.

        Args:
            session_id: The session to update.
            new_state:  The target state.

        Returns:
            The updated Session.

        Raises:
            KeyError: If session not found.
            ValueError: If new_state is not valid.
        """
        valid = {
            SESSION_STATE_ACTIVE,
            SESSION_STATE_WAITING_APPROVAL,
            SESSION_STATE_BLOCKED,
            SESSION_STATE_CLOSED,
        }
        if new_state not in valid:
            raise ValueError(f"Invalid state: {new_state!r}. Must be one of {valid}.")

        session = self.require(session_id)
        session.state = new_state
        session.updated_at = _now()
        return session

    def set_mode(self, session_id: str, mode: str) -> Session:
        """
        Change a session's mode.

        Background → interactive is the normal operator-attach transition.
        Interactive → background is possible (operator detaches).

        Args:
            session_id: The session to update.
            mode:       "background" or "interactive".

        Returns:
            The updated Session.

        Raises:
            KeyError: If session not found.
            ValueError: If mode is not valid.
        """
        if mode not in (SESSION_MODE_BACKGROUND, SESSION_MODE_INTERACTIVE):
            raise ValueError(f"Invalid mode: {mode!r}.")

        session = self.require(session_id)
        session.mode = mode
        session.updated_at = _now()
        return session

    def attach_overlay(self, session_id: str, overlay_id: str) -> Session:
        """
        Record that an overlay has been attached to this session.

        Appends to overlay_ids; does not validate the overlay_id itself.
        The OverlayService is responsible for overlay validity.

        Returns:
            The updated Session.
        """
        session = self.require(session_id)
        if overlay_id not in session.overlay_ids:
            session.overlay_ids.append(overlay_id)
            session.updated_at = _now()
        return session

    def detach_overlay(self, session_id: str, overlay_id: str) -> Session:
        """
        Record that an overlay has been detached from this session.

        Safe to call even if the overlay_id is not in the session's list.

        Returns:
            The updated Session.
        """
        session = self.require(session_id)
        if overlay_id in session.overlay_ids:
            session.overlay_ids.remove(overlay_id)
            session.updated_at = _now()
        return session

    def close(self, session_id: str) -> Session:
        """
        Mark a session as closed.

        Closed sessions are retained for audit purposes but are not active.

        Returns:
            The closed Session.
        """
        return self.transition_state(session_id, SESSION_STATE_CLOSED)

    def count(self) -> int:
        """Return the total number of sessions (any state)."""
        return len(self._sessions)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
