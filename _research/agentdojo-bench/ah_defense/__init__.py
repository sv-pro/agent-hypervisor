"""
Agent Hypervisor defense for AgentDojo benchmark.

Implements taint-based, manifest-driven prompt injection defense
operating as AgentDojo BasePipelineElement subclasses.

Key architectural properties (differentiating from CaMeL):
  - No LLM on the security-critical path
  - Design-time compiled World Manifests (YAML → deterministic JSON rules)
  - Taint propagation at message level (all tool outputs = untrusted)
  - TaintContainmentLaw: tainted data cannot flow into external side-effect tools
"""

# Lazy imports: don't pull agentdojo at package import time
# (agentdojo has optional heavy deps; import submodules directly as needed)

__all__ = [
    "Canonicalizer",
    "TaintState",
    "AHInputSanitizer",
    "AHTaintGuard",
    "build_ah_pipeline",
]


def __getattr__(name: str):
    if name == "Canonicalizer":
        from ah_defense.canonicalizer import Canonicalizer
        return Canonicalizer
    if name == "TaintState":
        from ah_defense.taint_tracker import TaintState
        return TaintState
    if name in ("AHInputSanitizer", "AHTaintGuard", "build_ah_pipeline"):
        from ah_defense import pipeline as _pipeline
        return getattr(_pipeline, name)
    raise AttributeError(f"module 'ah_defense' has no attribute {name!r}")
