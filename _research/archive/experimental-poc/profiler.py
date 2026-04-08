"""
profiler.py – derive a capability profile from one or more recorded traces.

A profile is the union of every (tool, action, resource-prefix) triple
observed across all trace steps that are not tainted.  Tainted steps are
noted separately; they never widen the allowed set.

Taint is derived deterministically: a step is tainted if any of its
input_sources is untrusted, OR if any step it depends_on is tainted.
The legacy 'tainted' field in trace JSON is ignored; provenance and
execution flow are the source of truth.

Usage (module):
    from compiler.profiler import derive_profile
    profile = derive_profile(["traces/benign_repo_maintenance.json"])

Usage (CLI):
    python -m awc.compiler.profiler traces/benign_repo_maintenance.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from awc.policy.taint import DEFAULT_INPUT_TRUST, compute_trace_taint


@dataclass
class CapabilityProfile:
    profile_id: str
    derived_from: list[str]
    allowed_tools: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    allowed_resources: list[str] = field(default_factory=list)
    tainted_steps_observed: int = 0

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "derived_from": self.derived_from,
            "allowed_tools": sorted(set(self.allowed_tools)),
            "allowed_actions": sorted(set(self.allowed_actions)),
            "allowed_resources": sorted(set(self.allowed_resources)),
            "tainted_steps_observed": self.tainted_steps_observed,
        }


def _resource_prefix(resource: str) -> str:
    """Return scheme://authority/* for a resource URI."""
    parts = resource.split("/")
    if len(parts) >= 3:
        return "/".join(parts[:3]) + "/*"
    return resource + "/*"


def derive_profile(
    trace_paths: Iterable[str | Path],
    profile_id: str = "derived",
    input_trust: dict[str, str] | None = None,
) -> CapabilityProfile:
    """Load one or more trace files and return a CapabilityProfile.

    Taint is computed with full propagation via depends_on (compute_trace_taint).
    A step is excluded if it is tainted by source OR if it depends on a tainted
    step.  The legacy 'tainted' field is ignored.
    """
    trust_map = input_trust if input_trust is not None else DEFAULT_INPUT_TRUST

    tools: set[str] = set()
    actions: set[str] = set()
    resources: set[str] = set()
    tainted_count = 0
    sources: list[str] = []

    for path in trace_paths:
        path = Path(path)
        sources.append(str(path))
        with path.open() as fh:
            trace = json.load(fh)

        steps = trace.get("steps", [])
        # Compute taint with propagation across the full trace.
        taint_state = compute_trace_taint(steps, trust_map)

        for step in steps:
            step_id = step.get("step_id", "?")
            is_tainted, _ = taint_state.get(step_id, (False, []))
            if is_tainted:
                tainted_count += 1
                continue  # tainted steps never expand allowed set
            tools.add(step["tool"])
            actions.add(step["action"])
            resources.add(_resource_prefix(step["resource"]))

    return CapabilityProfile(
        profile_id=profile_id,
        derived_from=sources,
        allowed_tools=sorted(tools),
        allowed_actions=sorted(actions),
        allowed_resources=sorted(resources),
        tainted_steps_observed=tainted_count,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m awc.compiler.profiler <trace.json> [<trace2.json> ...]")
        sys.exit(1)

    profile = derive_profile(sys.argv[1:], profile_id="derived_profile")
    import yaml  # type: ignore[import-untyped]

    print(yaml.dump(profile.to_dict(), default_flow_style=False, sort_keys=False))
