"""
program_executor.py — ProgramExecutor: runs a ProgramExecutionPlan in the sandbox.

This replaces the Phase 1 stub (which raised NotImplementedError) with a real,
working implementation.  The external interface is unchanged: callers that
previously received NotImplementedError will now receive a structured result dict.

Execution contract:
    - Accepts only ProgramExecutionPlan (TypeError for anything else).
    - Validates the plan before execution (must have program_source).
    - Builds the sandbox runtime from the plan's constraints.
    - Injects bindings from the execution context.
    - Returns a structured result dict (see ExecutionResult below).
    - Never re-evaluates policy — policy is complete before this is called.
    - Fails closed: any error returns ok=False with a structured error, never
      falls through to unsafe execution.

Result shape::

    # Success
    {
        "ok": True,
        "result": <value from emit_result()>,
        "plan_id": "prog-count_words-abc123",
        "execution_mode": "program",
        "duration_seconds": 0.0023,
    }

    # Failure
    {
        "ok": False,
        "error": "program exceeded timeout of 5.0s",
        "error_type": "timeout",   # "timeout" | "security" | "runtime" | "validation"
        "plan_id": "prog-...",
        "execution_mode": "program",
        "duration_seconds": 5.001,
    }

Context dict:
    The caller may pass a context dict with the following optional keys:
        "input"  — the input value injected as read_input() return value
        "args"   — dict of raw tool arguments (used as fallback input)
    Any other keys are ignored.  Context is never evaluated or executed.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .execution_plan import ExecutionPlan, ProgramExecutionPlan
from .interfaces import Result
from .sandbox_runtime import (
    SandboxError,
    SandboxRuntime,
    SandboxSecurityError,
    SandboxTimeoutError,
)

logger = logging.getLogger(__name__)


class ProgramExecutor:
    """
    Execute a ProgramExecutionPlan inside a bounded sandbox.

    Satisfies the Executor protocol (interfaces.py).

    Failure modes (all return ok=False, never raise past the caller):
        - plan is not a ProgramExecutionPlan → TypeError (re-raised)
        - plan.program_source is None        → validation error, ok=False
        - program violates sandbox policy    → security error, ok=False
        - program exceeds timeout            → timeout error, ok=False
        - program raises at runtime          → runtime error, ok=False
    """

    def execute(self, plan: ExecutionPlan, context: Any = None) -> Result:
        """
        Execute a ProgramExecutionPlan in the sandbox and return a result dict.

        Args:
            plan:    A ProgramExecutionPlan describing the program to run.
            context: Optional dict with "input" key (the data read_input() returns)
                     and/or "args" dict (fallback input source).

        Returns:
            A dict with at minimum: ok, plan_id, execution_mode, duration_seconds.
            On success also: result.
            On failure also: error, error_type.

        Raises:
            TypeError: plan is not a ProgramExecutionPlan.
        """
        if not isinstance(plan, ProgramExecutionPlan):
            raise TypeError(
                f"ProgramExecutor requires a ProgramExecutionPlan, "
                f"got {type(plan).__name__!r}. "
                "Use DirectExecutionPlan for direct tool adapter dispatch."
            )

        start = time.monotonic()

        # Validation: program_source must be present
        if not plan.program_source:
            duration = time.monotonic() - start
            logger.warning(
                "[program_layer] validation failed plan_id=%r: program_source is empty",
                plan.plan_id,
            )
            return {
                "ok": False,
                "error": "program_source is required but was not provided",
                "error_type": "validation",
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }

        # Validation: language must be "python" (only supported in Phase 1)
        if plan.language != "python":
            duration = time.monotonic() - start
            logger.warning(
                "[program_layer] unsupported language plan_id=%r lang=%r",
                plan.plan_id,
                plan.language,
            )
            return {
                "ok": False,
                "error": (
                    f"unsupported language {plan.language!r}; "
                    "Phase 1 supports 'python' only"
                ),
                "error_type": "validation",
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }

        # Extract input value from context
        input_value = _extract_input(context)

        # Build and run the sandbox
        runtime = SandboxRuntime(
            allowed_bindings=plan.allowed_bindings,
            timeout_seconds=plan.timeout_seconds,
        )

        try:
            result = runtime.run(
                program_source=plan.program_source,
                input_value=input_value,
            )
            duration = time.monotonic() - start
            logger.info(
                "[program_layer] executed plan_id=%r in %.4fs ok=True",
                plan.plan_id,
                duration,
            )
            return {
                "ok": True,
                "result": result,
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }

        except SandboxTimeoutError as exc:
            duration = time.monotonic() - start
            logger.warning(
                "[program_layer] timeout plan_id=%r after %.4fs: %s",
                plan.plan_id,
                duration,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "error_type": "timeout",
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }

        except SandboxSecurityError as exc:
            duration = time.monotonic() - start
            logger.warning(
                "[program_layer] security violation plan_id=%r: %s",
                plan.plan_id,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "error_type": "security",
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }

        except SandboxError as exc:
            duration = time.monotonic() - start
            logger.warning(
                "[program_layer] runtime error plan_id=%r: %s",
                plan.plan_id,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "error_type": "runtime",
                "plan_id": plan.plan_id,
                "execution_mode": "program",
                "duration_seconds": round(duration, 6),
            }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_input(context: Any) -> Any:
    """
    Pull the input value out of the execution context.

    Context shapes handled:
        {"input": value}          → value
        {"args": {"text": val}}   → val (first positional string arg)
        None / anything else      → None
    """
    if not isinstance(context, dict):
        return None
    if "input" in context:
        return context["input"]
    # Fallback: look for a single string-like value in args
    args = context.get("args")
    if isinstance(args, dict):
        for value in args.values():
            if isinstance(value, (str, bytes)):
                return value
    return None
