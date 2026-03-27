"""
semantic/primitives.py — Semantic Primitive type definitions.

A Semantic Primitive is an atomic unit of expressible meaning.
The Semantic Manifest registers which primitives exist for a given deployment.
Anything not representable as a registered primitive cannot exist in the system.

Four primitive kinds:
    action_intent      — intent to invoke a state-changing action
    query_intent       — intent to read or inspect state (no side effects)
    commitment         — a binding promise, guarantee, or quantified offer
    reasoning_pattern  — a structured cognitive operation (shapes reasoning, no tool call)

Design note: this module has zero dependencies on policy or compiler code.
It is a pure data model. All validation is deterministic and self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Primitive kinds
# ---------------------------------------------------------------------------

class PrimitiveKind(str, Enum):
    """
    The four fundamental categories of semantic primitives.

    These are exhaustive — any expressible meaning in the system must be one
    of these four kinds. Expressions that are not classifiable into a kind
    are not registered and therefore non-representable.
    """

    ACTION_INTENT = "action_intent"
    # Intent to invoke a state-changing action.
    # Must map to a tool registered in the World Manifest (maps_to_action required).
    # Example: "initiate a return for order ORD-123"

    QUERY_INTENT = "query_intent"
    # Intent to read or inspect state. No side effects.
    # Maps to read-only tools in the World Manifest.
    # Example: "what is the status of order ORD-123?"

    COMMITMENT = "commitment"
    # Intent to make a binding promise, guarantee, or quantified offer.
    # Subtypes: discount, deadline, guarantee, sla, refund.
    # These are the most tightly controlled primitives — each requires
    # explicit capability authorization. An unauthorized commitment tier
    # (e.g. 50% discount when only 5%/10% are registered) is NonRepresentable.
    # Example: "apply a 10% discount to order ORD-123"

    REASONING_PATTERN = "reasoning_pattern"
    # A structured cognitive operation.
    # Subtypes: compare, summarize, hypothesize, classify, plan.
    # Does not directly invoke a tool, but shapes how the agent reasons
    # before forming action intents. Restricts the *form* of reasoning,
    # not just the output.
    # Example: "compare the two shipping options by price"


# ---------------------------------------------------------------------------
# Parameter types and specs
# ---------------------------------------------------------------------------

class ParameterType(str, Enum):
    STRING  = "string"
    INTEGER = "integer"
    FLOAT   = "float"
    BOOLEAN = "boolean"
    ENUM    = "enum"
    OBJECT  = "object"
    ARRAY   = "array"


@dataclass(frozen=True)
class ParameterSpec:
    """
    Type-checked parameter specification for a semantic primitive.

    Validation is deterministic: same value always produces same result.
    The ENUM type is the key constraint for commitment primitives — only
    pre-registered values (e.g. specific discount tiers) are valid. Any
    value outside the enum is caught at parameter validation, making the
    expression NonRepresentable before it can reach the World Policy.
    """
    name: str
    type: ParameterType
    required: bool = True
    enum_values: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def validate(self, value: Any) -> tuple[bool, str]:
        """
        Deterministically validate a parameter value against this spec.
        Returns (is_valid, reason). Reason is empty string when valid.
        """
        if value is None:
            if self.required:
                return False, f"Required parameter '{self.name}' is missing"
            return True, ""

        if self.type == ParameterType.ENUM:
            str_value = str(value)
            if str_value not in self.enum_values:
                return False, (
                    f"Parameter '{self.name}' value '{value}' not in "
                    f"allowed set: {self.enum_values}"
                )

        elif self.type == ParameterType.FLOAT:
            try:
                float(value)
            except (TypeError, ValueError):
                return False, f"Parameter '{self.name}' must be numeric, got: {type(value).__name__}"

        elif self.type == ParameterType.INTEGER:
            try:
                int(value)
            except (TypeError, ValueError):
                return False, f"Parameter '{self.name}' must be an integer, got: {type(value).__name__}"

        elif self.type == ParameterType.BOOLEAN:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        return True, ""


# ---------------------------------------------------------------------------
# Semantic Primitive
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticPrimitive:
    """
    A registered unit of expressible meaning.

    Primitives are defined at design-time in the Semantic Manifest.
    At runtime, the SemanticValidator maps a CandidateExpression (from the LLM)
    against the registered set. Fragments not mappable to any primitive are
    NonRepresentable — they have no form in this deployment.

    Fields:
        id                    — unique identifier within the manifest
        kind                  — one of the four PrimitiveKind values
        description           — one-line human description (not used at runtime)
        parameters            — typed parameter specs (validated deterministically)
        maps_to_action        — World Manifest action this primitive invokes
                                (required for action_intent and commitment)
                                (absent for reasoning_pattern)
        subtype               — optional sub-classification
                                commitment: discount | guarantee | deadline | sla | refund
                                reasoning_pattern: compare | summarize | hypothesize |
                                                   classify | plan
        requires_capabilities — capabilities required to activate this primitive;
                                checked after parameter validation
        keywords              — design-time hints for the SemanticCompiler;
                                not used at runtime validation
    """
    id: str
    kind: PrimitiveKind
    description: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    maps_to_action: str | None = None
    subtype: str | None = None
    requires_capabilities: tuple[str, ...] = field(default_factory=tuple)
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def validate_parameters(self, params: dict[str, Any]) -> list[str]:
        """
        Validate a parameter dict against all specs for this primitive.
        Returns a list of error strings. Empty list means all parameters are valid.
        Deterministic: same input always produces same result.
        """
        errors: list[str] = []
        for spec in self.parameters:
            valid, reason = spec.validate(params.get(spec.name))
            if not valid:
                errors.append(reason)
        return errors
