"""
taint.py – deterministic taint derivation and propagation.

Taint is NOT read from a manually assigned trace annotation.
Taint is DERIVED from input provenance and PROPAGATED through execution
dependencies (depends_on).

Rules:
  1. Source taint: a step is tainted if any of its input_sources resolves
     to 'untrusted' or 'conditional' in the trust map. Unknown sources
     default to 'untrusted'.
  2. Propagated taint: a step is tainted if any step it depends_on is tainted.
  3. Final taint: source_taint OR propagated_taint.

Taint is a deterministic function of provenance and flow, not a manually
assigned or heuristic label.
"""

from __future__ import annotations

# Taint is derived from provenance (input_sources + depends_on),
# not from annotations or model output.

# Canonical trust map for known input source types.
# Manifests embed this directly under input_trust; it is also used by the
# profiler and as a fallback when no manifest trust map is available.
DEFAULT_INPUT_TRUST: dict[str, str] = {
    "repo_local": "trusted",
    "environment": "untrusted",
    "llm_output": "untrusted",
    "tool_output": "conditional",
}

# Trust levels that imply taint.  'conditional' is treated as tainted for
# this PoC to keep the model simple and conservative.
_TAINTED_LEVELS = {"untrusted", "conditional"}


def derive_source_taint(
    input_sources: list[str],
    input_trust_map: dict[str, str],
) -> tuple[bool, list[str]]:
    """
    Derive taint from input sources alone (no dependency propagation).

    Returns (is_tainted, reasons).
    A source is tainted if it maps to 'untrusted' or 'conditional'.
    Unknown sources default to 'untrusted'.
    """
    reasons: list[str] = []
    for src in input_sources:
        trust = input_trust_map.get(src, "untrusted")
        if trust in _TAINTED_LEVELS:
            reasons.append(f"untrusted_input:{src}")
    return bool(reasons), reasons


def compute_trace_taint(
    steps: list[dict],
    input_trust_map: dict[str, str],
) -> dict[str, tuple[bool, list[str]]]:
    """
    Compute derived taint for every step in a trace, in execution order.

    Taint propagates through depends_on references.
    Returns {step_id: (is_tainted, reasons)}.

    Raises ValueError if depends_on references an unknown or not-yet-seen
    step – this enforces that steps are declared in execution order.
    """
    taint_state: dict[str, tuple[bool, list[str]]] = {}

    for step in steps:
        step_id = step.get("step_id", "?")
        input_sources: list[str] = step.get("input_sources", [])
        depends_on: list[str] = step.get("depends_on", [])

        is_tainted, reasons = derive_source_taint(input_sources, input_trust_map)

        # Propagate taint from declared dependencies.
        for dep_id in depends_on:
            if dep_id not in taint_state:
                raise ValueError(
                    f"Step '{step_id}' depends_on unknown step '{dep_id}'. "
                    f"Ensure steps are listed in execution order."
                )
            dep_tainted, _ = taint_state[dep_id]
            if dep_tainted:
                tag = f"depends_on_tainted:{dep_id}"
                if tag not in reasons:
                    reasons.append(tag)
                is_tainted = True

        taint_state[step_id] = (is_tainted, reasons)

    return taint_state
