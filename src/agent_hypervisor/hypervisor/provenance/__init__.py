"""
Provenance chain utilities re-exported for hypervisor.provenance package.

resolve_chain()      — walk the derivation DAG to collect all ancestors
least_trusted()      — compute effective trust level from a list of classes
mixed_provenance()   — detect blended/laundered provenance in a chain
provenance_summary() — human-readable chain for audit logs

The ProvenanceGraph (append-only audit graph) is in provenance.graph.
"""

from __future__ import annotations

from ..models import ProvenanceClass, ValueRef  # noqa: F401

_TRUST_ORDER: list[ProvenanceClass] = [
    ProvenanceClass.external_document,
    ProvenanceClass.derived,
    ProvenanceClass.user_declared,
    ProvenanceClass.system,
]


def resolve_chain(ref: ValueRef, registry: dict[str, ValueRef]) -> list[ValueRef]:
    """Walk the derivation DAG and return all ancestors of ref (including ref)."""
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
    """Return the least-trusted provenance class among a list."""
    if not classes:
        return ProvenanceClass.external_document
    return min(classes, key=lambda c: _TRUST_ORDER.index(c))


def mixed_provenance(ref: ValueRef, registry: dict[str, ValueRef]) -> bool:
    """Return True if the provenance chain contains values from more than one class."""
    chain = resolve_chain(ref, registry)
    return len({v.provenance for v in chain}) > 1


def provenance_summary(ref: ValueRef, registry: dict[str, ValueRef]) -> str:
    """Return a human-readable derivation path: 'derived:label <- external_document:src'."""
    chain = resolve_chain(ref, registry)
    labels = [f"{v.provenance.value}:{v.source_label or v.id}" for v in chain]
    return " <- ".join(labels)


__all__ = [
    "resolve_chain",
    "least_trusted",
    "mixed_provenance",
    "provenance_summary",
]
