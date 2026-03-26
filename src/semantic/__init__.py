"""
semantic/ — Bounded Semantic Space layer for the Agent Hypervisor.

This package introduces a second ontological boundary: where the World Manifest
bounds what actions *exist*, the Semantic Manifest bounds what *meanings* exist.

Pipeline position:

    natural language
        → [SemanticMapper]    (LLM, online — produces CandidateExpression)
        → [SemanticValidator] (deterministic — validates against SemanticManifest)
        → SemanticExpression | NonRepresentableExpression | CapabilityRequiredExpression
        → existing Intent IR / IntentProposal pipeline

Public API:

    from src.semantic.primitives import PrimitiveKind, SemanticPrimitive, ParameterSpec
    from src.semantic.semantic_ir import (
        SemanticExpression, NonRepresentableExpression, CapabilityRequiredExpression
    )
    from src.semantic.semantic_manifest import SemanticManifest, load_semantic_manifest
    from src.semantic.semantic_validator import SemanticValidator, CandidateExpression
    from src.semantic.semantic_compiler import SemanticCompiler, LLMExtractor

See: docs/SEMANTIC_SPACE.md
"""
