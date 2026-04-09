"""
overlay_service.py — Session-scoped world augmentation service.

Handles the World Augmentation concept: operators can temporarily modify the
executable world for a specific session by attaching overlays. Overlays sit
on top of the base manifest without mutating it.

Core semantics:
- Overlays attach to a session, not to the base manifest.
- The base manifest is NEVER mutated by overlay operations.
- Overlays have an explicit created_by, TTL, and can be detached.
- Detaching an overlay restores the previous world state for the session.
- Multiple overlays can be active simultaneously; they are applied in order.
- Later overlays take precedence over earlier ones for the same tool.

Supported overlay changes (this phase):
- reveal_tools: add tools to the visible world
- hide_tools: remove tools from the visible world
- widen_scope: relax per-tool constraints
- narrow_scope: tighten per-tool constraints

Design notes:
- In-memory; no disk persistence in Phase 1.
- SessionStore must be updated separately (caller's responsibility).
- Event emission is opt-in via event_store parameter.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .domain import OverlayChanges, SessionOverlay
from .event_store import (
    EventStore,
    make_overlay_attached,
    make_overlay_detached,
)


class OverlayService:
    """
    Manages session-scoped world augmentation overlays.

    An overlay is an operator-authored temporary modification to a session's
    executable world. It does not touch the base manifest; it is applied on
    top of it by the WorldStateResolver.

    Invariants:
    - Overlays are session-scoped: they do not affect other sessions.
    - The base manifest is never mutated.
    - Detached or expired overlays are not returned by get_active_overlays().
    - Each overlay has a unique overlay_id (UUID).
    """

    def __init__(self) -> None:
        self._overlays: dict[str, SessionOverlay] = {}

    def attach(
        self,
        session_id: str,
        parent_manifest_id: str,
        created_by: str,
        changes: Optional[OverlayChanges] = None,
        ttl_seconds: Optional[int] = None,
        overlay_id: Optional[str] = None,
        event_store: Optional[EventStore] = None,
        session_store: Optional[Any] = None,
    ) -> SessionOverlay:
        """
        Create and attach a new overlay to a session.

        Args:
            session_id:          The session to augment.
            parent_manifest_id:  The base manifest this overlay is applied to.
            created_by:          Operator identity (for audit).
            changes:             The world changes to apply. Defaults to empty (no-op).
            ttl_seconds:         Time-to-live. None = no expiry.
            overlay_id:          Optional explicit ID; auto-generated if not provided.
            event_store:         If provided, an overlay_attached event is emitted.
            session_store:       If provided, session.overlay_ids is updated.

        Returns:
            The newly created and attached SessionOverlay.
        """
        oid = overlay_id or str(uuid.uuid4())
        if oid in self._overlays:
            raise ValueError(f"Overlay {oid!r} already exists.")

        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            ).isoformat()

        overlay = SessionOverlay(
            overlay_id=oid,
            session_id=session_id,
            parent_manifest_id=parent_manifest_id,
            created_by=created_by,
            changes=changes or OverlayChanges(),
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        self._overlays[oid] = overlay

        if session_store is not None:
            session_store.attach_overlay(session_id, oid)

        if event_store is not None:
            event_store.append(
                make_overlay_attached(
                    session_id=session_id,
                    overlay_id=oid,
                    created_by=created_by,
                    changes_summary=_summarise_changes(overlay.changes),
                )
            )

        return overlay

    def detach(
        self,
        overlay_id: str,
        event_store: Optional[EventStore] = None,
        session_store: Optional[Any] = None,
    ) -> bool:
        """
        Detach an overlay, removing its effect from the session.

        The overlay record is retained for audit purposes (detached_at is set).
        It will no longer be returned by get_active_overlays().

        Args:
            overlay_id:    The overlay to detach.
            event_store:   If provided, an overlay_detached event is emitted.
            session_store: If provided, session.overlay_ids is updated.

        Returns:
            True if the overlay was found and detached, False if not found
            or already detached.
        """
        overlay = self._overlays.get(overlay_id)
        if overlay is None or overlay.detached_at is not None:
            return False

        overlay.detached_at = _now()

        if session_store is not None:
            session_store.detach_overlay(overlay.session_id, overlay_id)

        if event_store is not None:
            event_store.append(
                make_overlay_detached(
                    session_id=overlay.session_id,
                    overlay_id=overlay_id,
                )
            )

        return True

    def get(self, overlay_id: str) -> Optional[SessionOverlay]:
        """Return an overlay by ID, or None."""
        return self._overlays.get(overlay_id)

    def get_active_overlays(self, session_id: str) -> list[SessionOverlay]:
        """
        Return all currently active overlays for a session.

        An overlay is active if it has not been detached and has not expired.
        Overlays are returned in creation order (oldest first). The WorldStateResolver
        applies them in this order; later overlays take precedence.

        Args:
            session_id: The session to query.

        Returns:
            List of active SessionOverlay objects, sorted by created_at ascending.
        """
        active = [
            o for o in self._overlays.values()
            if o.session_id == session_id and o.is_active()
        ]
        return sorted(active, key=lambda o: o.created_at)

    def list_all_for_session(self, session_id: str) -> list[SessionOverlay]:
        """
        Return all overlays for a session (including detached and expired).

        For audit purposes.
        """
        overlays = [
            o for o in self._overlays.values()
            if o.session_id == session_id
        ]
        return sorted(overlays, key=lambda o: o.created_at)

    def check_expired(self) -> list[SessionOverlay]:
        """
        Return all overlays that have expired but are not yet detached.

        Does NOT automatically detach them — callers decide if they want
        to detach or just inspect. (Expiry is checked lazily by is_active().)
        """
        now = datetime.now(timezone.utc)
        expired = []
        for overlay in self._overlays.values():
            if overlay.detached_at is not None:
                continue
            if not overlay.expires_at:
                continue
            try:
                expiry = datetime.fromisoformat(overlay.expires_at)
                if now > expiry:
                    expired.append(overlay)
            except ValueError:
                expired.append(overlay)
        return expired

    def count(self) -> int:
        """Return the total number of overlay records (any state)."""
        return len(self._overlays)


def _summarise_changes(changes: OverlayChanges) -> dict[str, Any]:
    """Build a compact summary dict for event payload."""
    summary: dict[str, Any] = {}
    if changes.reveal_tools:
        summary["reveal_tools"] = changes.reveal_tools
    if changes.hide_tools:
        summary["hide_tools"] = changes.hide_tools
    if changes.widen_scope:
        summary["widen_scope"] = list(changes.widen_scope.keys())
    if changes.narrow_scope:
        summary["narrow_scope"] = list(changes.narrow_scope.keys())
    return summary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
