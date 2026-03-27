"""
evaluate.py – CLI wrapper for the enforcement engine.

Evaluates every step in a trace against a manifest and prints a decision
table.  Taint is computed deterministically from input provenance and
propagated through depends_on dependencies before any step is evaluated.

Usage:
    python -m awc.policy.evaluate --trace traces/example.json \\
                               --manifest manifests/repo-safe-write.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from awc.policy.engine import Decision, evaluate_step
from awc.policy.taint import compute_trace_taint


def evaluate_trace(trace_path: Path, manifest_path: Path) -> list[dict]:
    with trace_path.open() as fh:
        trace = json.load(fh)
    with manifest_path.open() as fh:
        manifest = yaml.safe_load(fh)

    steps = trace.get("steps", [])
    input_trust_map: dict[str, str] = manifest.get("input_trust", {})

    # Derive taint for the full trace in execution order, propagating through
    # depends_on references.  This replaces reading the raw 'tainted' field.
    taint_state = compute_trace_taint(steps, input_trust_map)

    results = []
    for step in steps:
        step_id = step.get("step_id", "?")
        derived_taint, taint_reasons = taint_state.get(step_id, (False, []))
        decision, reason = evaluate_step(step, manifest, derived_taint=derived_taint, taint_reasons=taint_reasons)
        results.append(
            {
                "step_id": step_id,
                "tool": step.get("tool", "?"),
                "action": step.get("action", "?"),
                "resource": step.get("resource", "?"),
                "derived_taint": derived_taint,
                "taint_reasons": taint_reasons,
                "decision": decision.value,
                "reason": reason,
            }
        )
    return results


def _print_table(results: list[dict]) -> None:
    col_widths = {
        "step_id": 10,
        "tool": 14,
        "resource": 38,
        "decision": 20,
    }
    header = (
        f"{'STEP':<{col_widths['step_id']}}"
        f"{'TOOL':<{col_widths['tool']}}"
        f"{'RESOURCE':<{col_widths['resource']}}"
        f"{'DECISION':<{col_widths['decision']}}"
        f"REASON"
    )
    print(header)
    print("-" * 120)
    for r in results:
        taint_flag = " [TAINTED]" if r["derived_taint"] else ""
        print(
            f"{r['step_id']:<{col_widths['step_id']}}"
            f"{r['tool']:<{col_widths['tool']}}"
            f"{r['resource'][:36]:<{col_widths['resource']}}"
            f"{r['decision'] + taint_flag:<{col_widths['decision']}}"
            f"{r['reason']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a trace against a World Manifest.")
    parser.add_argument("--trace", required=True, help="Path to trace JSON file.")
    parser.add_argument("--manifest", required=True, help="Path to manifest YAML file.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output results as JSON.")
    args = parser.parse_args(argv)

    trace_path = Path(args.trace)
    manifest_path = Path(args.manifest)

    if not trace_path.exists():
        print(f"Error: trace file not found: {trace_path}", file=sys.stderr)
        return 1
    if not manifest_path.exists():
        print(f"Error: manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    results = evaluate_trace(trace_path, manifest_path)

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        _print_table(results)

    any_deny = any(r["decision"] == Decision.DENY.value for r in results)
    return 1 if any_deny else 0


if __name__ == "__main__":
    sys.exit(main())
