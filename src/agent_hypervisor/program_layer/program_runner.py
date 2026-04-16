"""
program_runner.py — Step-by-step program executor for Phase 1.

ProgramRunner executes a Program step by step, producing a ProgramTrace.

Execution contract
------------------
1. Validate each step's action against the allowed_actions set.
   Steps whose action is not in allowed_actions → verdict='deny';
   runner aborts immediately (remaining steps → verdict='skip').

2. Compile allowed steps using DeterministicTaskCompiler.
   If the compiler produces a DirectExecutionPlan (unsupported workflow)
   → verdict='deny'; runner aborts.

3. Execute compiled steps using ProgramExecutor inside the sandbox.
   Sandbox enforces: AST security validation, timeout, safe builtins only.
   Any sandbox error (timeout, security, runtime) → verdict='deny'; abort.

4. On first denied step, all remaining steps are marked 'skip' and the
   runner returns immediately with trace.ok=False, trace.aborted_at_step=i.

5. Return ProgramTrace with one StepTrace per step.

The runner does NOT re-evaluate policy.  Policy enforcement is complete
before ProgramRunner.run() is called.  The allowed_actions set passed to
the runner represents post-enforcement knowledge about what the world permits.

Fail-closed: any unexpected error during step execution is treated as
verdict='deny'.  The runner never propagates exceptions to the caller;
errors are always captured in StepTrace.error.

Usage::

    runner = ProgramRunner(allowed_actions={"count_words", "normalize_text"})
    program = Program(
        program_id="my-program",
        steps=(
            Step(action="count_words", params={"input": "hello world"}),
        ),
    )
    trace = runner.run(program)
    if trace.ok:
        print(trace.step_traces[0].result)   # {"word_count": 2, ...}
"""

from __future__ import annotations

import logging
import time
from typing import Any, Collection

from .execution_plan import DirectExecutionPlan, ProgramExecutionPlan
from .program_executor import ProgramExecutor
from .program_model import Program, Step, MAX_STEPS
from .program_trace import ProgramTrace, StepTrace
from .task_compiler import DeterministicTaskCompiler

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 5.0


