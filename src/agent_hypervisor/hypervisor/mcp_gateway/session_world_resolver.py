"""
session_world_resolver.py — Session to WorldManifest binding.

Responsibility:
    Map a session/request context to the active WorldManifest.

Resolution priority (highest to lowest):
    1. Explicit per-session registration (register_session).
    2. LinkingPolicyEngine evaluation against the provided context dict.
    3. Default manifest (gateway-level fallback).

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
    - If the LinkingPolicyEngine returns a profile_id that is not in the
      catalog (or the catalog is not configured), the engine result is silently
      skipped and the default manifest is used. This preserves fail-safe
      behaviour: a misconfigured linking rule never causes a crash.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from agent_hypervisor.compiler.manifest import load_manifest
from agent_hypervisor.compiler.schema import WorldManifest

if TYPE_CHECKING:
    from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
    from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog


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

        # Dynamic: rule-based dispatch via context dict
        engine = LinkingPolicyEngine(rules=[...])
        catalog = ProfilesCatalog(Path("manifests/profiles-index.yaml"))
        resolver.set_linking_policy(engine, catalog)
        manifest = resolver.resolve(session_id="s2", context={"workflow_tag": "finance"})
        # → manifest for whichever profile_id the rule selects
    """

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = Path(manifest_path)
        self._manifest: Optional[WorldManifest] = None
        # session_id → WorldManifest (per-session overrides)
        self._session_registry: dict[str, WorldManifest] = {}
        self._engine: Optional["LinkingPolicyEngine"] = None
        self._catalog: Optional["ProfilesCatalog"] = None
        self._load()  # Raises on failure — intentional (fail closed at startup)

    def set_linking_policy(
        self,
        engine: "LinkingPolicyEngine",
        catalog: "ProfilesCatalog",
    ) -> None:
        """
        Configure the rule engine used for context-driven profile dispatch.

        Args:
            engine:  A LinkingPolicyEngine with the active rule set.
            catalog: A ProfilesCatalog used to load the manifest for the
                     matched profile_id.
        """
        self._engine = engine
        self._catalog = catalog

    def clear_linking_policy(self) -> None:
        """Remove the rule engine; context-based dispatch falls back to default."""
        self._engine = None
        self._catalog = None

    def resolve(
        self,
        session_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> WorldManifest:
        """
        Return the WorldManifest for this session.

        Resolution order:
        1. Explicit per-session registration (register_session).
        2. LinkingPolicyEngine result when context is provided.
        3. Default gateway-level manifest.

        Args:
            session_id: Optional session identifier.
            context:    Optional context dict for rule-based dispatch
                        (e.g. {"workflow_tag": "finance", "trust_level": "low"}).

        Returns:
            The active WorldManifest for this session.

        Raises:
            RuntimeError: If no manifest is loaded.
        """
        if self._manifest is None:
            raise RuntimeError(
                "SessionWorldResolver has no manifest loaded. "
                "Check manifest_path and startup logs."
            )

        # Priority 1: explicit per-session binding
        if session_id and session_id in self._session_registry:
            return self._session_registry[session_id]

        # Priority 2: rule engine evaluation
        if context and self._engine is not None and self._catalog is not None:
            profile_id = self._engine.evaluate(context)
            if profile_id:
                try:
                    return self._catalog.load_manifest(profile_id)
                except Exception:
                    # Misconfigured rule (unknown profile) — fall through to default
                    pass

        # Priority 3: default manifest
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
    def linking_policy_rules(self) -> list[dict]:
        """Return active linking-policy rules, or empty list if none configured."""
        if self._engine is None:
            return []
        return self._engine.rules()

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
