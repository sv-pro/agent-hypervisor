"""
run_demo.py — Minimal demo runner for Phase 1 inspection.

Phase 1 only: this runner is skeletal.
It wires up a real DSPy LM, runs both modules over the example inputs,
and prints structured results for visual inspection.

Usage:
    ANTHROPIC_API_KEY=... python run_demo.py

No optimization, no training, no evaluation loop.
That is Phase 2.

Dependencies:
    dspy         (pip install dspy)
    anthropic    (transitive via dspy)
"""

from __future__ import annotations

import json
import os

import dspy

from .examples import CALIBRATION_EXAMPLES, WORKFLOWS
from .modules import CapabilityReviewer, WorkflowSecurityAnalyzer


def configure_lm() -> None:
    """Configure DSPy with Claude Sonnet. Swap model as needed."""
    lm = dspy.LM(
        model="anthropic/claude-sonnet-4-6",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    dspy.configure(lm=lm)


def run_workflow_examples() -> None:
    analyzer = WorkflowSecurityAnalyzer()

    for i, workflow in enumerate(WORKFLOWS, start=1):
        desc = workflow["workflow_description"]
        print(f"\n{'='*60}")
        print(f"Workflow {i}: {desc[:60]}...")
        print("="*60)

        result = analyzer(workflow_description=desc)

        print(f"\n[Capabilities extracted]\n{json.dumps(result.capabilities, indent=2)}")
        print(f"\n[Attacks]\n{json.dumps(result.attacks, indent=2)}")
        print(f"\n[Kept after minimization]\n{json.dumps(result.kept, indent=2)}")
        print(f"\n[Dropped]\n{json.dumps(result.dropped, indent=2)}")
        print(f"\n[Surrogates]\n{json.dumps(result.surrogates, indent=2)}")
        print(f"\n[Draft manifest]\n{json.dumps(result.manifest, indent=2)}")


def run_calibration_examples() -> None:
    reviewer = CapabilityReviewer()

    for i, example in enumerate(CALIBRATION_EXAMPLES, start=1):
        print(f"\n{'='*60}")
        print(f"Calibration {i}: '{example['requested_capability']}'")
        print("="*60)

        result = reviewer(
            workflow_description=example["workflow_description"],
            requested_capability=example["requested_capability"],
            request_context=example["request_context"],
        )

        print(f"\n[Decision]          {result.decision}")
        print(f"[Implied by workflow] {result.implied_by_workflow}")
        print(f"[Adversarial risk]  {result.adversarial_risk}")
        print(f"[Rationale]         {result.rationale}")
        print(f"[Reviewer action]   {result.reviewer_action}")


def main() -> None:
    configure_lm()
    run_workflow_examples()
    run_calibration_examples()


if __name__ == "__main__":
    main()