class ProgramRunner:
    """
    Execute a Program step by step and return a ProgramTrace.

    Args:
        allowed_actions:  Collection of action names the program may use.
                          Steps whose action is not in this set are denied.
                          If None, defaults to DeterministicTaskCompiler.SUPPORTED_WORKFLOWS.
        default_timeout:  Per-step wall-clock timeout in seconds (default 5.0).
                          Individual steps may override via params["timeout_seconds"].
        compiler:         TaskCompiler to use (default: DeterministicTaskCompiler).
        executor:         Executor to use (default: ProgramExecutor).

    Raises:
        ValueError: default_timeout is not positive.
        TypeError:  run() called with something other than a Program.
    """

    def __init__(
        self,
        allowed_actions: Collection[str] | None = None,
        default_timeout: float = _DEFAULT_TIMEOUT,
        compiler: DeterministicTaskCompiler | None = None,
        executor: ProgramExecutor | None = None,
    ) -> None:
        if default_timeout <= 0:
            raise ValueError(
                f"default_timeout must be positive, got {default_timeout!r}"
            )
        self._allowed_actions: frozenset[str] = (
            frozenset(allowed_actions)
            if allowed_actions is not None
            else frozenset(DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)
        )
        self._default_timeout = default_timeout
        self._compiler = compiler or DeterministicTaskCompiler()
        self._executor = executor or ProgramExecutor()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self, program: Program, context: dict[str, Any] | None = None
    ) -> ProgramTrace:
        """
        Execute program step by step and return a ProgramTrace.

        Steps execute in order (index 0 first).  On the first denied or
        errored step, all remaining steps are marked 'skip' and a
        ProgramTrace is returned with ok=False, aborted_at_step=<index>.

        Args:
            program:  the Program to execute (frozen; not mutated).
            context:  optional execution context dict.  Passed to the
                      executor for each step.  Step-level params["input"]
                      overrides any "input" key in this dict.

        Returns:
            ProgramTrace with one StepTrace per step.

        Raises:
            TypeError: program is not a Program instance.
        """
        if not isinstance(program, Program):
            raise TypeError(
                f"ProgramRunner.run() requires a Program, "
                f"got {type(program).__name__!r}"
            )

        trace = ProgramTrace(program_id=program.program_id)
        run_start = time.monotonic()
        aborted = False

        logger.info(
            "[program_runner] start program_id=%r steps=%d",
            program.program_id,
            len(program.steps),
        )

        for i, step in enumerate(program.steps):
            if aborted:
                trace.step_traces.append(
                    StepTrace(
                        step_index=i,
                        action=step.action,
                        verdict="skip",
                        result=None,
                        error="execution aborted by a prior denied step",
                        duration_seconds=0.0,
                    )
                )
                continue

            step_trace = self._execute_step(i, step, context)
            trace.step_traces.append(step_trace)

            if step_trace.verdict != "allow":
                aborted = True
                trace.aborted_at_step = i
                logger.warning(
                    "[program_runner] program_id=%r aborted at step %d "
                    "action=%r verdict=%r error=%r",
                    program.program_id,
                    i,
                    step.action,
                    step_trace.verdict,
                    step_trace.error,
                )

        trace.total_duration_seconds = round(time.monotonic() - run_start, 6)
        trace.ok = (not aborted) and all(
            st.verdict == "allow" for st in trace.step_traces
        )

        logger.info(
            "[program_runner] done program_id=%r ok=%s steps_run=%d duration=%.4fs",
            program.program_id,
            trace.ok,
            len(trace.step_traces),
            trace.total_duration_seconds,
        )

        return trace

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        index: int,
        step: Step,
        context: dict[str, Any] | None,
    ) -> StepTrace:
        """Execute a single step and return its StepTrace (never raises)."""
        step_start = time.monotonic()

        # --- 1. Validate action is in allowed set ---
        if step.action not in self._allowed_actions:
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="deny",
                result=None,
                error=(
                    f"action {step.action!r} is not in the allowed action set; "
                    f"allowed: {sorted(self._allowed_actions)}"
                ),
                duration_seconds=round(time.monotonic() - step_start, 6),
            )

        # --- 2. Compile step action → ExecutionPlan ---
        timeout = float(step.params.get("timeout_seconds", self._default_timeout))
        # Build intent dict: workflow is the action name; forward relevant params
        intent: dict[str, Any] = {
            "workflow": step.action,
            "timeout_seconds": timeout,
        }
        # Forward workflow-specific params (e.g. top_n for word_frequency)
        for key in ("top_n",):
            if key in step.params:
                intent[key] = step.params[key]

        try:
            plan = self._compiler.compile(intent=intent, world=None)
        except ValueError as exc:
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="deny",
                result=None,
                error=f"compile error: {exc}",
                duration_seconds=round(time.monotonic() - step_start, 6),
            )

        # DirectExecutionPlan means the compiler did not recognise the workflow —
        # action was in allowed_actions but not in SUPPORTED_WORKFLOWS.
        if isinstance(plan, DirectExecutionPlan):
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="deny",
                result=None,
                error=(
                    f"action {step.action!r} is not a supported program workflow; "
                    "supported: "
                    + ", ".join(sorted(DeterministicTaskCompiler.SUPPORTED_WORKFLOWS))
                ),
                duration_seconds=round(time.monotonic() - step_start, 6),
            )

        # --- 3. Build execution context (step params override caller context) ---
        exec_context: dict[str, Any] = {}
        if context:
            exec_context.update(context)
        if "input" in step.params:
            exec_context["input"] = step.params["input"]

        # --- 4. Execute in sandbox ---
        assert isinstance(plan, ProgramExecutionPlan)  # guaranteed by check above
        try:
            result = self._executor.execute(plan=plan, context=exec_context)
        except TypeError as exc:
            # ProgramExecutor raises TypeError only for wrong plan type.
            # Since we checked isinstance(plan, ProgramExecutionPlan) above,
            # this should not happen, but we handle it for completeness.
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="deny",
                result=None,
                error=f"executor type error: {exc}",
                duration_seconds=round(time.monotonic() - step_start, 6),
            )

        duration = round(time.monotonic() - step_start, 6)

        # --- 5. Interpret executor result ---
        if result.get("ok"):
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="allow",
                result=result.get("result"),
                error=None,
                duration_seconds=duration,
            )
        else:
            return StepTrace(
                step_index=index,
                action=step.action,
                verdict="deny",
                result=None,
                error=result.get("error", "unknown execution error"),
                duration_seconds=duration,
            )
