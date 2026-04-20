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

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .execution_plan import ExecutionPlan
from .program_store import ProgramStore
from .review_models import ReviewedProgram

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
    Filesystem-backed store for reviewed and attested programs.

    In the Program Ladder model, programs progress through states:
        disposable → observed → reviewed → attested

    The registry is the persistence layer for reviewed/attested programs.
    Each program is stored as a single JSON file via ProgramStore.

    Args:
        directory: path to the directory where program files are stored.
                   Created automatically on first store() call.
    """

    def __init__(self, directory: str | Path) -> None:
        self._store = ProgramStore(directory)

    def store(self, program: Any) -> str:
        """
        Persist a ReviewedProgram and return its program_id.

        Args:
            program: a ReviewedProgram instance.

        Returns:
            The program's id string.

        Raises:
            TypeError: program is not a ReviewedProgram.
            OSError:   the registry directory cannot be created or written.
        """
        if not isinstance(program, ReviewedProgram):
            raise TypeError(
                f"ProgramRegistry.store() requires a ReviewedProgram, "
                f"got {type(program).__name__!r}"
            )
        self._store.save(program)
        return program.id

    def load(self, program_id: str) -> Any:
        """
        Load a previously stored ReviewedProgram by id.

        Args:
            program_id: the program's unique id.

        Returns:
            The deserialized ReviewedProgram.

        Raises:
            KeyError:   no program with the given id exists.
            ValueError: the stored file is corrupt or schema is mismatched.
        """
        return self._store.load(program_id)
