"""
world_state_resolver.py — Resolves the visible world for a session.

Produces a WorldStateView by compositing the base manifest with all
active session overlays. This is the authoritative answer to:

  - Which tools are visible in this session?
  - Which constraints are active?
  - Which overlays are applied?
  - What mode is this session in?

Future UI and API endpoints will query WorldStateResolver to render the
control plane's view of a session's world.

Design:
- Resolution is deterministic: same inputs → same output.
- Overlays are applied in creation order (oldest first).
- Later overlays take precedence for conflicting mutations.
- The base manifest is never mutated; all changes exist only in the view.
- The resolver is stateless: it takes inputs and returns a view; it does
  not hold references to sessions or overlays.

Integration with the MCP gateway:
- Currently the MCP gateway uses SessionWorldResolver (static manifests).
- The WorldStateView can be used to synthesise a WorldManifest that
  SessionWorldResolver.register_session() ingests. See CONTROL_PLANE_PLAN.md
  for the planned bridge architecture.
"""

from __future__ import annotations

from typing import Any, Optional

from .domain import (
    SESSION_MODE_BACKGROUND,
    OverlayChanges,
    Session,
    SessionOverlay,
    WorldStateView,
)
from .overlay_service import OverlayService
from .session_store import SessionStore


class WorldStateResolver:
    """
    Computes a resolved WorldStateView for a session.

    Combines:
    - The base manifest (represented as visible_tools + constraints)
    - All active overlays for the session (applied in creation order)
    - The session's current mode

    The resolver is stateless. It reads from the stores but does not
    modify them. Call resolve() whenever you need a fresh view.
    """

    def __init__(
        self,
        session_store: SessionStore,
        overlay_service: OverlayService,
    ) -> None:
        self._sessions = session_store
        self._overlays = overlay_service

    def resolve(
        self,
        session_id: str,
        base_tools: list[str],
        base_constraints: Optional[dict[str, Any]] = None,
    ) -> WorldStateView:
        """
        Compute the resolved WorldStateView for a session.

        Args:
            session_id:        The session to resolve.
            base_tools:        The tool names from the base WorldManifest.
                               (Use WorldManifest.tool_names().)
            base_constraints:  Per-tool constraints from the base manifest.
                               Format: {tool_name: {constraint_key: value, ...}}.
                               Defaults to empty (no per-tool constraints).

        Returns:
            A WorldStateView representing the current visible world for this
            session after all active overlays are applied.

        Raises:
            KeyError: If session_id is not found in the session store.
        """
        session: Session = self._sessions.require(session_id)
        active_overlays: list[SessionOverlay] = self._overlays.get_active_overlays(session_id)

        # Start from the base manifest
        visible_tools: list[str] = list(base_tools)
        constraints: dict[str, Any] = dict(base_constraints or {})

        # Apply overlays in creation order (oldest first)
        # Later overlays win for conflicting changes
        for overlay in active_overlays:
            visible_tools, constraints = _apply_overlay(
                visible_tools, constraints, overlay.changes
            )

        return WorldStateView(
            session_id=session_id,
            manifest_id=session.manifest_id,
            mode=session.mode,
            visible_tools=visible_tools,
            active_constraints=constraints,
            active_overlay_ids=[o.overlay_id for o in active_overlays],
        )

    def resolve_from_manifest(self, session_id: str, manifest: Any) -> WorldStateView:
        """
        Convenience method: resolve from a WorldManifest object directly.

        Args:
            session_id: The session to resolve.
            manifest:   A WorldManifest instance (from compiler.schema).

        Returns:
            A WorldStateView for this session.
        """
        base_tools = manifest.tool_names()
        base_constraints = {
            cap.tool: cap.constraints
            for cap in manifest.capabilities
            if cap.constraints
        }
        return self.resolve(session_id, base_tools, base_constraints)


# ---------------------------------------------------------------------------
# Overlay application logic
# ---------------------------------------------------------------------------

