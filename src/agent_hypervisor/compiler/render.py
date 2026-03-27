"""Render: project a world manifest into a Rendered Capability Surface."""

from __future__ import annotations

from collections.abc import Callable

from .schema import CapabilityConstraint, WorldManifest


class CapabilityViolation(Exception):
    """Raised when a tool call violates the workflow manifest."""


class RenderedTool:
    """A constrained tool wrapper that is part of the Rendered Capability Surface.

    The tool name follows the deterministic convention ``rendered__{tool_name}``.
    Calling an instance checks the invocation against the embedded
    :class:`~agent_world_compiler.schema.CapabilityConstraint` and raises
    :class:`CapabilityViolation` if the call is not permitted.
    """

    def __init__(self, constraint: CapabilityConstraint, raw_fn: Callable | None = None):
        self.constraint = constraint
        self.raw_fn = raw_fn
        # deterministic name: rendered__{tool_name}
        self.name = f"rendered__{constraint.tool}"

    def __call__(self, **params):
        """Invoke the rendered tool, enforcing manifest constraints.

        Args:
            **params: Parameters forwarded to the underlying tool.

        Returns:
            The result of ``raw_fn(**params)`` when a raw function is provided,
            otherwise a status dict.

        Raises:
            CapabilityViolation: If the call violates the manifest constraints.
        """
        if not self.constraint.allows(self.constraint.tool, params):
            raise CapabilityViolation(
                f"Tool '{self.constraint.tool}' call with params {params} "
                f"violates manifest constraints {self.constraint.constraints}"
            )
        if self.raw_fn is not None:
            return self.raw_fn(**params)
        return {"tool": self.constraint.tool, "params": params, "status": "rendered"}


def render_manifest(
    manifest: WorldManifest,
    raw_tools: dict[str, Callable] | None = None,
) -> dict[str, "RenderedTool"]:
    """Render a WorldManifest into the Rendered Capability Surface.

    Each capability in the manifest becomes a :class:`RenderedTool` keyed by
    ``rendered__{tool_name}``.  If *raw_tools* contains a matching callable it
    is wired in; otherwise the rendered tool returns a status dict on success.

    Args:
        manifest: The world manifest to render.
        raw_tools: Optional mapping of tool names to raw callables.

    Returns:
        Dict mapping ``rendered__{tool_name}`` to :class:`RenderedTool` instances
        representing the agent's Rendered Capability Surface.
    """
    raw_tools = raw_tools or {}
    rendered: dict[str, RenderedTool] = {}
    for cap in manifest.capabilities:
        raw_fn = raw_tools.get(cap.tool)
        tool = RenderedTool(constraint=cap, raw_fn=raw_fn)
        rendered[tool.name] = tool
    return rendered


def render_summary(rendered: dict[str, "RenderedTool"]) -> str:
    """Return a human-readable summary of the Rendered Capability Surface.

    Args:
        rendered: Mapping of rendered tool names to :class:`RenderedTool` instances.

    Returns:
        Multi-line string describing each tool in the Rendered Capability Surface
        and its constraints.
    """
    lines = [f"Rendered Capability Surface ({len(rendered)} tools):"]
    for name, tool in rendered.items():
        c = tool.constraint.constraints
        if "paths" in c:
            detail = "paths: " + ", ".join(c["paths"])
        elif "domains" in c:
            detail = "domains: " + ", ".join(c["domains"])
        elif c:
            detail = str(c)
        else:
            detail = "unrestricted"
        lines.append(f"  {name}  [{detail}]")
    return "\n".join(lines)
