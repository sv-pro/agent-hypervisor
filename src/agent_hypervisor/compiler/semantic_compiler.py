"""
semantic/semantic_compiler.py — Design-time Semantic Manifest compiler.

The SemanticCompiler operates OFFLINE (design-time only). It uses an LLM
to extract semantic patterns from workflow definitions and propose primitives.
The output is a draft Semantic Manifest YAML that a human reviews before
committing to version control.

Pipeline:
    workflow_definitions (text/YAML)
        → extract_patterns()        — LLM reads workflows, identifies intent patterns
        → propose_primitives()      — LLM canonicalizes, deduplicates, assigns kinds
        → generate_edge_cases()     — LLM generates adversarial inputs per primitive
        → emit CompilerOutput       — draft YAML + warnings + edge case report

Runtime:
    The compiler is NOT present at runtime. Its output (the manifest YAML) is
    loaded once at startup by load_semantic_manifest(). All runtime validation
    is deterministic and LLM-free.

LLM Extractor:
    The LLM dependency is injected via the LLMExtractor protocol. This makes the
    compiler independently testable with a stub extractor and decouples it from
    any specific LLM client (Anthropic, OpenAI, etc.).

Usage:
    extractor = MyAnthropicExtractor(client)
    compiler = SemanticCompiler(extractor)
    output = compiler.compile(
        workflow_texts=["customer asks for refund...", "customer tracks order..."],
        manifest_name="customer-support-semantic-space",
    )
    import yaml
    yaml.dump(output.to_yaml_dict(), open("semantic.yaml", "w"), default_flow_style=False)

See: docs/SEMANTIC_SPACE.md §6 (Design-Time Compilation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .primitives import (
    ParameterSpec, ParameterType, PrimitiveKind, SemanticPrimitive,
)
from .semantic_manifest import SemanticManifest


# ---------------------------------------------------------------------------
# LLM Extractor Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMExtractor(Protocol):
    """
    Protocol for LLM-based pattern extraction.

    Implement this interface with your LLM client.
    The SemanticCompiler calls these three methods; the implementation
    handles prompt construction, API calls, and response parsing.

    All methods are called offline (design-time only). None are called
    during runtime semantic validation.
    """

    def extract_patterns(self, workflow_text: str) -> list[dict]:
        """
        Given a workflow definition (free text or YAML), return a list of
        semantic pattern dicts found in the workflow.

        Each dict should have:
            {
                "intent": str,           # human description of the intent
                "kind": str,             # action_intent | query_intent |
                                         # commitment | reasoning_pattern
                "parameters": [          # extracted parameter hints
                    {"name": str, "type": str, "values": [...]}
                ],
                "keywords": [str],       # surface-form phrases that trigger this intent
                "example": str           # verbatim example from the workflow
            }
        """
        ...

    def propose_primitives(
        self, patterns: list[dict], existing_ids: set[str]
    ) -> list[dict]:
        """
        Given extracted patterns, propose canonical, deduplicated primitives.

        Each dict should conform to the SemanticPrimitive structure:
            {
                "id": str,
                "kind": str,
                "description": str,
                "subtype": str | None,
                "parameters": [...],
                "maps_to_action": str | None,
                "requires_capabilities": [str],
                "keywords": [str]
            }

        existing_ids is the set of already-committed primitive ids.
        The LLM should avoid proposing duplicates.
        """
        ...

    def generate_edge_cases(self, primitive: dict) -> list[str]:
        """
        Given a primitive definition, generate adversarial input strings
        that should NOT map to this primitive (for boundary testing).

        Returns a list of natural language strings:
            - Inputs that look similar but differ in one parameter value
            - Inputs that attempt to exceed authorized limits
            - Injected instructions framed as this intent
        """
        ...


# ---------------------------------------------------------------------------
# Compiler data types
# ---------------------------------------------------------------------------

@dataclass
class PatternSet:
    """Extracted semantic patterns from a single workflow text."""
    patterns: list[dict] = field(default_factory=list)
    workflow_source: str = ""
    raw_text_length: int = 0


@dataclass
class EdgeCaseReport:
    """
    Result of edge case generation for one primitive.

    adversarial_inputs: inputs that should definitively NOT map to this primitive
    boundary_inputs:    inputs that are genuinely ambiguous (require human review)

    The compiler populates adversarial_inputs from the LLM output.
    boundary_inputs must be classified by human review during manifest review.
    """
    primitive_id: str
    adversarial_inputs: list[str] = field(default_factory=list)
    boundary_inputs: list[str] = field(default_factory=list)


@dataclass
class CompilerOutput:
    """
    Full output of one design-time compilation run.

    manifest:            the draft SemanticManifest (ready for human review)
    edge_case_reports:   per-primitive adversarial input lists
    warnings:            non-fatal issues encountered during compilation
                         (e.g. malformed LLM proposals, missing maps_to_action)
    """
    manifest: SemanticManifest
    edge_case_reports: list[EdgeCaseReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_yaml_dict(self) -> dict:
        """
        Produce the dict that serializes to a valid Semantic Manifest YAML.
        The output conforms to manifests/semantic_manifest_schema.yaml.
        """
        primitives: list[dict] = []
        for p in self.manifest.primitives:
            pdict: dict[str, Any] = {
                "id": p.id,
                "kind": p.kind.value,
                "description": p.description,
            }
            if p.subtype:
                pdict["subtype"] = p.subtype
            if p.parameters:
                pdict["parameters"] = [
                    {
                        "name": param.name,
                        "type": param.type.value,
                        "required": param.required,
                        **({"values": list(param.enum_values)} if param.enum_values else {}),
                        **({"description": param.description} if param.description else {}),
                    }
                    for param in p.parameters
                ]
            if p.maps_to_action:
                pdict["maps_to_action"] = p.maps_to_action
            if p.requires_capabilities:
                pdict["requires_capabilities"] = list(p.requires_capabilities)
            if p.keywords:
                pdict["keywords"] = list(p.keywords)
            primitives.append(pdict)

        return {
            "semantic_manifest": {
                "name": self.manifest.name,
                "version": self.manifest.version,
                "description": self.manifest.description,
                "primitives": primitives,
            }
        }


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class SemanticCompiler:
    """
    Design-time compiler: extracts semantic primitives from workflow definitions.

    The compiler orchestrates three LLM calls per compilation run:
        1. extract_patterns  — what intents appear in these workflows?
        2. propose_primitives — canonicalize into typed SemanticPrimitives
        3. generate_edge_cases — what inputs should NOT trigger each primitive?

    The LLM is used only here (offline). The output YAML is the artifact that
    matters — it is reviewed by a human and committed to version control.
    """

    def __init__(self, extractor: LLMExtractor) -> None:
        self._extractor = extractor

    def compile(
        self,
        workflow_texts: list[str],
        manifest_name: str,
        version: str = "1.0.0",
        description: str = "",
    ) -> CompilerOutput:
        """
        Full design-time compilation pipeline.

            1. Extract semantic patterns from each workflow text.
            2. Propose and deduplicate canonical primitives.
            3. Generate adversarial edge cases per primitive.
            4. Return CompilerOutput with draft manifest + warnings.

        Args:
            workflow_texts: list of workflow definition strings (free text or YAML)
            manifest_name:  name field for the resulting SemanticManifest
            version:        semver string for the manifest
            description:    one-line purpose statement
        """
        # Step 1: Extract patterns from all workflow texts
        all_patterns: list[dict] = []
        for text in workflow_texts:
            pattern_set = self._extract_patterns(text)
            all_patterns.extend(pattern_set.patterns)

        # Step 2: Propose canonical primitives (LLM deduplicates and normalizes)
        existing_ids: set[str] = set()
        raw_primitives = self._extractor.propose_primitives(all_patterns, existing_ids)

        primitives: list[SemanticPrimitive] = []
        warnings: list[str] = []
        edge_reports: list[EdgeCaseReport] = []

        # Step 3: Parse, validate, and generate edge cases per primitive
        for raw in raw_primitives:
            try:
                prim = _parse_raw_primitive(raw)
            except (KeyError, ValueError) as exc:
                warnings.append(f"Skipped malformed primitive proposal '{raw.get('id', '?')}': {exc}")
                continue

            # Warn on action_intent/commitment without maps_to_action
            if prim.kind in (PrimitiveKind.ACTION_INTENT, PrimitiveKind.COMMITMENT):
                if not prim.maps_to_action:
                    warnings.append(
                        f"Primitive '{prim.id}' (kind={prim.kind.value}) "
                        f"has no maps_to_action. It cannot invoke a World Manifest tool."
                    )

            primitives.append(prim)

            adversarial = self._extractor.generate_edge_cases(raw)
            edge_reports.append(EdgeCaseReport(
                primitive_id=prim.id,
                adversarial_inputs=adversarial,
            ))

        manifest = SemanticManifest(
            name=manifest_name,
            version=version,
            description=description,
            primitives=tuple(primitives),
        )

        return CompilerOutput(
            manifest=manifest,
            edge_case_reports=edge_reports,
            warnings=warnings,
        )

    def _extract_patterns(self, workflow_text: str) -> PatternSet:
        patterns = self._extractor.extract_patterns(workflow_text)
        return PatternSet(
            patterns=patterns,
            workflow_source=workflow_text[:80],
            raw_text_length=len(workflow_text),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_raw_primitive(raw: dict) -> SemanticPrimitive:
    """Parse a raw dict (from LLM proposal) into a typed SemanticPrimitive."""
    kind = PrimitiveKind(raw["kind"])
    params: list[ParameterSpec] = []
    for p in raw.get("parameters", []):
        ptype = ParameterType(p.get("type", "string"))
        enum_values = tuple(str(v) for v in p.get("values", []))
        params.append(ParameterSpec(
            name=p["name"],
            type=ptype,
            required=bool(p.get("required", True)),
            enum_values=enum_values,
            description=p.get("description", ""),
        ))
    return SemanticPrimitive(
        id=raw["id"],
        kind=kind,
        description=raw.get("description", ""),
        parameters=tuple(params),
        maps_to_action=raw.get("maps_to_action"),
        subtype=raw.get("subtype"),
        requires_capabilities=tuple(raw.get("requires_capabilities", [])),
        keywords=tuple(raw.get("keywords", [])),
    )
