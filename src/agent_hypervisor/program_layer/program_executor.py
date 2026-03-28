"""
program_executor.py — Stub executor for ProgramExecutionPlan.

ProgramExecutor implements the Executor protocol for program-type plans.
It is intentionally incomplete in Phase 1: it logs the intention and raises
NotImplementedError to make the stub boundary explicit and loud.

Architecture, not functionality.

What this stub does:
    - Accepts a ProgramExecutionPlan
    - Logs the program_id / plan_id so the intent is traceable
    - Raises NotImplementedError with a clear, actionable message

What this stub does NOT do:
    - Execute any code
    - Spawn a sandbox
    - Touch the World Kernel
    - Re-evaluate policy

When a real implementation is added, it replaces the body of execute()
without changing the interface or the call site in execution_router.py.
"""

from __future__ import annotations

import logging
from typing import Any

from .execution_plan import ExecutionPlan, ProgramExecutionPlan
from .interfaces import Result

logger = logging.getLogger(__name__)


class ProgramExecutor:
    """
    Stub executor for ProgramExecutionPlan.

    Satisfies the Executor protocol. Raises NotImplementedError on execute()
    to clearly mark the boundary between scaffolding and a real implementation.

    Replace the body of execute() to introduce real sandbox execution.
    The interface and the dispatch call site (execution_router.py) do not change.
    """

    def execute(self, plan: ExecutionPlan, context: Any) -> Result:
        """
        Execute a ProgramExecutionPlan.

        Args:
            plan:    A ProgramExecutionPlan describing the program to run.
            context: Execution context (tool registry, session args, etc.)
                     Shape is caller-defined; this executor ignores it for now.

        Raises:
            TypeError:          plan is not a ProgramExecutionPlan.
            NotImplementedError: always — sandbox is not yet implemented.
        """
        if not isinstance(plan, ProgramExecutionPlan):
            raise TypeError(
                f"ProgramExecutor requires a ProgramExecutionPlan, "
                f"got {type(plan).__name__!r}. "
                "Use DirectExecutionPlan for direct tool adapter dispatch."
            )

        logger.info(
            "[program_layer] ProgramExecutor: would execute program "
            "plan_id=%r program_id=%r (sandbox not yet implemented)",
            plan.plan_id,
            plan.program_id,
        )

        raise NotImplementedError(
            f"ProgramExecutor: sandbox execution is not yet implemented.\n"
            f"  plan_id:    {plan.plan_id!r}\n"
            f"  program_id: {plan.program_id!r}\n"
            "\n"
            "This is an intentional Phase 1 stub. "
            "Real execution requires a sandboxed environment — "
            "see docs/architecture/program_layer.md §6 for what is "
            "intentionally deferred."
        )
