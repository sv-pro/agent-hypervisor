"""
program_review_demo.py — End-to-end demonstration of PL-3 (Program Review & Minimization).

This demo shows the full lifecycle of a candidate program:

    1. Build a raw candidate program from a simulated trace
    2. Propose the program (PROPOSED status)
    3. Minimize: remove duplicate steps, strip None params, narrow URL scope
    4. Review: attach reviewer notes (REVIEWED status)
    5. Accept: world validation passes (ACCEPTED status)
    6. Replay: execute minimized program through the hypervisor pipeline

Run:
    python examples/program_review_demo.py
"""

import json
import sys
import tempfile
from pathlib import Path

# Allow running from the repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_hypervisor.program_layer.program_runner import ProgramRunner
from agent_hypervisor.program_layer.replay_engine import ReplayEngine
from agent_hypervisor.program_layer.review_lifecycle import (
    accept_program,
    minimize_program,
    propose_program,
    reject_program,
    review_program,
)
from agent_hypervisor.program_layer.review_models import CandidateStep
from agent_hypervisor.program_layer.program_store import ProgramStore
from agent_hypervisor.program_layer.task_compiler import DeterministicTaskCompiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sep(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def _print_steps(label: str, steps) -> None:
    print(f"\n{label} ({len(steps)} step(s)):")
    for i, s in enumerate(steps):
        caps = f"  caps={list(s.capabilities_used)}" if s.capabilities_used else ""
        print(f"  [{i}] {s.tool}  params={json.dumps(s.params)}{caps}")


def _print_diff(diff) -> None:
    if diff.is_empty:
        print("\nDiff: (no changes — program was already minimal)")
        return
    print("\nDiff:")
    for r in diff.removed_steps:
        print(f"  REMOVED  step[{r.index}] {r.tool!r}  — {r.reason}")
    for c in diff.param_changes:
        print(f"  PARAM    step[{c.step_index}] {c.field!r}: "
              f"{c.before!r}  →  {c.after!r}  — {c.reason}")
    for c in diff.capability_reduction:
        print(f"  CAP      step[{c.step_index}] {c.before!r}  →  {c.after!r}  — {c.reason}")


# ---------------------------------------------------------------------------
# Step 1: Simulate a raw candidate program from a trace
# ---------------------------------------------------------------------------

SIMULATED_TRACE_ID = "trace-20260416-001"

# These steps represent what an agent actually did, extracted from a trace.
# They are intentionally "noisy" to demonstrate minimization:
#   - step 1 is a duplicate of step 0 (same tool + params)
#   - step 2 has a None-valued param ("debug") that can be dropped
#   - step 3 has a URL with a query string that can be stripped
#   - step 4 has a broad capability ("http_request:any") that can be narrowed
RAW_STEPS = [
    CandidateStep(
        tool="count_words",
        params={"input": "The quick brown fox"},
        provenance=SIMULATED_TRACE_ID,
    ),
    # Duplicate — agent called count_words twice on the same input
    CandidateStep(
        tool="count_words",
        params={"input": "The quick brown fox"},
        provenance=SIMULATED_TRACE_ID,
    ),
    # None-valued param that adds no information
    CandidateStep(
        tool="normalize_text",
        params={"input": "The Quick Brown Fox", "debug": None},
        provenance=SIMULATED_TRACE_ID,
    ),
    # URL with tracking query params — strip them
    CandidateStep(
        tool="http_request",
        params={"url": "https://api.example.com/v1/words?session=abc123&token=xyz"},
        provenance=SIMULATED_TRACE_ID,
        capabilities_used=("http_request:any",),
    ),
]


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProgramStore(Path(tmpdir) / "programs")

        # ----------------------------------------------------------------
        # Step 2: Propose the program
        # ----------------------------------------------------------------
        _sep("STEP 2 — Propose program from trace")
        prog = propose_program(
            steps=RAW_STEPS,
            trace_id=SIMULATED_TRACE_ID,
            world_version="1.0",
            store=store,
        )
        print(f"\nProgram ID : {prog.id}")
        print(f"Status     : {prog.status.value}")
        print(f"Trace ID   : {prog.metadata.created_from_trace}")
        _print_steps("Original steps", prog.original_steps)

        # ----------------------------------------------------------------
        # Step 3: Minimize
        # ----------------------------------------------------------------
        _sep("STEP 3 — Minimize")
        prog = minimize_program(prog.id, store)
        _print_steps("Minimized steps", prog.minimized_steps)
        _print_diff(prog.diff)

        step_delta = len(prog.original_steps) - len(prog.minimized_steps)
        print(f"\nReduction: {len(prog.original_steps)} → {len(prog.minimized_steps)} steps "
              f"({step_delta} removed)")

        # ----------------------------------------------------------------
        # Step 4: Review
        # ----------------------------------------------------------------
        _sep("STEP 4 — Review (proposed → reviewed)")
        prog = review_program(prog.id, store, notes="Minimization looks correct. Approved for sandbox replay.")
        print(f"\nStatus : {prog.status.value}")
        print(f"Notes  : {prog.metadata.reviewer_notes}")

        # ----------------------------------------------------------------
        # Step 5: Accept (with world validation)
        #
        # Note: http_request is NOT in the default sandbox workflow set, so
        # we accept using only the steps that survive world validation.
        # Here we show both outcomes: accept on a known-good subset, and
        # demonstrate rejection for the full set.
        # ----------------------------------------------------------------
        _sep("STEP 5 — Accept with world validation")

        # Build a program using only sandbox-compatible steps for acceptance demo
        sandbox_steps = [
            s for s in RAW_STEPS
            if s.tool in DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
        ]
        prog2 = propose_program(
            steps=sandbox_steps,
            trace_id=SIMULATED_TRACE_ID,
            world_version="1.0",
            store=store,
            program_id="prog-sandbox-demo",
        )
        minimize_program(prog2.id, store)
        review_program(prog2.id, store, notes="Sandbox-compatible subset.")
        accepted = accept_program(
            prog2.id,
            store,
            allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS,
        )
        print(f"\nStatus : {accepted.status.value}")
        print(f"World  : validated against {sorted(DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)}")

        # Show that accepting with an unknown tool raises WorldValidationError
        from agent_hypervisor.program_layer.review_lifecycle import WorldValidationError
        prog3 = propose_program(
            steps=[CandidateStep(tool="forbidden_tool")],
            trace_id=None,
            world_version="1.0",
            store=store,
            program_id="prog-rejected-demo",
        )
        review_program(prog3.id, store)
        try:
            accept_program(prog3.id, store, allowed_actions={"count_words"})
        except WorldValidationError as e:
            print(f"\nWorldValidationError (expected): {e}")

        # ----------------------------------------------------------------
        # Step 6: Replay
        # ----------------------------------------------------------------
        _sep("STEP 6 — Replay accepted program")
        engine = ReplayEngine()
        runner = ProgramRunner(
            allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
        )
        trace = engine.replay(
            accepted,
            runner=runner,
            context={"input": "The quick brown fox"},
        )
        print(f"\nReplay result: ok={trace.ok}")
        for st in trace.step_traces:
            status_icon = "✓" if st.verdict == "allow" else "✗"
            print(f"  {status_icon} step[{st.step_index}] {st.action!r}  "
                  f"verdict={st.verdict}  result={st.result}")

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        _sep("SUMMARY")
        print(f"""
  Original steps  : {len(RAW_STEPS)}
  Minimized steps : {len(accepted.minimized_steps)}
  Steps removed   : {len(accepted.diff.removed_steps)}
  Param changes   : {len(accepted.diff.param_changes)}
  Cap reductions  : {len(accepted.diff.capability_reduction)}
  Final status    : {accepted.status.value}
  Replay          : {'passed' if trace.ok else 'failed'}
""")


if __name__ == "__main__":
    run_demo()
