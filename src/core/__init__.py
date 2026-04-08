"""
Public API for the core package.
Re-exports everything from hypervisor so consumers can do:

    from core import Hypervisor, WorldManifest, ...
"""

from core.hypervisor import (  # noqa: F401
    Decision,
    ExecutionMode,
    Hypervisor,
    InvariantViolation,
    ManifestResolver,
    ProposedAction,
    ProvenanceRecord,
    ResolutionResult,
    SemanticEvent,
    TrustLevel,
    WorldManifest,
    check_invariants,
)

__all__ = [
    "Decision",
    "ExecutionMode",
    "Hypervisor",
    "InvariantViolation",
    "ManifestResolver",
    "ProposedAction",
    "ProvenanceRecord",
    "ResolutionResult",
    "SemanticEvent",
    "TrustLevel",
    "WorldManifest",
    "check_invariants",
]
