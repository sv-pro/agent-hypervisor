"""
interfaces.py — Clean extension point protocols for the Program Layer.

These are structural interfaces (Protocols). Nothing implements them yet
beyond the stubs in this package. They define where future components
plug in without constraining their implementation.

Three interfaces:

    TaskCompiler     — compile(intent, world) -> ExecutionPlan
    Executor         — execute(plan, context) -> Result
    ProgramRegistry  — store(program) / load(program_id)  [stub class]

Design principle:
    "Programs may define *how* tasks are executed, but never *what* is possible.
     That remains defined by the World Kernel."

    TaskCompiler and Executor see only post-enforcement state. They never
    interact with IRBuilder, CompiledPolicy, ProvenanceFirewall, or PolicyEngine.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .execution_plan import ExecutionPlan

# Result is intentionally untyped at this layer.
# Execution results are heterogeneous — the caller knows the shape.
Result = Any


@runtime_checkable
class TaskCompiler(Protocol):
    """
    Compile an intent and world context into an ExecutionPlan.

    Intent:  a structured description of the task to perform.
             (e.g. a string, a goal object, a parsed NL query)
    World:   the compiled world context the plan must operate within.
             (e.g. CompiledPolicy, tool registry, session state)

    Returns an ExecutionPlan that the Executor can dispatch.

    Implementations must not:
    - Call IRBuilder or modify compiled policy
    - Make policy decisions (those are complete before compile() is called)
    - Raise on unknown intents — return a DirectExecutionPlan as fallback
    """

    def compile(self, intent: Any, world: Any) -> ExecutionPlan:
        """Return an ExecutionPlan for the given intent within the world."""
        ...


@runtime_checkable
class Executor(Protocol):
    """
    Execute an ExecutionPlan within a given context.

    Plan:    the ExecutionPlan to execute (direct or program)
    Context: execution environment (tool registry, session, args, etc.)

    Returns a Result (any JSON-serialisable value).

    Implementations must not:
    - Re-run policy enforcement (enforcement is already complete)
    - Modify the plan (plans are frozen)
    - Swallow errors silently — raise or return an error-bearing Result
    """

    def execute(self, plan: ExecutionPlan, context: Any) -> Result:
        """Execute the plan and return the result."""
        ...


class ProgramRegistry:
    """
    Stub: future store for reviewed and attested programs.

    In the Program Ladder model, programs progress through states:
        disposable → observed → reviewed → attested

    The registry is the persistence layer for reviewed/attested programs.
    It is not implemented in Phase 1 — all methods raise NotImplementedError.

    This class exists to define the interface and reserve the namespace.
    """

    def store(self, program: Any) -> str:
        """
        Persist a program and return its assigned program_id.

        Not yet implemented.
        """
        raise NotImplementedError(
            "ProgramRegistry.store() is not yet implemented. "
            "See docs/architecture/program_layer.md §4 for the planned interface."
        )

    def load(self, program_id: str) -> Any:
        """
        Load a previously stored program by id.

        Not yet implemented.
        """
        raise NotImplementedError(
            "ProgramRegistry.load() is not yet implemented. "
            "See docs/architecture/program_layer.md §4 for the planned interface."
        )
