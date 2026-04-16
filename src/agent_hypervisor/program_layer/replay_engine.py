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

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Collection, Literal, Optional

from .program_model import Program, Step
from .program_runner import ProgramRunner
from .program_trace import ProgramTrace, StepTrace
from .review_models import ReviewedProgram
from .task_compiler import DeterministicTaskCompiler
from .world_registry import WorldDescriptor
from .world_validator import validate_program


# ---------------------------------------------------------------------------
# Replay trace — enriches ProgramTrace with world context (SYS-2 light step 8)
# ---------------------------------------------------------------------------


ReplayWorldSource = Literal["active", "explicit", "default"]
ReplayVerdict = Literal["allow", "deny", "partial_failure"]


@dataclass(frozen=True)
class ReplayTrace:
    """
    Wraps a ProgramTrace with the World context under which replay occurred.

    Fields:
        replay_id            — unique per-replay identifier ("replay-<hex>")
        program_id           — the replayed program's id
        world_id             — world used for this replay
        world_version        — the world's version
        world_source         — how the world was selected: "active" (fetched
                               from the registry's active pointer), "explicit"
                               (passed by the caller), or "default"
                               (no world context; SUPPORTED_WORKFLOWS)
        preview_compatible   — prior preview verdict if run; None if skipped
        program_trace        — the underlying execution trace (step verdicts)
        final_verdict        — 'allow' if every step allowed, 'deny' if the
                               first step was denied, 'partial_failure' if
                               some steps ran before a later step was denied
        replayed_at          — ISO-8601 wall clock of the replay call

    The `program_trace` field carries the full step-by-step outcome; this
    wrapper exists only to bind world identity to that outcome so downstream
    audit can reconstruct "who replayed, what program, under which world".
    """

    replay_id: str
    program_id: str
    world_id: str
    world_version: str
    world_source: ReplayWorldSource
    program_trace: ProgramTrace
    final_verdict: ReplayVerdict
    preview_compatible: Optional[bool] = field(default=None)
    replayed_at: str = field(default="")

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "program_id": self.program_id,
            "world_id": self.world_id,
            "world_version": self.world_version,
            "world_source": self.world_source,
            "preview_compatible": self.preview_compatible,
            "final_verdict": self.final_verdict,
            "replayed_at": self.replayed_at,
            "program_trace": self.program_trace.to_dict(),
        }


def _make_replay_id() -> str:
    return f"replay-{uuid.uuid4().hex[:12]}"


def _classify_verdict(trace: ProgramTrace) -> ReplayVerdict:
    """
    Map a ProgramTrace to the three-valued replay verdict.

    - allow            — every step.verdict == 'allow'
    - deny             — first step was denied (nothing executed)
    - partial_failure  — at least one step executed before a later deny
    """
    if trace.ok:
        return "allow"
    if not trace.step_traces:
        return "deny"
    allowed_prefix = any(st.allowed for st in trace.step_traces)
    if allowed_prefix:
        return "partial_failure"
    return "deny"


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

    # ------------------------------------------------------------------
    # SYS-2 light: replay targeting a specific World
    # ------------------------------------------------------------------

    def replay_under_world(
        self,
        program: ReviewedProgram,
        world: Optional[WorldDescriptor] = None,
        world_source: ReplayWorldSource = "explicit",
        preview_compatible: Optional[bool] = None,
        runner: Optional[ProgramRunner] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ReplayTrace:
        """
        Replay ``program`` under a specific ``world`` and return a ReplayTrace.

        The world's ``allowed_actions`` becomes the replay's authority
        boundary — no matter what world the program was originally accepted
        against.  This enforces the SYS-2 light invariant: "a reviewed
        program does not carry authority; authority lives in the World."

        Args:
            program:             the ReviewedProgram to replay.
            world:               WorldDescriptor defining allowed_actions.
                                 When None, falls back to the default
                                 SUPPORTED_WORKFLOWS set and the returned
                                 ReplayTrace marks world_source='default'.
            world_source:        how the caller chose this world — used by
                                 audit so a trace records 'active' vs
                                 'explicit' vs 'default' selection.  Ignored
                                 when world is None (forced to 'default').
            preview_compatible:  optional verdict from a prior compatibility
                                 preview; stored on the trace for audit.  No
                                 effect on execution.
            runner:              optional ProgramRunner to reuse.  If None,
                                 a fresh runner is built from the world's
                                 allowed_actions.
            context:             execution context passed through to runner.

        Returns:
            A ReplayTrace carrying the world identity, source, preview
            verdict, and the underlying ProgramTrace.
        """
        if world is None:
            allowed_actions: Collection[str] = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
            world_id = "default"
            world_version = "unspecified"
            world_source = "default"
        else:
            if not isinstance(world, WorldDescriptor):
                raise TypeError(
                    f"replay_under_world() requires a WorldDescriptor, "
                    f"got {type(world).__name__!r}"
                )
            allowed_actions = world.allowed_actions
            world_id = world.world_id
            world_version = world.version

        program_trace = self.replay(
            program,
            runner=runner,
            context=context,
            allowed_actions=allowed_actions,
        )

        return ReplayTrace(
            replay_id=_make_replay_id(),
            program_id=program.id,
            world_id=world_id,
            world_version=world_version,
            world_source=world_source,
            preview_compatible=preview_compatible,
            program_trace=program_trace,
            final_verdict=_classify_verdict(program_trace),
            replayed_at=datetime.now(tz=timezone.utc).isoformat(),
        )
