"""
program_model.py — Minimal, linear program model for Phase 1.

A Program is a finite, linear sequence of Steps.
There are no branches, loops, or dynamic control flow — the program is
fully serialisable and deterministic: given the same world and inputs,
it always produces the same execution path.

Design constraints (from spec):
    - At most MAX_STEPS (10) steps per program.
    - Each step has: action (str) and params (dict).
    - No branching, no loops, no dynamic control flow.
    - Programs and Steps are frozen (immutable) after construction.
    - Programs are identifiable by a stable program_id.

Step.action is matched against the world's allowed action set by
ProgramRunner at execution time. Unknown actions → deny verdict.

Usage::

    program = Program(
        program_id="analysis-v1",
        steps=(
            Step(action="count_words", params={"input": "hello world"}),
            Step(action="normalize_text", params={"input": "HELLO WORLD"}),
        ),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Hard upper bound on steps per program.
# Caller receives ValueError at construction time if exceeded.
MAX_STEPS: int = 10


@dataclass(frozen=True)
class Step:
    """
    A single step in a linear program.

    Fields:
        action  — the action name to invoke; matched against the world's
                  allowed action set by ProgramRunner (unknown → deny).
        params  — key-value parameters for the action.  Passed to the
                  executor as execution context.  Must be JSON-serialisable.
                  Excluded from hash and equality comparisons (structural
                  identity is determined by action only).

    Raises:
        ValueError: action is empty or whitespace-only.
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action.strip():
            raise ValueError(
                f"Step.action must be a non-empty string, got {self.action!r}"
            )


@dataclass(frozen=True)
class Program:
    """
    A minimal, linear program: a finite ordered sequence of Steps.

    Constraints enforced at construction:
        - program_id must be a non-empty string.
        - steps must be a tuple (not a list — enforces immutability at the
          call site).
        - 1 <= len(steps) <= MAX_STEPS.
        - Every element of steps must be a Step instance.

    Programs are frozen after construction.  Callers cannot mutate steps.

    The program_id is stable across re-runs of the same logical program —
    it is used in ProgramTrace for correlation and logging.  It should be
    unique per program definition, not per execution (use UUIDs for the
    latter).

    Example::

        program = Program(
            program_id="analysis-v1",
            steps=(
                Step(action="count_words", params={"input": "hello world"}),
                Step(action="normalize_text", params={"input": "HELLO WORLD"}),
            ),
        )

    Raises:
        ValueError: program_id is empty, steps is empty, or len(steps) > MAX_STEPS.
        TypeError:  steps is not a tuple, or any element is not a Step.
    """

    program_id: str
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.program_id, str) or not self.program_id.strip():
            raise ValueError(
                f"Program.program_id must be a non-empty string, got {self.program_id!r}"
            )
        if not isinstance(self.steps, tuple):
            raise TypeError(
                "Program.steps must be a tuple of Step objects "
                "(use tuple(), not list). "
                f"Got {type(self.steps).__name__!r}."
            )
        if len(self.steps) == 0:
            raise ValueError("Program must have at least one step")
        if len(self.steps) > MAX_STEPS:
            raise ValueError(
                f"Program exceeds maximum step limit: "
                f"{len(self.steps)} steps > MAX_STEPS ({MAX_STEPS}). "
                "Split the program into smaller units or increase MAX_STEPS."
            )
        for i, step in enumerate(self.steps):
            if not isinstance(step, Step):
                raise TypeError(
                    f"Program.steps[{i}] must be a Step instance, "
                    f"got {type(step).__name__!r}"
                )

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):  # type: ignore[override]
        return iter(self.steps)
