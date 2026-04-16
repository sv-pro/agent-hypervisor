"""
review_lifecycle.py — Program review lifecycle management (PL-3).

Provides the programmatic API for advancing a ReviewedProgram through its
lifecycle states:

    proposed → reviewed → accepted | rejected

Functions:
    propose_program()  — create a new ReviewedProgram in PROPOSED status
    minimize_program() — apply deterministic minimization to original_steps
    review_program()   — transition proposed → reviewed (add reviewer notes)
    accept_program()   — transition reviewed → accepted (world validation first)
    reject_program()   — transition reviewed → rejected

Status transitions are strictly enforced:
    - propose_program()  always creates a fresh PROPOSED program.
    - review_program()   requires current status == PROPOSED.
    - accept_program()   requires current status == REVIEWED.
    - reject_program()   requires current status == REVIEWED.

Calling a lifecycle function on a program in the wrong state raises
InvalidTransitionError before any write occurs.

World validation in accept_program():
    Every tool in minimized_steps must appear in allowed_actions.  If any
    tool is absent, WorldValidationError is raised instead of accepting —
    the store is not modified.

Usage::

    store = ProgramStore("programs/")

    prog = propose_program(
        steps=[CandidateStep(tool="count_words", params={"input": "hello"})],
        trace_id="trace-abc",
        world_version="1.0",
        store=store,
    )
    prog = minimize_program(prog.id, store)
    prog = review_program(prog.id, store, notes="Looks correct.")
    prog = accept_program(prog.id, store, allowed_actions={"count_words"})
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Collection, Optional

from .minimizer import Minimizer
from .program_model import Program, Step
from .program_store import ProgramStore
from .review_models import (
    CandidateStep,
    ProgramDiff,
    ProgramMetadata,
    ProgramStatus,
    ReviewedProgram,
    make_program_id,
)
from .world_validator import validate_program


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidTransitionError(Exception):
    """Raised when a requested status transition is not permitted."""


class WorldValidationError(Exception):
    """Raised when the minimized program fails world validation."""


# ---------------------------------------------------------------------------
# Permitted transitions
# ---------------------------------------------------------------------------

_ALLOWED: frozenset[tuple[ProgramStatus, ProgramStatus]] = frozenset(
    {
        (ProgramStatus.PROPOSED, ProgramStatus.REVIEWED),
        (ProgramStatus.REVIEWED, ProgramStatus.ACCEPTED),
        (ProgramStatus.REVIEWED, ProgramStatus.REJECTED),
    }
)


def _assert_transition(current: ProgramStatus, target: ProgramStatus) -> None:
    if (current, target) not in _ALLOWED:
        allowed_desc = ", ".join(
            f"{a.value} → {b.value}" for a, b in sorted(_ALLOWED)
        )
        raise InvalidTransitionError(
            f"Cannot transition from {current.value!r} to {target.value!r}. "
            f"Allowed transitions: {allowed_desc}"
        )


# ---------------------------------------------------------------------------
# Lifecycle functions
# ---------------------------------------------------------------------------


def propose_program(
    steps: list[CandidateStep],
    trace_id: Optional[str],
    world_version: str,
    store: ProgramStore,
    program_id: Optional[str] = None,
) -> ReviewedProgram:
    """
    Create a new ReviewedProgram in PROPOSED status and save it to the store.

    minimized_steps is initialised to a copy of original_steps (no
    minimization applied yet).  Call minimize_program() afterwards.

    Args:
        steps:          list of CandidateStep (at least one required)
        trace_id:       trace this program was extracted from (may be None)
        world_version:  world manifest version string at creation time
        store:          ProgramStore to persist the program
        program_id:     optional explicit id (auto-generated if None)

    Returns:
        The saved ReviewedProgram with status=PROPOSED.

    Raises:
        ValueError: steps is empty.
        TypeError:  steps contains non-CandidateStep items.
    """
    if not steps:
        raise ValueError("propose_program() requires at least one CandidateStep")
    for i, s in enumerate(steps):
        if not isinstance(s, CandidateStep):
            raise TypeError(
                f"steps[{i}] must be a CandidateStep, got {type(s).__name__!r}"
            )

    prog_id = program_id or make_program_id()
    metadata = ProgramMetadata(
        created_from_trace=trace_id,
        world_version=world_version,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        reviewer_notes=None,
    )
    program = ReviewedProgram(
        id=prog_id,
        status=ProgramStatus.PROPOSED,
        original_steps=tuple(steps),
        minimized_steps=tuple(steps),  # identity until minimize_program() runs
        diff=ProgramDiff(),
        metadata=metadata,
    )
    store.save(program)
    return program


def minimize_program(program_id: str, store: ProgramStore) -> ReviewedProgram:
    """
    Apply deterministic minimization to the original_steps of a stored program.

    Updates minimized_steps and diff in the store.  original_steps are NEVER
    modified.  The program's status is unchanged.

    Args:
        program_id: id of the program to minimize
        store:      ProgramStore containing the program

    Returns:
        The updated ReviewedProgram with minimized_steps and diff set.

    Raises:
        KeyError:   program not found in the store.
        ValueError: stored file is corrupt.
    """
    program = store.load(program_id)
    minimizer = Minimizer()
    minimized_steps, diff = minimizer.minimize(list(program.original_steps))

    updated = dataclasses.replace(
        program,
        minimized_steps=tuple(minimized_steps),
        diff=diff,
    )
    store.save(updated)
    return updated


def review_program(
    program_id: str,
    store: ProgramStore,
    notes: Optional[str] = None,
) -> ReviewedProgram:
    """
    Transition a PROPOSED program to REVIEWED status.

    Optionally attaches reviewer notes to the metadata.

    Args:
        program_id: id of the program to review
        store:      ProgramStore containing the program
        notes:      optional human-readable reviewer notes

    Returns:
        The updated ReviewedProgram with status=REVIEWED.

    Raises:
        KeyError:              program not found.
        InvalidTransitionError: current status is not PROPOSED.
    """
    program = store.load(program_id)
    _assert_transition(program.status, ProgramStatus.REVIEWED)

    new_meta = dataclasses.replace(program.metadata, reviewer_notes=notes)
    updated = dataclasses.replace(
        program,
        status=ProgramStatus.REVIEWED,
        metadata=new_meta,
    )
    store.save(updated)
    return updated


def accept_program(
    program_id: str,
    store: ProgramStore,
    allowed_actions: Optional[Collection[str]] = None,
) -> ReviewedProgram:
    """
    Transition a REVIEWED program to ACCEPTED status.

    Validates every tool in minimized_steps against allowed_actions before
    writing.  Raises WorldValidationError if any step fails; the store is
    not modified in that case.

    Args:
        program_id:      id of the program to accept
        store:           ProgramStore containing the program
        allowed_actions: the world's allowed action set.
                         Defaults to DeterministicTaskCompiler.SUPPORTED_WORKFLOWS.

    Returns:
        The updated ReviewedProgram with status=ACCEPTED.

    Raises:
        KeyError:              program not found.
        InvalidTransitionError: current status is not REVIEWED.
        WorldValidationError:  minimized steps fail world validation.
    """
    from .task_compiler import DeterministicTaskCompiler

    program = store.load(program_id)
    _assert_transition(program.status, ProgramStatus.ACCEPTED)

    if allowed_actions is None:
        allowed_actions = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS

    # World validation: convert minimized CandidateStep → Step and validate
    if program.minimized_steps:
        validation_steps = tuple(
            Step(action=cs.tool, params=cs.params)
            for cs in program.minimized_steps
        )
        validation_prog = Program(
            program_id=program.id,
            steps=validation_steps,
        )
        result = validate_program(validation_prog, allowed_actions)
        if not result.ok:
            msgs = "; ".join(str(v) for v in result.violations)
            raise WorldValidationError(
                f"Program {program_id!r} fails world validation: {msgs}"
            )

    updated = dataclasses.replace(program, status=ProgramStatus.ACCEPTED)
    store.save(updated)
    return updated


def reject_program(
    program_id: str,
    store: ProgramStore,
    reason: Optional[str] = None,
) -> ReviewedProgram:
    """
    Transition a REVIEWED program to REJECTED status.

    Optionally records the rejection reason in reviewer_notes.

    Args:
        program_id: id of the program to reject
        store:      ProgramStore containing the program
        reason:     optional rejection reason (appended to reviewer_notes)

    Returns:
        The updated ReviewedProgram with status=REJECTED.

    Raises:
        KeyError:              program not found.
        InvalidTransitionError: current status is not REVIEWED.
    """
    program = store.load(program_id)
    _assert_transition(program.status, ProgramStatus.REJECTED)

    existing_notes = program.metadata.reviewer_notes
    if reason:
        notes = (
            f"{existing_notes}\n[rejected]: {reason}"
            if existing_notes
            else f"[rejected]: {reason}"
        )
    else:
        notes = existing_notes

    new_meta = dataclasses.replace(program.metadata, reviewer_notes=notes)
    updated = dataclasses.replace(
        program,
        status=ProgramStatus.REJECTED,
        metadata=new_meta,
    )
    store.save(updated)
    return updated
