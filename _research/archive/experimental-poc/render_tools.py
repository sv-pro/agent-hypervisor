"""render_tools.py – project a compiled manifest into rendered tool descriptors.

Rendered tools are the agent-facing capability surface derived from the manifest.
Each allowed_action entry in the manifest becomes exactly one RenderedTool.

No-expansion invariant:
    Rendered tools may only be derived from manifest allowed_actions.
    They must never introduce capabilities not already present in the manifest.
    The renderer never touches denied_actions; absent capabilities are simply
    not exposed as tools.

Conceptual dispatch contract (informational – dispatcher not implemented here):
    1. Look up the RenderedTool by name.
    2. Apply fixed_args before forwarding to the base_tool.
    3. Enforce allowed_resource_patterns before dispatch.
    4. Check trust_required and taint_ok against the live step context.
    Actual dispatch is left to the enforcement engine (policy/engine.py).

This module is a minimal bridge from policy enforcement to capability rendering.
It is intentionally small: representing the architectural idea, not building
the full platform.
"""

from __future__ import annotations

# Rendered tools represent the ontology layer:
# capabilities that do not exist here cannot be invoked by the agent.

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RenderedTool:
    """A narrowed, agent-facing tool descriptor derived from a manifest capability.

    Each field encodes a constraint inherited from the manifest allowed_action entry.
    A RenderedTool is an executable capability descriptor: not just metadata, but
    a narrowed representation of what the agent is permitted to do.

    No-expansion invariant: every RenderedTool must trace back to a single
    allowed_action entry in the source manifest.  The renderer never introduces
    capabilities absent from the manifest.
    """

    name: str                            # deterministic, human-readable identifier
    base_tool: str                       # underlying tool this renders (from manifest action)
    action: str                          # action identifier (same as base_tool in this PoC)
    description: str                     # brief human-readable description
    input_schema: dict[str, Any]         # minimal schema for allowed inputs
    fixed_args: dict[str, str]           # args pre-applied before dispatch
    allowed_resource_patterns: list[str] # resource constraints preserved from manifest
    trust_required: str                  # minimum trust level required
    taint_ok: bool                       # whether tainted input is tolerated

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (e.g. for YAML output)."""
        return {
            "name": self.name,
            "base_tool": self.base_tool,
            "action": self.action,
            "description": self.description,
            "input_schema": self.input_schema,
            "fixed_args": self.fixed_args,
            "allowed_resource_patterns": self.allowed_resource_patterns,
            "trust_required": self.trust_required,
            "taint_ok": self.taint_ok,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Known resource-pattern-to-suffix mappings.
# Extend this table to cover new resource schemes without touching render logic.
_RESOURCE_SUFFIX_MAP: dict[str, str] = {
    "repo://local":          "repo_only",
    "repo://remote/origin":  "origin_only",
    "repo://remote":         "remote_only",
    "shell://local":         "local_only",
    "env://":                "env_only",
    "external://":           "external_only",
}


def _resource_suffix(pattern: str) -> str:
    """Derive a short, readable suffix from a resource pattern.

    Strips trailing wildcard segments, checks the known-suffix table,
    and falls back to a sanitised snake_case representation.
    """
    p = pattern.rstrip("/*").rstrip("/")
    if p in _RESOURCE_SUFFIX_MAP:
        return _RESOURCE_SUFFIX_MAP[p]
    # Fallback: sanitise the stripped URI to snake_case and append _only.
    sanitised = re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_")
    return f"{sanitised}_only"


def _make_name(action: str, patterns: list[str]) -> str:
    """Build a deterministic, readable tool name from action and resource patterns.

    Uses the first (most specific) resource pattern as the suffix source.
    Result is always a valid Python identifier: lowercase, underscore-separated.
    """
    suffix = _resource_suffix(patterns[0]) if patterns else "any"
    return f"{action}_{suffix}"


def _fixed_args_for(patterns: list[str]) -> dict[str, str]:
    """Extract fixed arguments implied by the resource pattern.

    These are args that are pre-determined by the manifest constraint and
    must be applied before dispatching to the base tool.

    Examples:
        repo://remote/origin/*  →  {"remote": "origin"}
        repo://local/*          →  {}
        shell://local           →  {}
    """
    if not patterns:
        return {}
    p = patterns[0].rstrip("/*").rstrip("/")
    # repo://remote/<name>  →  remote=<name>
    if p.startswith("repo://remote/"):
        remote_name = p.split("/")[-1]
        # guard: don't emit {"remote": "remote"} for bare repo://remote
        if remote_name and remote_name != "remote":
            return {"remote": remote_name}
    return {}


def _input_schema_for(action: str) -> dict[str, Any]:
    """Minimal input schema for a rendered tool.

    Encodes the resource URI as the primary input.  In a full system this
    would be richer; for the PoC a single required 'resource' field suffices.
    """
    return {
        "type": "object",
        "properties": {
            "resource": {
                "type": "string",
                "description": f"Resource URI for {action}",
            },
        },
        "required": ["resource"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_tools(manifest: dict[str, Any]) -> list[RenderedTool]:
    """Project manifest allowed_actions into a list of RenderedTool descriptors.

    No-expansion invariant:
        Only entries in manifest["allowed_actions"] are rendered.
        Denied or absent capabilities are never exposed as tools.
        The count of returned tools equals the count of allowed_action entries.

    Args:
        manifest: a compiled World Manifest dict (as produced by compile_manifest).

    Returns:
        Ordered list of RenderedTool descriptors, one per allowed_action entry.
        Order matches the order of allowed_actions in the manifest.
    """
    # No-expansion: we read only allowed_actions.
    # denied_actions and approval_required are deliberately not consulted here;
    # they contain capabilities the manifest explicitly restricts, not enables.
    allowed = manifest.get("allowed_actions", [])
    tools: list[RenderedTool] = []

    for entry in allowed:
        action = entry["action"]
        patterns = list(entry.get("permitted_resources", []))
        trust_required = entry.get("trust_required", "trusted")
        taint_ok = bool(entry.get("taint_ok", False))

        name = _make_name(action, patterns)
        description = (
            f"Narrowed {action} capability restricted to: "
            + (", ".join(patterns) if patterns else "(no resource constraint)")
        )

        tools.append(RenderedTool(
            name=name,
            base_tool=action,
            action=action,
            description=description,
            input_schema=_input_schema_for(action),
            fixed_args=_fixed_args_for(patterns),
            allowed_resource_patterns=patterns,
            trust_required=trust_required,
            taint_ok=taint_ok,
        ))

    return tools
