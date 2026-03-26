"""
semantic/semantic_manifest.py — Semantic Manifest model and YAML loader.

A Semantic Manifest is the design-time definition of a deployment's bounded
semantic space. It specifies which semantic primitives exist, their types,
parameters, and capability requirements.

Relationship to other manifests:
    World Manifest      → bounds actions (what tools exist)
    Semantic Manifest   → bounds meaning (what can be expressed)
    Capability Matrix   → bounds execution (what can run at each trust level)

Layering:
    An expression must first be representable (Semantic Manifest check) before
    it can be permitted (World Policy / Capability Matrix check).

Authoring:
    Manifests are authored at design-time using the SemanticCompiler (LLM-assisted
    offline extraction from workflow definitions). The resulting YAML is reviewed
    by a human and committed to version control.

Runtime:
    Loaded once at startup via load_semantic_manifest(). No LLM is involved
    after this point. All validation is deterministic.

See: manifests/semantic_manifest_schema.yaml for the annotated schema.
     docs/SEMANTIC_SPACE.md §5 for the compilation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .primitives import (
    ParameterSpec, ParameterType, PrimitiveKind, SemanticPrimitive,
)


# ---------------------------------------------------------------------------
# Semantic Manifest model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticManifest:
    """
    The complete semantic space definition for a deployment.

    Immutable after construction. Loaded from YAML at startup.
    All field access is O(n) by default; use build_index() if high-frequency
    lookup is required.

    Fields:
        name        — human identifier (e.g. "customer-support-semantic-space")
        version     — semver string (e.g. "1.0.0")
        description — optional purpose statement
        primitives  — registered semantic primitives (the bounded space)
    """
    name: str
    version: str
    primitives: tuple[SemanticPrimitive, ...] = field(default_factory=tuple)
    description: str = ""

    def get_primitive(self, primitive_id: str) -> SemanticPrimitive | None:
        """Return the primitive with the given id, or None if not registered."""
        for p in self.primitives:
            if p.id == primitive_id:
                return p
        return None

    def get_primitives_by_kind(self, kind: PrimitiveKind) -> list[SemanticPrimitive]:
        """Return all primitives of the given kind."""
        return [p for p in self.primitives if p.kind == kind]

    def primitive_ids(self) -> frozenset[str]:
        """Return the set of all registered primitive ids."""
        return frozenset(p.id for p in self.primitives)

    def build_index(self) -> dict[str, SemanticPrimitive]:
        """Return a dict for O(1) lookup. Use when validating high-volume input."""
        return {p.id: p for p in self.primitives}


# ---------------------------------------------------------------------------
# YAML parsing helpers
# ---------------------------------------------------------------------------

def _parse_parameter_spec(raw: dict[str, Any]) -> ParameterSpec:
    ptype = ParameterType(raw.get("type", "string"))
    enum_values: tuple[str, ...] = tuple(
        str(v) for v in raw.get("values", [])
    )
    return ParameterSpec(
        name=raw["name"],
        type=ptype,
        required=bool(raw.get("required", True)),
        enum_values=enum_values,
        description=raw.get("description", ""),
    )


def _parse_primitive(raw: dict[str, Any]) -> SemanticPrimitive:
    kind = PrimitiveKind(raw["kind"])
    params = tuple(
        _parse_parameter_spec(p) for p in raw.get("parameters", [])
    )
    return SemanticPrimitive(
        id=raw["id"],
        kind=kind,
        description=raw.get("description", ""),
        parameters=params,
        maps_to_action=raw.get("maps_to_action"),
        subtype=raw.get("subtype"),
        requires_capabilities=tuple(raw.get("requires_capabilities", [])),
        keywords=tuple(raw.get("keywords", [])),
    )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_semantic_manifest(path: str | Path) -> SemanticManifest:
    """
    Load and parse a Semantic Manifest from a YAML file.

    The file must conform to manifests/semantic_manifest_schema.yaml.
    Raises ValueError on missing required fields.
    Raises yaml.YAMLError on malformed YAML.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    # Support both top-level 'semantic_manifest:' wrapper and bare documents
    sm = data.get("semantic_manifest", data)

    if "name" not in sm or "version" not in sm:
        raise ValueError(f"Semantic manifest at '{path}' is missing required fields: name, version")

    primitives = tuple(
        _parse_primitive(p) for p in sm.get("primitives", [])
    )

    return SemanticManifest(
        name=sm["name"],
        version=sm["version"],
        description=sm.get("description", ""),
        primitives=primitives,
    )
