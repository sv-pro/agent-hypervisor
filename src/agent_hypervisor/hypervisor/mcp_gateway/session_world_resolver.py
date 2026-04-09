"""
session_world_resolver.py — Session to WorldManifest binding.

Responsibility:
    Map a session/request context to the active WorldManifest.

Initial implementation:
    Single static manifest per gateway instance, loaded from a YAML file
    at startup. All sessions share this manifest.

Extension path:
    The resolve(session_id, context) signature is designed to evolve into
    per-session or per-user manifest selection without changing callers.
    A future implementation might look up session_id in a manifest registry
    or select a manifest based on context["workflow"] or context["role"].

Invariants:
    - If the manifest file cannot be loaded at startup, the resolver raises.
      Gateway startup fails; it does NOT default to an empty/permissive world.
    - If reload() fails, the existing manifest is retained (fail safe).
    - The resolver never returns None — callers can always depend on a manifest.
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
        manifest = resolver.resolve(session_id="s1")
        # → WorldManifest with declared capabilities
    """

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = Path(manifest_path)
        self._manifest: Optional[WorldManifest] = None
        self._load()  # Raises on failure — intentional (fail closed at startup)

    def resolve(
        self,
        session_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> WorldManifest:
        """
        Return the WorldManifest for this session.

        Current implementation ignores session_id and context — same manifest
        for all sessions. This is the correct starting point.

        Args:
            session_id: Optional session identifier (unused in v1).
            context:    Optional context dict (unused in v1).

        Returns:
            The active WorldManifest.

        Raises:
            RuntimeError: If no manifest is loaded (should not happen after
                          successful __init__, but included for safety).
        """
        if self._manifest is None:
            raise RuntimeError(
                "SessionWorldResolver has no manifest loaded. "
                "Check manifest_path and startup logs."
            )
        return self._manifest

    def reload(self) -> bool:
        """
        Reload the manifest from disk.

        Returns True if reload succeeded, False if it failed (existing
        manifest is retained on failure).
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
        return self._manifest

    def _load(self) -> None:
        """Load manifest at startup. Raises on failure."""
        self._manifest = load_manifest(self._manifest_path)