def _apply_overlay(
    visible_tools: list[str],
    constraints: dict[str, Any],
    changes: OverlayChanges,
) -> tuple[list[str], dict[str, Any]]:
    """
    Apply one overlay's changes to the current visible_tools and constraints.

    Returns a new (visible_tools, constraints) tuple; does not mutate inputs.

    Semantics:
    1. hide_tools removes tools from the visible set.
    2. reveal_tools adds tools to the visible set (if not already present).
    3. widen_scope updates per-tool constraint dicts (relaxing restrictions).
    4. narrow_scope updates per-tool constraint dicts (tightening restrictions).
       narrow_scope always wins over widen_scope for the same tool.

    Fail-closed rule: If a reveal_tool tries to add a tool that the manifest
    did not declare, it IS added to the visible world (the operator is
    explicitly widening the world). The enforcement layer (ToolCallEnforcer)
    still needs a registered adapter; unknown adapters still fail closed there.
    """
    # Work with copies
    tools = list(visible_tools)
    cons = {k: dict(v) if isinstance(v, dict) else v for k, v in constraints.items()}

    # Step 1: hide_tools — remove from visible set
    for tool in changes.hide_tools:
        if tool in tools:
            tools.remove(tool)

    # Step 2: reveal_tools — add to visible set (no-op if already present)
    for tool in changes.reveal_tools:
        if tool not in tools:
            tools.append(tool)

    # Step 3: widen_scope — relax constraints per tool
    for tool, delta in changes.widen_scope.items():
        if tool in cons and isinstance(cons[tool], dict) and isinstance(delta, dict):
            # Merge: delta values override existing constraint values
            cons[tool] = {**cons[tool], **delta}
        elif isinstance(delta, dict):
            cons[tool] = dict(delta)

    # Step 4: narrow_scope — tighten constraints per tool (wins over widen_scope)
    for tool, delta in changes.narrow_scope.items():
        if tool in cons and isinstance(cons[tool], dict) and isinstance(delta, dict):
            # Merge: narrow_scope delta overrides both base and widen_scope
            cons[tool] = {**cons[tool], **delta}
        elif isinstance(delta, dict):
            cons[tool] = dict(delta)

    # Step 5: additional_constraints applied at top level
    if changes.additional_constraints:
        cons["__additional__"] = changes.additional_constraints

    return tools, cons


# ---------------------------------------------------------------------------
# Utility: synthesise a WorldManifest-compatible dict from a WorldStateView
# ---------------------------------------------------------------------------

def world_state_to_manifest_dict(view: WorldStateView) -> dict[str, Any]:
    """
    Convert a WorldStateView to a dict compatible with WorldManifest.

    This is the bridge between the control plane's view of the world and
    the data plane's manifest format. The result can be passed to
    manifest_from_dict() (compiler.schema) to create a synthetic manifest
    that SessionWorldResolver can register.

    Usage::

        view = resolver.resolve(session_id, base_tools, base_constraints)
        manifest_dict = world_state_to_manifest_dict(view)
        synthetic_manifest = manifest_from_dict(manifest_dict)
        session_world_resolver.register_session(session_id, synthetic_manifest_path)

    Note: The synthetic manifest workflow_id uses the overlay suffix to
    distinguish it from the base manifest.
    """
    capabilities = []
    for tool in view.visible_tools:
        cap: dict[str, Any] = {"tool": tool}
        tool_constraints = view.active_constraints.get(tool)
        if tool_constraints and isinstance(tool_constraints, dict):
            cap["constraints"] = tool_constraints
        capabilities.append(cap)

    overlay_suffix = (
        "-".join(view.active_overlay_ids[:3])  # first 3 overlay IDs
        if view.active_overlay_ids else "base"
    )

    return {
        "workflow_id": f"{view.manifest_id}+overlay:{overlay_suffix}",
        "version": "1.0",
        "capabilities": capabilities,
        "metadata": {
            "synthesised_from": view.manifest_id,
            "active_overlays": view.active_overlay_ids,
            "computed_at": view.computed_at,
        },
    }
