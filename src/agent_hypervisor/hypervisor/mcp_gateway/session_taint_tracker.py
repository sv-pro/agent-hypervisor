"""
session_taint_tracker.py — Per-session runtime signal tracker.

Responsibility:
    Track observable signals for each live session that the
    LinkingPolicyEngine uses to drive automatic profile switching:

        taint_level       "clean" | "elevated" | "high"
        tool_call_count   cumulative tools/call invocations
        session_age_s     seconds since session was first seen
        last_verdict      last enforcement verdict: "allow" | "deny" | "ask"

These signals are injected into the resolver context on every tools/call so
that temporal / cumulative linking-policy rules fire automatically without
any explicit register_session() call.

Design constraints:
    - Pure in-memory (no I/O).  The tracker is reconstructed on restart.
    - Thread-safety: all mutations take a per-session lock so that concurrent
      tools/call invocations from the same session are safe.
    - Taint is monotonic: it can only escalate (clean → elevated → high);
      the only way to reset it is an explicit operator call to clear_taint().
    - The tracker never raises; unknown sessions are auto-initialised on
      first contact.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Ordered escalation levels.  Index reflects severity.
TAINT_LEVELS = ["clean", "elevated", "high"]


def _taint_index(level: str) -> int:
    try:
        return TAINT_LEVELS.index(level)
    except ValueError:
        return 0  # unknown level → treat as clean


@dataclass
class SessionSignals:
    """
    Runtime observable state for one session.

    All fields are updated in-place under the session lock.
    """
    session_id: str
    taint_level: str = "clean"               # monotonic escalation
    tool_call_count: int = 0                 # cumulative calls
    last_verdict: str = "allow"              # last enforcement outcome
    created_at: float = field(default_factory=time.monotonic)
    original_profile_id: Optional[str] = None   # profile at session start
    current_profile_id: Optional[str] = None    # last auto-switched profile

    @property
    def session_age_s(self) -> float:
        """Seconds since this session was first tracked."""
        return time.monotonic() - self.created_at

    def to_context(self) -> dict[str, Any]:
        """
        Materialise signals as a plain dict suitable for injecting into
        SessionWorldResolver.resolve(context=...).

        The keys here are the canonical context keys the linking-policy
        engine understands for Phase 4 temporal rules.
        """
        return {
            "taint_level": self.taint_level,
            "tool_call_count": self.tool_call_count,
            "session_age_s": round(self.session_age_s, 1),
            "last_verdict": self.last_verdict,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialisable snapshot for the REST API."""
        return {
            "session_id": self.session_id,
            "taint_level": self.taint_level,
            "tool_call_count": self.tool_call_count,
            "session_age_s": round(self.session_age_s, 1),
            "last_verdict": self.last_verdict,
            "original_profile_id": self.original_profile_id,
            "current_profile_id": self.current_profile_id,
        }


class SessionTaintTracker:
    """
    Tracks per-session runtime signals used for automatic profile switching.

    Usage::

        tracker = SessionTaintTracker()

        # On every tools/call:
        tracker.record_tool_call(session_id, verdict="allow")
        context = tracker.get_context(session_id)
        # → {"taint_level": "clean", "tool_call_count": 1, ...}

        # Escalate taint (e.g. after a suspicious pattern):
        tracker.escalate_taint(session_id, "high")

        # Operator clears taint to restore original profile:
        tracker.clear_taint(session_id)
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionSignals] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    # ── Session lifecycle ──────────────────────────────────────────────

    def _get_or_create(self, session_id: str) -> tuple[SessionSignals, threading.Lock]:
        """Return (signals, lock) for session_id, creating if needed."""
        with self._global_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionSignals(session_id=session_id)
                self._locks[session_id] = threading.Lock()
            return self._sessions[session_id], self._locks[session_id]

    def init_session(
        self,
        session_id: str,
        original_profile_id: Optional[str] = None,
    ) -> None:
        """
        Register a new session, recording the profile it starts with.

        Idempotent — calling again on an existing session is a no-op.
        """
        signals, lock = self._get_or_create(session_id)
        with lock:
            if signals.original_profile_id is None and original_profile_id:
                signals.original_profile_id = original_profile_id
                signals.current_profile_id = original_profile_id

    def remove_session(self, session_id: str) -> None:
        """Remove a session from tracking (e.g. on disconnect)."""
        with self._global_lock:
            self._sessions.pop(session_id, None)
            self._locks.pop(session_id, None)

    # ── Signal mutation ────────────────────────────────────────────────

    def record_tool_call(self, session_id: str, verdict: str = "allow") -> None:
        """
        Increment tool_call_count and update last_verdict.

        Call this on every tools/call invocation (before profile resolution
        so that the updated count is visible to the rule engine on this call).
        """
        signals, lock = self._get_or_create(session_id)
        with lock:
            signals.tool_call_count += 1
            signals.last_verdict = verdict

    def escalate_taint(self, session_id: str, level: str) -> bool:
        """
        Escalate (or set) the taint level for a session.

        Taint is monotonic — it will only be updated if the requested level
        is strictly higher than the current level.

        Args:
            session_id: Session to escalate.
            level:      One of "clean", "elevated", "high".

        Returns:
            True if the taint level changed, False if it was already ≥ level.
        """
        signals, lock = self._get_or_create(session_id)
        with lock:
            current_idx = _taint_index(signals.taint_level)
            new_idx = _taint_index(level)
            if new_idx > current_idx:
                signals.taint_level = level
                return True
            return False

    def clear_taint(self, session_id: str) -> bool:
        """
        Reset taint to "clean" (operator override).

        Args:
            session_id: Session to clear.

        Returns:
            True if the session was tracked (taint was reset), False otherwise.
        """
        with self._global_lock:
            if session_id not in self._sessions:
                return False
        signals, lock = self._get_or_create(session_id)
        with lock:
            signals.taint_level = "clean"
            # Restore current_profile_id to original so that subsequent
            # resolve() calls pick up the original profile again.
            signals.current_profile_id = signals.original_profile_id
            return True

    def note_profile_switch(
        self,
        session_id: str,
        new_profile_id: str,
    ) -> None:
        """Record that the session's profile was auto-switched."""
        signals, lock = self._get_or_create(session_id)
        with lock:
            signals.current_profile_id = new_profile_id

    # ── Query ──────────────────────────────────────────────────────────

    def get_signals(self, session_id: str) -> Optional[SessionSignals]:
        """Return a snapshot (not a live reference) of signals, or None."""
        with self._global_lock:
            sig = self._sessions.get(session_id)
        return sig  # caller should not mutate

    def get_context(self, session_id: str) -> dict[str, Any]:
        """
        Return the current signals as a context dict for the rule engine.

        Creates the session entry on first call (auto-init).
        """
        signals, _ = self._get_or_create(session_id)
        return signals.to_context()

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return serialisable snapshots of all tracked sessions."""
        with self._global_lock:
            session_ids = list(self._sessions.keys())
        return [self._sessions[sid].to_dict() for sid in session_ids]
