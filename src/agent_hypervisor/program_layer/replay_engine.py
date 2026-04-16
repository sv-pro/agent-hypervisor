"""
replay_engine.py — Replay engine for minimized programs (PL-3).

Converts a ReviewedProgram's minimized_steps into a Program and replays it
through the same ProgramRunner pipeline used for live execution.

Replay contract:
    1. Convert each CandidateStep → Step (tool → action, params preserved).
    2. Construct a Program from the converted steps.
    3. Run static world validation (validate_program).
       If validation fails, return a failed ProgramTrace without executing.
    4. Run the Program through ProgramRunner — same enforcement path as live.
    5. Return the ProgramTrace.

The outcome is deterministic: the same ReviewedProgram replayed against the
same World and allowed_actions always produces the same ProgramTrace.

Edge cases:
    - Empty minimized_steps (all steps removed): returns ok=True with an
      empty step_traces list.  An empty program has no side effects.
    - World validation fails: returns ok=False with StepTrace entries whose
      verdict='deny' and error explains which world constraint was violated.
      No steps execute.

Usage::

    from program_layer.replay_engine import ReplayEngine
    from program_layer.program_runner import ProgramRunner

    engine = ReplayEngine()
    trace = engine.replay(program)
    if trace.ok:
        print("Replay succeeded")
    else:
        failed = [st for st in trace.step_traces if st.denied]
        for st in failed:
            print(f"Step {st.step_index} ({st.action}) denied: {st.error}")
"""

from __future__ import annotations

from typing import Any, Collection, Optional

from .program_model import Program, Step
from .program_runner import ProgramRunner
from .program_trace import ProgramTrace, StepTrace
from .review_models import ReviewedProgram
from .task_compiler import DeterministicTaskCompiler
from .world_validator import validate_program


class ReplayEngine:
    """
    Replay a ReviewedProgram's minimized steps through ProgramRunner.

    The engine is stateless — each call to replay() is independent.
    """

    def replay(
        self,
        program: ReviewedProgram,
        runner: Optional[ProgramRunner] = None,
        context: Optional[dict[str, Any]] = None,
        allowed_actions: Optional[Collection[str]] = None,
    ) -> ProgramTrace:
        """
        Replay the minimized program and return a ProgramTrace.

        Args:
            program:         the ReviewedProgram to replay (uses minimized_steps).
            runner:          ProgramRunner to use.  If None, a new ProgramRunner
                             is constructed with the given allowed_actions.
            context:         optional execution context passed to ProgramRunner.run().
            allowed_actions: the world's allowed action set.
                             Defaults to DeterministicTaskCompiler.SUPPORTED_WORKFLOWS.
                             Ignored when runner is provided explicitly.

        Returns:
            ProgramTrace with one StepTrace per step (same structure as live
            execution).

        Raises:
            TypeError: program is not a ReviewedProgram.
        """
        if not isinstance(program, ReviewedProgram):
            raise TypeError(
                f"ReplayEngine.replay() requires a ReviewedProgram, "
                f"got {type(program).__name__!r}"
            )

        if allowed_actions is None:
            allowed_actions = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS

        # ----------------------------------------------------------------
        # Edge case: empty minimized program (all steps removed)
        # ----------------------------------------------------------------
        if not program.minimized_steps:
            trace = ProgramTrace(program_id=program.id)
            trace.ok = True
            trace.total_duration_seconds = 0.0
            trace.aborted_at_step = None
            return trace

        # ----------------------------------------------------------------
        # Convert CandidateStep → Step
        # ----------------------------------------------------------------
        steps = tuple(
            Step(
                action=cs.tool,
                params=cs.params,
                description=f"replayed from program {program.id}",
            )
            for cs in program.minimized_steps
        )
        prog = Program(program_id=program.id, steps=steps)

        # ----------------------------------------------------------------
        # Static world validation before any execution
        # ----------------------------------------------------------------
        validation = validate_program(prog, allowed_actions)
        if not validation.ok:
            trace = ProgramTrace(program_id=program.id)
            trace.ok = False
            trace.aborted_at_step = validation.violations[0].step_index
            trace.step_traces = [
                StepTrace(
                    step_index=v.step_index,
                    action=v.action,
                    verdict="deny",
                    result=None,
                    error=f"world validation failed: {v.reason}",
                    duration_seconds=0.0,
                )
                for v in validation.violations
            ]
            return trace

        # ----------------------------------------------------------------
        # Replay through ProgramRunner (same path as live execution)
        # ----------------------------------------------------------------
        if runner is None:
            runner = ProgramRunner(allowed_actions=allowed_actions)

        return runner.run(prog, context=context)
