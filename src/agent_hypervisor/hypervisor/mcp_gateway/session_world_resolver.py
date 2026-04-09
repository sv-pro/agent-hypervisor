"""
session_world_resolver.py — Session to WorldManifest binding.

Responsibility:
    Map a session/request context to the active WorldManifest.

v1 implementation:
    Single static manifest per gateway instance (the default), plus an
    optional per-session registry. Sessions without an explicit binding
    fall back to the default manifest.

Extension path:
    register_session(session_id, manifest_path) binds a specific session
    to a different WorldManifest loaded from disk. This is the intended
    evolution of the resolve(session_id, context) signature that was
    designed to support this pattern from the start.

Invariants:
    - If the default manifest file cannot be loaded at startup, the resolver
      raises. Gateway startup fails; it does NOT default to an empty/permissive
      world.
    - If reload() fails, the existing manifest is retained (fail safe).
    - If register_session() fails to load the manifest, it raises and the
      session is NOT registered (fail closed — no silent fallback to default).
    - The resolver never returns None — callers can always depend on a manifest.
    - Unregistering a session is safe to call even if the session is not
      registered (idempotent, returns False in that case).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent_hypervisor.compiler.manifest import load_manifest
from agent_hypervisor.compiler.schema import WorldManifest


class SessionWorldResolver:
    """
    Resolves the active WorldManifest for a given session.

    Usage::

        resolver = SessionWorldResolver(Path("manifests/example_world.yaml"))

        # Default: all sessions share the same manifest
        manifest = resolver.resolve(session_id="s1")

        # Per-session: bind a specific session to a different manifest
        resolver.register_session("s1", Path("manifests/read_only_world.yaml"))
        manifest = resolver.resolve(session_id="s1")
        # → read_only_world manifest

        resolver.unregister_session("s1")
        manifest = resolver.resolve(session_id="s1")
        # → back to default manifest
    """

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = Path(manifest_path)
        self._manifest: Optional[WorldManifest] = None
        # session_id → WorldManifest (per-session overrides)
        self._session_registry: dict[str, WorldManifest] = {}
        self._load()  # Raises on failure — intentional (fail closed at startup)

    def resolve(
        self,
        session_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> WorldManifest:
        """
        Return the WorldManifest for this session.

        If the session has a registered manifest (via register_session),
        that manifest is returned. Otherwise the default manifest is used.

        Args:
            session_id: Optional session identifier. If registered, the
                        session-specific manifest is returned.
            context:    Optional context dict (reserved for future use).

        Returns:
            The active WorldManifest for this session.

        Raises:
            RuntimeError: If no manifest is loaded (should not happen after
                          successful __init__, but included for safety).
        """
        if self._manifest is None:
            raise RuntimeError(
                "SessionWorldResolver has no manifest loaded. "
                "Check manifest_path and startup logs."
            )
        if session_id and session_id in self._session_registry:
            return self._session_registry[session_id]
        return self._manifest

    def register_session(self, session_id: str, manifest_path: Path) -> WorldManifest:
        """
        Bind a session to a specific WorldManifest loaded from disk.

        The manifest is loaded immediately. If loading fails, the session
        is NOT registered and the exception propagates (fail closed).

        Args:
            session_id:    The session identifier to bind.
            manifest_path: Path to the WorldManifest YAML file.

        Returns:
            The loaded WorldManifest that was registered.

        Raises:
            FileNotFoundError: If manifest_path does not exist.
            Exception: If the manifest YAML is invalid.
        """
        manifest = load_manifest(Path(manifest_path))
        self._session_registry[session_id] = manifest
        return manifest

    def unregister_session(self, session_id: str) -> bool:
        """
        Remove a session's manifest binding, reverting to the default.

        Safe to call even if the session is not registered.

        Args:
            session_id: The session identifier to unbind.

        Returns:
            True if the session was registered and removed, False otherwise.
        """
        if session_id in self._session_registry:
            del self._session_registry[session_id]
            return True
        return False

    def session_registry(self) -> dict[str, str]:
        """
        Return a snapshot of current session bindings.

        Returns:
            Dict mapping session_id → workflow_id of the bound manifest.
        """
        return {
            sid: m.workflow_id
            for sid, m in self._session_registry.items()
        }

    def reload(self) -> bool:
        """
        Reload the default manifest from disk.

        Returns True if reload succeeded, False if it failed (existing
        manifest is retained on failure). Per-session registrations are
        not affected.
        """
        try:
            new_manifest = load_manifest(self._manifest_path)
            self._manifest = new_manifest
            return True
        except Exception:
            # Retain existing manifest — do not fail open
            return False

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    @property
    def manifest(self) -> Optional[WorldManifest]:
        """The default (gateway-level) manifest."""
        return self._manifest

    def _load(self) -> None:
        """Load default manifest at startup. Raises on failure."""
        self._manifest = load_manifest(self._manifest_path)
