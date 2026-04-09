"""
tool_surface_renderer.py — Manifest-driven tool surface rendering.

Responsibility:
    Given a WorldManifest and a ToolRegistry, produce the list of MCPTool
    objects that are visible in the current world.

Core principle:
    tools/list is not just discovery — it is world rendering.
    A tool that is not in the manifest does not exist in this world.
    It is absent, not merely forbidden.

Invariants:
    - Only tools declared in the manifest AND registered in the registry appear.
    - Tool order follows manifest declaration order (deterministic).
    - No LLM, no probabilistic filtering, no mutable state.
"""

from __future__ import annotations

from agent_hypervisor.compiler.schema import WorldManifest
from agent_hypervisor.hypervisor.gateway.tool_registry import ToolRegistry

from .protocol import MCPTool


class ToolSurfaceRenderer:
    """
    Renders the visible tool surface for an MCP client.

    Two sources of truth must agree for a tool to appear:
      1. WorldManifest declares the tool (ontological inclusion)
      2. ToolRegistry has an adapter for the tool (implementation exists)

    If either is missing, the tool is absent from the rendered surface.
    This is ontological absence, not a runtime rejection.
    """

    def __init__(self, manifest: WorldManifest, registry: ToolRegistry) -> None:
        self._manifest = manifest
        self._registry = registry

    def render(self) -> list[MCPTool]:
        """
        Return the list of tools visible in the current world.

        Order follows the manifest's capability list (deterministic).
        Tools in the registry but not in the manifest do not appear.
        Tools in the manifest but with no adapter do not appear.
        """
        result: list[MCPTool] = []
        for cap in self._manifest.capabilities:
            tool_def = self._registry.get_tool(cap.tool)
            if tool_def is None:
                # Declared in manifest but no adapter — skip (not an error).
                # This allows manifests to declare intent before adapters exist.
                continue
            input_schema = self._build_input_schema(cap.tool, cap.constraints)
            result.append(
                MCPTool(
                    name=tool_def.name,
                    description=tool_def.description,
                    inputSchema=input_schema,
                )
            )
        return result

    def is_visible(self, tool_name: str) -> bool:
        """
        Return True if tool_name is visible in the current world.

        A tool is visible iff:
          - The manifest declares it (with any constraints), AND
          - The registry has an adapter for it.

        Used by ToolCallEnforcer as a fast pre-check.
        """
        if not self._manifest.allows(tool_name, {}):
            return False
        return self._registry.get_tool(tool_name) is not None

    @staticmethod
    def _build_input_schema(tool_name: str, constraints: dict) -> dict:
        """
        Build a JSON Schema for the tool's inputSchema field.

        Currently generates a permissive schema. Constraints from the manifest
        are recorded as metadata but not yet enforced as JSON Schema assertions.
        A future phase can derive tighter schemas from constraint specs.
        """
        schema: dict = {"type": "object", "properties": {}}
        if constraints:
            schema["x-ah-constraints"] = constraints
        return schema
