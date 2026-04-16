"""
program_trace.py — Per-step execution trace for Program Layer Phase 1.

ProgramTrace is the observability artifact produced by ProgramRunner.
It records what happened at each step: the verdict (allow/deny/skip),
the step result on success, the error message on failure, and timing.

Verdicts:
    'allow'  — step was executed and completed successfully
    'deny'   — step was rejected (action not in allowed set, sandbox security
               violation, timeout, or runtime error)
    'skip'   — step was never attempted because a prior step was denied;
               execution was aborted early

ProgramTrace.ok is True only if every step completed with verdict='allow'.
ProgramTrace.aborted_at_step is set to the index of the first denied step
(the one that triggered the abort).  Steps after that index have verdict='skip'.

Usage::

    trace = runner.run(program)
    if trace.ok:
        # All steps succeeded; access results
        for step_trace in trace.step_traces:
            print(step_trace.action, step_trace.result)
    else:
        # Find the failing step
        failed = next(st for st in trace.step_traces if st.denied)
        print(f"Step {failed.step_index} ({failed.action}) denied: {failed.error}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StepVerdict = Literal["allow", "deny", "skip"]


@dataclass(frozen=True)
class StepTrace:
    """
    Immutable record of a single step's execution outcome.

    Fields:
        step_index        — 0-based position in the program
        action            — the step's action name (from Step.action)
        verdict           — 'allow' | 'deny' | 'skip'
        result            — the step's output value (None if denied or skipped)
        error             — error or denial message (None if verdict == 'allow')
        duration_seconds  — wall-clock time for this step; 0.0 for 'skip'
    """

    step_index: int
    action: str
    verdict: StepVerdict
    result: Any = field(default=None, hash=False, compare=False)
    error: str | None = field(default=None)
    duration_seconds: float = field(default=0.0)

    @property
    def allowed(self) -> bool:
        """True if the step was successfully executed."""
        return self.verdict == "allow"

    @property
    def denied(self) -> bool:
        """True if the step was rejected before or during execution."""
        return self.verdict == "deny"

    @property
    def skipped(self) -> bool:
        """True if the step was never attempted due to a prior denial."""
        return self.verdict == "skip"


@dataclass
class ProgramTrace:
    """
    Full execution record for a Program run.

    Built incrementally by ProgramRunner.run() as steps execute.
    Treat as read-only after ProgramRunner.run() returns.

    Fields:
        program_id              — matches Program.program_id
        step_traces             — ordered list of StepTrace (one per step)
        ok                      — True only if all steps are 'allow'
        total_duration_seconds  — wall-clock time for the entire program run
        aborted_at_step         — 0-based index of the first denied step;
                                  None if ok=True or if program had no steps

    Usage::

        trace = runner.run(program)
        summary = trace.to_dict()   # JSON-safe dict for logging/storage
    """

    program_id: str
    step_traces: list[StepTrace] = field(default_factory=list)
    ok: bool = field(default=False)
    total_duration_seconds: float = field(default=0.0)
    aborted_at_step: int | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialise to a plain, JSON-safe dict.

        Used for audit logging and external storage.  The shape is stable
        across Phase 1 releases.
        """
        return {
            "program_id": self.program_id,
            "ok": self.ok,
            "total_duration_seconds": round(self.total_duration_seconds, 6),
            "aborted_at_step": self.aborted_at_step,
            "step_traces": [
                {
                    "step_index": st.step_index,
                    "action": st.action,
                    "verdict": st.verdict,
                    "result": st.result,
                    "error": st.error,
                    "duration_seconds": round(st.duration_seconds, 6),
                }
                for st in self.step_traces
            ],
        }
