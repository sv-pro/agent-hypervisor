"""
compatibility.py — Deterministic program/world compatibility checks.

The authority check: given a ReviewedProgram's minimized_steps and a
WorldDescriptor, decide whether the program could lawfully replay under
that world.  This is a pure validation pass — no execution, no side
effects, no mutation.

Output contracts:

    ProgramWorldCompatibility — per-step verdicts for a single (program, world)
    ProgramWorldDiff          — side-by-side verdicts for (program, world_a, world_b)

Both shapes are JSON-serializable and stable within SYS-2 light.

Why this module exists separately from world_validator.py:
    - world_validator returns violations about a ``Program`` with ``Step``s.
    - compatibility works directly on a ReviewedProgram's ``CandidateStep``s
      (the shape stored in ProgramStore), and attaches world identity so a
      single verdict carries the full "who, what, which world" triple.

    compatibility still delegates the per-step check to validate_step to keep
    the authority logic in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .program_model import Step
from .program_store import ProgramStore
from .review_models import CandidateStep, ReviewedProgram
from .world_registry import WorldDescriptor, WorldRegistry
from .world_validator import validate_step


# ---------------------------------------------------------------------------
# Per-step and summary models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepCompatibility:
    """
    Verdict for a single step against a world.

    Fields:
        step_index          — 0-based index in minimized_steps
        action              — the step's tool/action name
        allowed             — True if the world permits this action
        reason              — short human-readable explanation
        missing_capability  — action name that is absent from the world, if any

    The ``schema_issue`` slot reserved in the spec is not emitted by this
    module (schema-level validation is the compiler's job, not SYS-2's).
    """

    step_index: int
    action: str
    allowed: bool
    reason: str
    missing_capability: Optional[str] = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "allowed": self.allowed,
            "reason": self.reason,
            "missing_capability": self.missing_capability,
        }


@dataclass(frozen=True)
class CompatibilitySummary:
    """Aggregate counts derived from a list of StepCompatibility."""

    allowed_steps: int
    denied_steps: int
    restricted_actions: tuple[str, ...]  # unique actions that were denied

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_steps": self.allowed_steps,
            "denied_steps": self.denied_steps,
            "restricted_actions": list(self.restricted_actions),
        }


@dataclass(frozen=True)
class ProgramWorldCompatibility:
    """
    Full compatibility verdict for a program under one world.

    ``compatible`` is True iff every step is allowed.  Callers that want to
    allow partial replay should inspect ``step_results`` directly.
    """

    program_id: str
    world_id: str
    world_version: str
    compatible: bool
    step_results: tuple[StepCompatibility, ...]
    summary: CompatibilitySummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "world_id": self.world_id,
            "world_version": self.world_version,
            "compatible": self.compatible,
            "step_results": [s.to_dict() for s in self.step_results],
            "summary": self.summary.to_dict(),
        }


# ---------------------------------------------------------------------------
# Divergence model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DivergencePoint:
    """A single step where two worlds give different verdicts."""

    step_index: int
    action: str
    world_a: str  # "allowed" or "denied: <reason>"
    world_b: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "world_a": self.world_a,
            "world_b": self.world_b,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProgramWorldDiff:
    """
    Side-by-side compatibility verdict for one program across two worlds.

    Fields:
        program_id        — the program being compared
        world_a, world_b  — {id, version} pairs for each world
        both_compatible   — True iff compatibility holds under BOTH worlds
        divergence_points — steps where the two worlds disagree
    """

    program_id: str
    world_a: dict[str, str]
    world_b: dict[str, str]
    both_compatible: bool
    divergence_points: tuple[DivergencePoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "world_a": dict(self.world_a),
            "world_b": dict(self.world_b),
            "both_compatible": self.both_compatible,
            "divergence_points": [d.to_dict() for d in self.divergence_points],
        }


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------


def check_compatibility(
    program: ReviewedProgram,
    world: WorldDescriptor,
) -> ProgramWorldCompatibility:
    """
    Check every minimized step against the world's allowed_actions.

    Deterministic: same program + same world always produces the same
    verdict.  No side effects.

    Args:
        program: the ReviewedProgram whose minimized_steps will be checked.
        world:   the WorldDescriptor defining allowed_actions.

    Returns:
        A ProgramWorldCompatibility with per-step results and summary.

    Notes:
        - An empty minimized_steps list is reported as compatible=True (a
          program with no steps cannot violate any world).
        - The action and its validate_step violation message are surfaced
          verbatim in ``StepCompatibility.reason`` for auditability.
    """
    if not isinstance(program, ReviewedProgram):
        raise TypeError(
            f"check_compatibility() requires a ReviewedProgram, "
            f"got {type(program).__name__!r}"
        )
    if not isinstance(world, WorldDescriptor):
        raise TypeError(
            f"check_compatibility() requires a WorldDescriptor, "
            f"got {type(world).__name__!r}"
        )

    step_results: list[StepCompatibility] = []
    restricted: list[str] = []

    for i, cs in enumerate(program.minimized_steps):
        violation = validate_step(
            Step(action=cs.tool, params=cs.params),
            world.allowed_actions,
            step_index=i,
        )
        if violation is None:
            step_results.append(
                StepCompatibility(
                    step_index=i,
                    action=cs.tool,
                    allowed=True,
                    reason="action present in world",
                )
            )
        else:
            if cs.tool not in restricted:
                restricted.append(cs.tool)
            step_results.append(
                StepCompatibility(
                    step_index=i,
                    action=cs.tool,
                    allowed=False,
                    reason=violation.reason,
                    missing_capability=cs.tool,
                )
            )

    allowed = sum(1 for s in step_results if s.allowed)
    denied = len(step_results) - allowed
    summary = CompatibilitySummary(
        allowed_steps=allowed,
        denied_steps=denied,
        restricted_actions=tuple(restricted),
    )

    return ProgramWorldCompatibility(
        program_id=program.id,
        world_id=world.world_id,
        world_version=world.version,
        compatible=(denied == 0),
        step_results=tuple(step_results),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Preview (registry-aware wrapper)
# ---------------------------------------------------------------------------


def preview_program_under_world(
    program_id: str,
    world_id: str,
    version: Optional[str],
    store: ProgramStore,
    registry: WorldRegistry,
) -> ProgramWorldCompatibility:
    """
    Load a stored program and preview its compatibility under a world.

    Looks up the world via ``registry.get(world_id, version)`` and the
    program via ``store.load(program_id)``.  Preview does not execute and
    does not mutate either side.

    Raises:
        KeyError:             program or world does not exist.
        WorldNotFoundError:   world_id/version is unknown to the registry.
    """
    program = store.load(program_id)
    world = registry.get(world_id, version)
    return check_compatibility(program, world)


# ---------------------------------------------------------------------------
# Cross-world divergence
# ---------------------------------------------------------------------------


def compare_program_across_worlds(
    program_id: str,
    world_a_id: str,
    world_a_version: Optional[str],
    world_b_id: str,
    world_b_version: Optional[str],
    store: ProgramStore,
    registry: WorldRegistry,
) -> ProgramWorldDiff:
    """
    Run compatibility under two worlds and return the divergence points.

    A "divergence point" is a step where one world allows the action and the
    other denies it.  Steps that are allowed or denied in both worlds are
    not emitted.

    ``both_compatible`` is True only when the program is fully compatible
    under both worlds.
    """
    program = store.load(program_id)
    world_a = registry.get(world_a_id, world_a_version)
    world_b = registry.get(world_b_id, world_b_version)

    compat_a = check_compatibility(program, world_a)
    compat_b = check_compatibility(program, world_b)

    divergences: list[DivergencePoint] = []
    for sa, sb in zip(compat_a.step_results, compat_b.step_results):
        if sa.allowed == sb.allowed:
            continue
        reason = (
            f"{world_b.world_id} denies {sa.action!r} ({sb.reason})"
            if sa.allowed
            else f"{world_a.world_id} denies {sa.action!r} ({sa.reason})"
        )
        divergences.append(
            DivergencePoint(
                step_index=sa.step_index,
                action=sa.action,
                world_a=_verdict_label(sa),
                world_b=_verdict_label(sb),
                reason=reason,
            )
        )

    return ProgramWorldDiff(
        program_id=program.id,
        world_a={"id": world_a.world_id, "version": world_a.version},
        world_b={"id": world_b.world_id, "version": world_b.version},
        both_compatible=(compat_a.compatible and compat_b.compatible),
        divergence_points=tuple(divergences),
    )


def _verdict_label(step: StepCompatibility) -> str:
    return "allowed" if step.allowed else f"denied: {step.reason}"
