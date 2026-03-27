"""Schema: dataclass definitions for world manifests and capability constraints."""

import fnmatch
from dataclasses import dataclass, field
from typing import Any

import jsonschema


@dataclass
class CapabilityConstraint:
    """Constraints on a single tool's use within a workflow."""

    tool: str
    constraints: dict[str, Any] = field(default_factory=dict)

    def allows(self, tool: str, params: dict[str, Any]) -> bool:
        """Return True if this constraint permits the given tool invocation."""
        if self.tool != tool:
            return False
        # path-based constraint check
        if "paths" in self.constraints and "path" in params:
            allowed = self.constraints["paths"]
            return any(fnmatch.fnmatch(params["path"], p) for p in allowed)
        # domain-based constraint check
        if "domains" in self.constraints and "domain" in params:
            return params["domain"] in self.constraints["domains"]
        # No constraints means allow any params for this tool
        return True


@dataclass
class WorldManifest:
    """Declarative boundary specification defining an agent's world."""

    workflow_id: str
    version: str = "1.0"
    capabilities: list[CapabilityConstraint] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def allows(self, tool: str, params: dict[str, Any] | None = None) -> bool:
        """Return True if any capability constraint permits this tool call."""
        params = params or {}
        return any(cap.allows(tool, params) for cap in self.capabilities)

    def tool_names(self) -> list[str]:
        """Return the list of permitted tool names."""
        return [cap.tool for cap in self.capabilities]


def manifest_to_dict(manifest: WorldManifest) -> dict:
    """Serialize a WorldManifest to a plain dict."""
    return {
        "workflow_id": manifest.workflow_id,
        "version": manifest.version,
        "capabilities": [
            {"tool": cap.tool, "constraints": cap.constraints}
            for cap in manifest.capabilities
        ],
        "metadata": manifest.metadata,
    }


def manifest_from_dict(data: dict) -> WorldManifest:
    """Deserialize a WorldManifest from a plain dict."""
    capabilities = [
        CapabilityConstraint(
            tool=cap["tool"],
            constraints=cap.get("constraints", {}),
        )
        for cap in data.get("capabilities", [])
    ]
    return WorldManifest(
        workflow_id=data["workflow_id"],
        version=data.get("version", "1.0"),
        capabilities=capabilities,
        metadata=data.get("metadata", {}),
    )


MANIFEST_JSON_SCHEMA = {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
        "workflow_id": {"type": "string"},
        "version": {"type": "string"},
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool"],
                "properties": {
                    "tool": {"type": "string"},
                    "constraints": {"type": "object"},
                },
            },
        },
        "metadata": {"type": "object"},
    },
}


def validate_manifest_dict(data: dict) -> None:
    """Validate a manifest dict against MANIFEST_JSON_SCHEMA.

    Raises jsonschema.ValidationError if the dict is invalid.
    """
    jsonschema.validate(data, MANIFEST_JSON_SCHEMA)
