"""Profile: derive minimal safe capability sets from execution traces."""

from .observe import ExecutionTrace, ToolCall
from .schema import CapabilityConstraint, WorldManifest


def _is_file_tool(tool: str) -> bool:
    return "read" in tool or "write" in tool or "file" in tool


def _is_web_tool(tool: str) -> bool:
    return "search" in tool or "fetch" in tool or "web" in tool


def profile_trace(trace: ExecutionTrace) -> list[CapabilityConstraint]:
    """Derive a minimal capability profile from an execution trace.

    Key invariants:
    - **Safe compression**: only safe=True calls contribute to the profile.
    - **No capability expansion**: no tool, path, or domain not observed in safe
      calls will appear in the returned constraints.

    For file-related tools (name contains "read", "write", or "file"), observed
    ``path`` params are collected into ``constraints["paths"]``.

    For web-related tools (name contains "search", "fetch", or "web"), observed
    ``domain`` params are collected into ``constraints["domains"]``.

    Other tools receive an empty constraints dict (allow any params).

    Args:
        trace: The execution trace to profile.

    Returns:
        List of CapabilityConstraint, one per unique tool observed in safe calls.
    """
    # Accumulate safe calls per tool
    safe_calls: dict[str, list[ToolCall]] = {}
    for call in trace.calls:
        if not call.safe:
            continue
        safe_calls.setdefault(call.tool, []).append(call)

    constraints: list[CapabilityConstraint] = []
    for tool, calls in safe_calls.items():
        if _is_file_tool(tool):
            paths = [
                call.params["path"]
                for call in calls
                if "path" in call.params
            ]
            constraints.append(CapabilityConstraint(tool=tool, constraints={"paths": paths}))
        elif _is_web_tool(tool):
            domains = [
                call.params["domain"]
                for call in calls
                if "domain" in call.params
            ]
            constraints.append(CapabilityConstraint(tool=tool, constraints={"domains": domains}))
        else:
            constraints.append(CapabilityConstraint(tool=tool, constraints={}))

    return constraints


def build_manifest(
    trace: ExecutionTrace,
    workflow_id: str | None = None,
) -> WorldManifest:
    """Build a WorldManifest from an execution trace.

    Calls :func:`profile_trace` to derive the capability set and wraps the
    result in a :class:`~agent_world_compiler.schema.WorldManifest`.

    Args:
        trace: The execution trace to compile.
        workflow_id: Override for the workflow identifier; defaults to
            ``trace.workflow_id``.

    Returns:
        A WorldManifest representing the minimal safe capability boundary.
    """
    capabilities = profile_trace(trace)
    return WorldManifest(
        workflow_id=workflow_id or trace.workflow_id,
        capabilities=capabilities,
        metadata=dict(trace.metadata),
    )
