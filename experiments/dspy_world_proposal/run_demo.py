#!/usr/bin/env python3
"""
run_demo.py — Terminal demo for the DSPy World Proposal experiment.

Runs Track A (Workflow Threat + Minimization) and Track B (Calibration Review)
against example workflows and prints structured results.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python run_demo.py

    # Or with OpenAI:
    export OPENAI_API_KEY=sk-...
    python run_demo.py
"""

from __future__ import annotations

import json
import os
import sys

# Ensure this directory is on the path regardless of where the script is invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dspy

from examples import TRACK_A_EXAMPLES, TRACK_B_EXAMPLES
from modules import CalibrationReviewPipeline, ThreatAndMinimizationPipeline


# ---------------------------------------------------------------------------
# LM setup
# ---------------------------------------------------------------------------


def setup_lm() -> dspy.LM:
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if anthropic_key:
        lm = dspy.LM("anthropic/claude-sonnet-4-6", api_key=anthropic_key)
        print(f"[lm] anthropic/claude-sonnet-4-6")
    elif openai_key:
        lm = dspy.LM("openai/gpt-4o-mini", api_key=openai_key)
        print(f"[lm] openai/gpt-4o-mini")
    else:
        print(
            "[error] No LM API key found.\n"
            "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY before running the demo."
        )
        sys.exit(1)

    dspy.configure(lm=lm)
    return lm


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

WIDTH = 72
HEAVY = "=" * WIDTH
LIGHT = "-" * WIDTH


def header(title: str, char: str = "=") -> None:
    bar = char * WIDTH
    print(f"\n{bar}")
    print(f"  {title}")
    print(f"{bar}\n")


def sub(label: str) -> None:
    print(f"\n{LIGHT}")
    print(f"  {label}")
    print(f"{LIGHT}")


def bullet(items: list, indent: int = 2) -> None:
    pad = " " * indent
    for item in items:
        print(f"{pad}• {item}")


# ---------------------------------------------------------------------------
# Track A renderer
# ---------------------------------------------------------------------------


def render_track_a(result: dict) -> None:
    wf = result["workflow"]
    header(f"TRACK A  |  {wf[:55]}{'...' if len(wf) > 55 else ''}")

    sub("1. INFERRED CAPABILITIES")
    for cap in result["inferred_capabilities"]:
        print(f"  [{cap['scope']:25s}]  {cap['name']}")
        print(f"   {'':27s}  → {cap['justification']}")

    sub("2. ATTACK SCENARIOS")
    for atk in result["attack_scenarios"]:
        print(f"  [{atk['exploited_capability']:25s}]  {atk['name']}")
        print(f"   path   : {atk['description']}")
        print(f"   impact : {atk['impact']}")

    sub("3. MINIMIZED CAPABILITIES  (necessary + sufficient)")
    for cap in result["minimized_capabilities"]:
        print(f"  [{cap['scope']:25s}]  {cap['name']}")
    print()
    print("  REMOVED:")
    bullet(result["removed_capabilities"], indent=4)

    sub("4. SURROGATE SUGGESTIONS")
    if result["surrogate_suggestions"]:
        for s in result["surrogate_suggestions"]:
            print(f"  {s['original_capability']}")
            print(f"    → surrogate     : {s['surrogate']}")
            print(f"    → rationale     : {s['rationale']}")
            print(f"    → scope removed : {s['scope_reduction']}")
    else:
        print("  (no surrogates proposed; minimized set is already narrow)")

    sub("5. DRAFT MANIFEST")
    m = result["draft_manifest"]
    print(f"  workflow_id : {m['workflow_id']}")
    print(f"  closed_world ({len(m['closed_world'])} capabilities):")
    for entry in m["closed_world"]:
        surrogate_tag = (
            f"  [surrogate_for: {entry['surrogate_for']}]"
            if entry.get("surrogate_for")
            else ""
        )
        print(f"    [{entry['scope']:25s}]  {entry['capability']}{surrogate_tag}")
    print(f"  removed        : {m['removed_capabilities']}")
    if m.get("surrogates_applied"):
        print(f"  surrogates     : {m['surrogates_applied']}")
    if m.get("notes"):
        print("  notes:")
        bullet(m["notes"], indent=4)


# ---------------------------------------------------------------------------
# Track B renderer
# ---------------------------------------------------------------------------


def render_track_b(result: dict) -> None:
    v = result["verdict"]
    header(f"TRACK B  |  capability: {result['capability_request']}")

    print(f"  capability_request : {result['capability_request']}")
    print(f"  workflow_goal      : {result['workflow_goal'][:70]}")
    print(f"  provenance         : {result['provenance'][:80]}...")

    sub("CALIBRATION VERDICT")
    print(f"  directly_implied_by_task : {v['directly_implied_by_task']}")
    print(f"  implication_type         : {v['implication_type']}")

    print("\n  ABUSE CASES:")
    bullet(v["abuse_cases"], indent=4)

    if v.get("narrower_safer_alternative"):
        print(f"\n  NARROWER SURROGATE : {v['narrower_safer_alternative']}")
    else:
        print("\n  NARROWER SURROGATE : none proposed")

    rec = v["recommendation"]
    rec_marker = {
        "approve_exact": "✓ APPROVE EXACT",
        "approve_narrower": "~ APPROVE NARROWER",
        "deny": "✗ DENY",
        "require_stronger_justification": "? REQUIRE STRONGER JUSTIFICATION",
    }.get(rec, rec.upper())

    print(f"\n  RECOMMENDATION : {rec_marker}")
    print(f"  REASONING      : {v['reasoning']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    header("DSPy World Proposal  —  Threat Analysis & Calibration Experiment", "#")
    setup_lm()

    track_a = ThreatAndMinimizationPipeline()
    track_b = CalibrationReviewPipeline()

    # --- Track A ---
    header("TRACK A  —  Workflow Threat + Minimization Analysis", "#")

    for ex in TRACK_A_EXAMPLES:
        print(f"\n[running] {ex['name']} ...")
        try:
            result = track_a(
                workflow_description=ex["workflow_description"],
                tool_list=ex["tool_list"],
            )
            render_track_a(result)
        except Exception as exc:
            print(f"  [error] {exc}")
            import traceback
            traceback.print_exc()

    # --- Track B ---
    header("TRACK B  —  Calibration Review Assistant", "#")

    for ex in TRACK_B_EXAMPLES:
        print(f"\n[running] {ex['name']} ...")
        try:
            result = track_b(
                capability_request=ex["capability_request"],
                workflow_goal=ex["workflow_goal"],
                provenance=ex["provenance"],
            )
            render_track_b(result)
        except Exception as exc:
            print(f"  [error] {exc}")
            import traceback
            traceback.print_exc()

    header("Demo complete", "=")


if __name__ == "__main__":
    main()
