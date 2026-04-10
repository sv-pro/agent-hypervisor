"""
participant_registry.py — Registry of participants eligible to respond to approval requests.

A participant is a connected session (identified by its SSE session_id) that holds
one or more roles. Roles map to approval scopes:
  user     → one_off scope
  operator → session scope
  admin    → world scope

Participants receive "approval_requested" SSE events when an approval is created
and can respond via PATCH /control/approvals/{id}/respond with verdicts for any
of their applicable scopes.

Design notes:
- Keyed by session_id (one registration per SSE session).
- Re-registering the same session_id updates the roles (upsert semantics).
- In-memory; no persistence required — participants re-register on reconnect.
- Thread-safety: single-threaded asyncio event loop context; no locking needed.
"""

from __future__ import annotations

from typing import Optional

from .domain import ParticipantRegistration, _now


class ParticipantRegistry:
    """
    In-memory registry of participants eligible to respond to approval requests.

    Participants are identified by their SSE session_id. Each participant holds
    a set of roles that determine which approval scopes they can vote on.

    Invariants:
    - At most one registration per session_id.
    - Re-registering a session_id replaces the previous registration (upsert).
    - Unregistering is idempotent — calling unregister() for an unknown session
      is a no-op and returns False.
    """

    def __init__(self) -> None:
        self._participants: dict[str, ParticipantRegistration] = {}  # session_id → reg

    def register(self, session_id: str, roles: set) -> ParticipantRegistration:
        """
        Register (or update) a participant with the given roles.

        Args:
            session_id: The SSE session_id of the participant. Used to route
                        approval events and to look up the SSE queue.
            roles:      Set of role strings, e.g. {"user", "operator"}.
                        Empty set is valid (participant receives events but has
                        no applicable scopes).

        Returns:
            The ParticipantRegistration record (new or updated).
        """
        reg = ParticipantRegistration(
            participant_id=session_id,
            session_id=session_id,
            roles=set(roles),
        )
        self._participants[session_id] = reg
        return reg

    def unregister(self, session_id: str) -> bool:
        """
        Remove a participant registration.

        Args:
            session_id: The session to remove.

        Returns:
            True if the session was found and removed, False if not registered.
        """
        if session_id in self._participants:
            del self._participants[session_id]
            return True
        return False

    def get(self, session_id: str) -> Optional[ParticipantRegistration]:
        """Return the registration for a session, or None."""
        return self._participants.get(session_id)

    def list_all(self) -> list[ParticipantRegistration]:
        """
        Return all registered participants.

        Returns:
            Participants sorted by registered_at ascending.
        """
        return sorted(self._participants.values(), key=lambda r: r.registered_at)

    def count(self) -> int:
        """Return the number of registered participants."""
        return len(self._participants)
