"""
intent_validator.py — Tool call validation against World Manifests.

Loads World Manifest YAML files (compiled at design time) and evaluates
proposed tool calls for:
  1. Ontology: does this tool exist in the manifest?
  2. Taint containment: does tainted context + external tool violate policy?

This is the "no LLM on the critical path" guarantee: all validation is
deterministic lookups against pre-compiled manifest data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from ah_defense.taint_tracker import TaintState


ToolType = Literal["read_only", "internal_write", "external_side_effect", "unknown"]


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating one tool call."""
    tool_name: str
    verdict: Literal["allow", "deny"]
    reason: str
    tool_type: ToolType


class IntentValidator:
    """
    Validates proposed tool calls against a World Manifest.

    The World Manifest is a YAML file that classifies each tool in a
    task suite into one of three categories:
      - read_only: no side effects (always allowed)
      - internal_write: modifies internal state (allowed unless policy says otherwise)
      - external_side_effect: communicates outside the virtual world (blocked when tainted)

    Usage:
        validator = IntentValidator.from_manifest("manifests/workspace.yaml")
        result = validator.validate("send_email", taint_state)
    """

    def __init__(self, tool_classifications: dict[str, ToolType]) -> None:
        self._classifications = tool_classifications

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "IntentValidator":
        """Load a World Manifest YAML file and create a validator."""
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        classifications: dict[str, ToolType] = {}
        for tool_type in ("read_only", "internal_write", "external_side_effect"):
            for tool_name in manifest.get(tool_type, []):
                classifications[tool_name] = tool_type  # type: ignore

        return cls(classifications)

    @classmethod
    def for_suite(cls, suite_name: str, manifests_dir: str | Path | None = None) -> "IntentValidator":
        """Load the manifest for a named AgentDojo suite."""
        if manifests_dir is None:
            manifests_dir = Path(__file__).parent / "manifests"
        manifest_path = Path(manifests_dir) / f"{suite_name}.yaml"
        if not manifest_path.exists():
            # Fallback: return a permissive validator that allows everything
            return cls({})
        return cls.from_manifest(manifest_path)

    def get_tool_type(self, tool_name: str) -> ToolType:
        """Return the type of a tool, or 'unknown' if not in the manifest."""
        return self._classifications.get(tool_name, "unknown")

    def validate(self, tool_name: str, taint_state: TaintState) -> ValidationResult:
        """
        Validate a proposed tool call against the manifest and taint state.

        Args:
            tool_name: The tool being proposed.
            taint_state: Current session taint state.

        Returns:
            ValidationResult with verdict="allow" or verdict="deny".
        """
        tool_type = self.get_tool_type(tool_name)

        # Unknown tools are treated as potentially external — allow but note
        # (In v1 we don't block unknown tools to preserve utility;
        #  a production manifest would be exhaustive.)
        if tool_type == "unknown":
            # Conservative: treat unknown as external_side_effect for taint
            effective_type: ToolType = "external_side_effect"
        else:
            effective_type = tool_type

        blocked = taint_state.check_tool_call(tool_name, effective_type)

        if blocked:
            return ValidationResult(
                tool_name=tool_name,
                verdict="deny",
                reason=(
                    f"TaintContainmentLaw: tool '{tool_name}' has type "
                    f"'{effective_type}' and tainted context is present. "
                    "External side-effect blocked to prevent prompt injection exfiltration."
                ),
                tool_type=effective_type,
            )

        return ValidationResult(
            tool_name=tool_name,
            verdict="allow",
            reason=f"Tool '{tool_name}' ({effective_type}) permitted with current taint state",
            tool_type=effective_type,
        )
