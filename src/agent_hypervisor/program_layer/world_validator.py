"""
world_validator.py — Pre-execution program validation against the world.

Before any step executes, the world validator checks the entire program
for constraint violations.  This is a static, deterministic check:

    For each step:
        1. Check the action exists in the allowed action set.
        2. Reject the step if the action is absent.

If any step violates a constraint, execution of the ENTIRE program is
denied — no steps run.  This is stricter than the step-by-step abort
in ProgramRunner (which runs steps until the first deny); the pre-check
catches violations before any side effects occur.

The validator operates on an ``allowed_actions`` frozenset, not on a live
CompiledPolicy.  The caller is responsible for deriving ``allowed_actions``
from the world:

    - From a CompiledPolicy: ``frozenset(policy.action_space)`` gives
      manifest-level actions.  For program-layer workflows, use the
      intersection with ``DeterministicTaskCompiler.SUPPORTED_WORKFLOWS``.
    - From ProgramRunner: pass the same ``allowed_actions`` used to
      construct the runner.
    - Default: ``DeterministicTaskCompiler.SUPPORTED_WORKFLOWS``.

Why static pre-validation?
    Step-by-step execution aborts on first deny but the earlier steps have
    already run.  Pre-validation rejects the program before any step runs,
    which is safer when steps have side effects (even sandboxed ones) or
    when the caller wants an up-front list of all violations.

Usage::

    from program_layer.world_validator import validate_program
    from program_layer.task_compiler import DeterministicTaskCompiler

    violations = validate_program(program, DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)
    if violations:
        # Reject the program before any execution
        for v in violations:
            print(f"DENY: {v}")
    else:
        trace = runner.run(program)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Collection

from .program_model import Program, Step


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepViolation:
    """A constraint violation for a single step."""

    step_index: int
    action: str
    reason: str

    def __str__(self) -> str:
        return f"step[{self.step_index}] action={self.action!r}: {self.reason}"


@dataclass(frozen=True)
class ValidationResult:
    """
    Outcome of validate_program().

    Fields:
        ok         — True if no violations were found; the program may execute.
        violations — ordered list of constraint violations (empty when ok=True).
    """

    ok: bool
    violations: tuple[StepViolation, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """JSON-safe dict, suitable for logging."""
        return {
            "ok": self.ok,
            "violations": [
                {
                    "step_index": v.step_index,
                    "action": v.action,
                    "reason": v.reason,
                }
                for v in self.violations
            ],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_program(
    program: Program,
    allowed_actions: Collection[str],
) -> ValidationResult:
    """
    Validate every step of program against allowed_actions.

    Checks each step in order.  Collects ALL violations before returning
    so the caller gets a complete picture, not just the first failure.

    Args:
        program:         the Program to validate (frozen; not mutated).
        allowed_actions: collection of action names the program may use.
                         Any step whose action is absent → violation.

    Returns:
        ValidationResult with ok=True and empty violations if every step's
        action is in allowed_actions.
        ValidationResult with ok=False and one StepViolation per failing
        step otherwise.

    Raises:
        TypeError: program is not a Program instance.
    """
    if not isinstance(program, Program):
        raise TypeError(
            f"validate_program() requires a Program, "
            f"got {type(program).__name__!r}"
        )

    allowed = frozenset(allowed_actions)
    violations: list[StepViolation] = []

    for i, step in enumerate(program.steps):
        violation = _check_step(i, step, allowed)
        if violation is not None:
            violations.append(violation)

    return ValidationResult(
        ok=len(violations) == 0,
        violations=tuple(violations),
    )


def validate_step(
    step: Step,
    allowed_actions: Collection[str],
    step_index: int = 0,
) -> StepViolation | None:
    """
    Validate a single step against allowed_actions.

    Returns a StepViolation if the step is invalid, None if it is valid.
    Useful for incremental validation or early-exit scenarios.

    Args:
        step:            the Step to validate.
        allowed_actions: collection of allowed action names.
        step_index:      0-based position used in the StepViolation message.
    """
    return _check_step(step_index, step, frozenset(allowed_actions))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_step(
    index: int,
    step: Step,
    allowed: frozenset[str],
) -> StepViolation | None:
    """Return a StepViolation if the step violates a constraint, else None."""
    if step.action not in allowed:
        return StepViolation(
            step_index=index,
            action=step.action,
            reason=(
                f"action not in allowed set; "
                f"allowed: {sorted(allowed)}"
            ),
        )
    return None
