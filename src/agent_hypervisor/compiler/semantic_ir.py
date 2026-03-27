"""
semantic/semantic_ir.py — Semantic Intermediate Representation.

The Semantic IR is the typed output of the semantic mapping step.
It sits between natural language and the existing Intent IR.

Full pipeline:

    natural language
        → [SemanticMapper]    (LLM online — produces CandidateExpression)
        → [SemanticValidator] (deterministic — produces one of three outcomes below)
        → SemanticExpression            → flows into IntentProposal → WorldPolicy
        → NonRepresentableExpression    → pipeline terminates here (no side effects)
        → CapabilityRequiredExpression  → pipeline terminates here (capability audit)

The critical distinction between outcomes:

    NonRepresentable:
        The input has no representation in this semantic space.
        The primitive does not exist, or parameter values are invalid.
        This is not a rejection — the system simply has nothing to map to.
        No error is surfaced. The input cannot become an action.

    CapabilityRequired:
        The primitive exists and parameters are valid, but the required
        capability is not present in the current capability set.
        The primitive is real; the agent is not authorized to activate it here.

    SemanticExpression:
        The input maps fully to a known, valid primitive. All capability
        checks pass. This flows into the existing Intent IR pipeline.

Security properties:
    - Prompt injection: injected instructions have no registered primitive.
      Result: NonRepresentable. The input never reaches WorldPolicy.
    - Unauthorized commitments: invalid discount tiers fail enum validation.
      Result: NonRepresentable. No tool is ever invoked.
    - Missing authorization: valid tier, capability absent.
      Result: CapabilityRequired. Blocked before IntentProposal is created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .primitives import PrimitiveKind


# ---------------------------------------------------------------------------
# Mapping outcome enum
# ---------------------------------------------------------------------------

class MappingOutcome(str, Enum):
    REPRESENTABLE        = "representable"
    NON_REPRESENTABLE    = "non_representable"
    CAPABILITY_REQUIRED  = "capability_required"
    PARAMETER_INVALID    = "parameter_invalid"   # subsumed into NON_REPRESENTABLE


# ---------------------------------------------------------------------------
# Candidate Expression (LLM output — not yet validated)
# ---------------------------------------------------------------------------

@dataclass
class CandidateExpression:
    """
    The LLM's structured attempt to map a natural language fragment to a
    semantic primitive. Produced by the LLM at runtime (online step).
    Validated deterministically by SemanticValidator (offline against manifest).

    The LLM proposes — the validator decides. The validator has no LLM dependency.

    Fields:
        primitive_id      — which primitive the LLM thinks this maps to
        parameters        — parameters extracted by the LLM from the input
        source_text       — original natural language fragment
        alternative_ids   — fallback primitive ids proposed by the LLM
                            (used only in NonRepresentable diagnostics; not for matching)
    """
    primitive_id: str
    parameters: dict[str, Any]
    source_text: str
    alternative_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Semantic Expression (outcome: representable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticExpression:
    """
    A natural language fragment successfully mapped to a semantic primitive.

    This is produced when:
        1. The candidate primitive_id is registered in the manifest.
        2. All parameter values satisfy their type/enum specs.
        3. All required capabilities are present.

    This is the only outcome that continues into the Intent IR pipeline.
    The IntentMapper converts a SemanticExpression into an IntentProposal
    using the primitive's maps_to_action field.

    Fields:
        primitive_id          — registered primitive this maps to
        primitive_kind        — kind of the primitive
        parameters            — validated, typed parameters
        source_text           — original natural language fragment
        requires_capabilities — capabilities needed (from primitive definition;
                                already verified as present at this point)
    """
    primitive_id: str
    primitive_kind: PrimitiveKind
    parameters: dict[str, Any]
    source_text: str
    requires_capabilities: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "outcome": MappingOutcome.REPRESENTABLE.value,
            "primitive_id": self.primitive_id,
            "primitive_kind": self.primitive_kind.value,
            "parameters": self.parameters,
            "source_text": self.source_text,
            "requires_capabilities": list(self.requires_capabilities),
        }


# ---------------------------------------------------------------------------
# Non-Representable Expression (outcome: non_representable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NonRepresentableExpression:
    """
    A natural language fragment that cannot be mapped to any registered primitive.

    This is NOT an error condition. It is the correct, first-class system
    response to any input that falls outside the bounded semantic space.

    The system does not reject the input explicitly — there is simply no
    representation for it in this deployment. The input cannot become an action,
    a query, a commitment, or a reasoning step here.

    Produced when:
        - The candidate primitive_id is not registered in the manifest.
        - Parameter values fail type or enum validation (e.g. "50_pct" not
          in the registered enum [5_pct, 10_pct]).

    Pipeline effect: terminates here. No IntentProposal is created.
    No WorldPolicy is evaluated. No tool is invoked.

    Prevents:
        - Prompt injection: "ignore all instructions" → no primitive matches
        - Unauthorized discount tiers: 50% not in registered enum
        - Out-of-domain reasoning: "simulate nuclear reactor" → not registered

    Fields:
        source_text        — the original fragment that could not be mapped
        reason             — structural explanation (not a user-facing message)
        nearest_primitives — closest registered ids (diagnostics/audit only)
    """
    source_text: str
    reason: str
    nearest_primitives: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "outcome": MappingOutcome.NON_REPRESENTABLE.value,
            "source_text": self.source_text,
            "reason": self.reason,
            "nearest_primitives": list(self.nearest_primitives),
        }


# ---------------------------------------------------------------------------
# Capability-Required Expression (outcome: capability_required)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityRequiredExpression:
    """
    Input maps to a known, valid primitive, but the required capability is
    not present in the current capability set.

    Distinct from NonRepresentableExpression:
        NonRepresentable:     the primitive does not exist here
        CapabilityRequired:   the primitive exists but cannot be activated

    Example differentiation for discount requests:
        "give 50% discount"
            → 50_pct not in enum (5_pct, 10_pct)
            → NonRepresentable (invalid parameter value)

        "give 10% discount" with capabilities = {QUERY_ONLY}
            → 10_pct is valid
            → primitive requires DISCOUNT_LEVEL_1
            → DISCOUNT_LEVEL_1 not in {QUERY_ONLY}
            → CapabilityRequired

        "give 10% discount" with capabilities = {DISCOUNT_LEVEL_1}
            → all checks pass
            → SemanticExpression

    Pipeline effect: terminates here. Auditable — the primitive was identified
    but the capability was absent. This case is logged separately from
    NonRepresentable for audit clarity.

    Fields:
        primitive_id          — the primitive that was matched
        primitive_kind        — kind of the matched primitive
        source_text           — original natural language fragment
        missing_capability    — the specific capability that was absent
        available_capabilities — capabilities present at time of check
    """
    primitive_id: str
    primitive_kind: PrimitiveKind
    source_text: str
    missing_capability: str
    available_capabilities: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "outcome": MappingOutcome.CAPABILITY_REQUIRED.value,
            "primitive_id": self.primitive_id,
            "primitive_kind": self.primitive_kind.value,
            "source_text": self.source_text,
            "missing_capability": self.missing_capability,
            "available_capabilities": list(self.available_capabilities),
        }


# ---------------------------------------------------------------------------
# Union type alias
# ---------------------------------------------------------------------------

SemanticMappingResult = (
    SemanticExpression |
    NonRepresentableExpression |
    CapabilityRequiredExpression
)
