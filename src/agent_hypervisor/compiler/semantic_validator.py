"""
semantic/semantic_validator.py — Runtime semantic validator (deterministic).

The SemanticValidator maps a CandidateExpression (produced upstream by the LLM)
against the registered primitives in the Semantic Manifest.

IMPORTANT: This validator contains no LLM. It is fully deterministic.
The LLM's role ends when it produces a structured CandidateExpression.
From that point, only exact manifest lookup and type checking apply.

This is the semantic-space equivalent of Layer 4 (World Policy):
    Layer 4 (World Policy):     "does this action exist? is it permitted?"
    SemanticValidator:          "does this meaning exist? is it activatable?"

Validation algorithm (ordered, fail-closed):

    1. Primitive lookup
       Is candidate.primitive_id registered in the manifest?
       No  → NonRepresentableExpression (ontological absence)

    2. Parameter validation
       Do candidate.parameters satisfy all ParameterSpec constraints?
       No  → NonRepresentableExpression (invalid expression in this space)

    3. Capability check
       Are all primitive.requires_capabilities present in available_capabilities?
       No  → CapabilityRequiredExpression (primitive real, capability absent)

    4. Pass
       → SemanticExpression (flows into Intent IR pipeline)

The validator is instantiated per-request with the current capability set.
The manifest is immutable and can be shared across requests.

Invariants upheld:
    I-4 (Determinism): Same candidate + same manifest + same capabilities
                       always produce the same outcome.
    I-1 (Input):       Validation operates on structured CandidateExpression,
                       not raw natural language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .primitives import PrimitiveKind
from .semantic_ir import (
    CandidateExpression,
    CapabilityRequiredExpression,
    MappingOutcome,
    NonRepresentableExpression,
    SemanticExpression,
    SemanticMappingResult,
)
from .semantic_manifest import SemanticManifest


class SemanticValidator:
    """
    Deterministic runtime validator for semantic expressions.

    The validator has no LLM dependency. It takes a CandidateExpression
    (produced upstream by the LLM) and deterministically classifies it as:
        SemanticExpression            — representable, all checks pass
        CapabilityRequiredExpression  — primitive exists, capability absent
        NonRepresentableExpression    — no matching primitive or invalid params

    Same input always produces same output (Invariant I-4: Determinism).

    Usage:
        manifest = load_semantic_manifest("manifests/examples/customer_support_semantic.yaml")
        validator = SemanticValidator(manifest, available_capabilities={"QUERY_ONLY"})
        result = validator.validate(candidate)
    """

    def __init__(
        self,
        manifest: SemanticManifest,
        available_capabilities: set[str] | None = None,
    ) -> None:
        self._manifest = manifest
        self._capabilities: frozenset[str] = frozenset(available_capabilities or set())
        # Build O(1) lookup index for high-frequency use
        self._index: dict[str, Any] = manifest.build_index()

    def validate(self, candidate: CandidateExpression) -> SemanticMappingResult:
        """
        Deterministically validate a candidate semantic expression.

        Returns one of:
            SemanticExpression            (all checks pass)
            NonRepresentableExpression    (primitive absent or params invalid)
            CapabilityRequiredExpression  (primitive valid, capability missing)
        """
        # Step 1: Primitive must be registered in the manifest
        primitive = self._index.get(candidate.primitive_id)
        if primitive is None:
            return NonRepresentableExpression(
                source_text=candidate.source_text,
                reason=(
                    f"Primitive '{candidate.primitive_id}' is not registered "
                    f"in semantic manifest '{self._manifest.name}'. "
                    f"Input has no representation in this semantic space."
                ),
                nearest_primitives=tuple(candidate.alternative_ids[:3]),
            )

        # Step 2: Parameter values must satisfy all type/enum constraints
        errors = primitive.validate_parameters(candidate.parameters)
        if errors:
            return NonRepresentableExpression(
                source_text=candidate.source_text,
                reason=f"Parameter validation failed: {'; '.join(errors)}",
                nearest_primitives=(primitive.id,),
            )

        # Step 3: All required capabilities must be present
        for cap in primitive.requires_capabilities:
            if cap not in self._capabilities:
                return CapabilityRequiredExpression(
                    primitive_id=primitive.id,
                    primitive_kind=primitive.kind,
                    source_text=candidate.source_text,
                    missing_capability=cap,
                    available_capabilities=tuple(sorted(self._capabilities)),
                )

        # All checks pass → representable
        return SemanticExpression(
            primitive_id=primitive.id,
            primitive_kind=primitive.kind,
            parameters=dict(candidate.parameters),
            source_text=candidate.source_text,
            requires_capabilities=primitive.requires_capabilities,
        )

    def validate_batch(
        self, candidates: list[CandidateExpression]
    ) -> list[SemanticMappingResult]:
        """Validate a list of candidates. Results are in the same order as input."""
        return [self.validate(c) for c in candidates]
