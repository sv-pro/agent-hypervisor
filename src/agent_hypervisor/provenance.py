"""
provenance.py — Provenance chain utilities.

Provenance is the record of where a value came from and how it was
transformed before it arrived at the tool execution boundary.

Key concepts:

  ValueRef         — value + provenance class + roles + parent chain
  resolve_chain()  — walk the derivation DAG to collect all ancestors
  mixed_provenance() — detect when a value has ancestors from multiple
                        trust levels (indicates blended/laundered provenance)

Trust ordering (least → most trusted):
  external_document < derived < user_declared < system

A derived value inherits the least-trusted provenance class among its
parents (RULE-03: provenance is sticky).
"""

from __future__ import annotations

from .models import ProvenanceClass, ValueRef


# Trust ordering — lower index = less trusted.
_TRUST_ORDER: list[ProvenanceClass] = [
    ProvenanceClass.external_document,
    ProvenanceClass.derived,
    ProvenanceClass.user_declared,
    ProvenanceClass.system,
]


def resolve_chain(ref: ValueRef, registry: dict[str, ValueRef]) -> list[ValueRef]:
    """
    Walk the derivation DAG and return all ancestors of ref (including ref).

    The result is in BFS order starting from ref. Cycles are silently broken
    (they should not occur in a well-formed derivation DAG).

    Args:
        ref:      The ValueRef whose ancestry should be resolved.
        registry: Mapping from ValueRef.id to ValueRef for all known values.

    Returns:
        List of ValueRef instances (ref first, then ancestors in visit order).
    """
    seen: set[str] = set()
    result: list[ValueRef] = []

    def walk(r: ValueRef) -> None:
        if r.id in seen:
            return
        seen.add(r.id)
        result.append(r)
        for pid in r.parents:
            parent = registry.get(pid)
            if parent:
                walk(parent)

    walk(ref)
    return result


def least_trusted(classes: list[ProvenanceClass]) -> ProvenanceClass:
    """
    Return the least-trusted provenance class among a list.

    Used to compute effective provenance of a derived value from its parents.
    """
    if not classes:
        return ProvenanceClass.external_document
    return min(classes, key=lambda c: _TRUST_ORDER.index(c))


def mixed_provenance(ref: ValueRef, registry: dict[str, ValueRef]) -> bool:
    """
    Return True if the provenance chain of ref contains values from more than
    one distinct provenance class.

    Mixed provenance indicates that a value's ancestry includes sources of
    different trust levels — e.g. data derived from both an external document
    and a user_declared input. This is a signal for heightened scrutiny because
    the less-trusted source dominates (RULE-03), yet the presence of a trusted
    source may be used to falsely imply legitimacy.

    Example:
        ref (derived)
          ├── external_doc (external_document)  ← untrusted
          └── contacts (user_declared)           ← trusted
        → mixed_provenance returns True
    """
    chain = resolve_chain(ref, registry)
    classes = {v.provenance for v in chain}
    return len(classes) > 1


def provenance_summary(ref: ValueRef, registry: dict[str, ValueRef]) -> str:
    """
    Return a human-readable summary of the provenance chain for ref.

    Format: "derived:label <- external_document:source <- ..."
    Useful for trace logging and audit output.
    """
    chain = resolve_chain(ref, registry)
    labels = [
        f"{v.provenance.value}:{v.source_label or v.id}"
        for v in chain
    ]
    return " <- ".join(labels)
