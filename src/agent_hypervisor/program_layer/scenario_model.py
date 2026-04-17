"""
scenario_model.py — SYS-3 Comparative Playground data models.

A **Scenario** binds ONE program to MULTIPLE worlds.  The point of SYS-3 is
to make visible a single deterministic claim:

    The same program produces different outcomes under different worlds.
    program ≠ authority; world = authority.

Data model layering (all frozen dataclasses, all with stable ``to_dict`` /
``from_dict`` matching the house style in ``review_models.py``):

    WorldRef                 — (world_id, version) pair.
    Scenario                 — one program bound to N worlds.  Program may be
                               referenced by id (loaded from ProgramStore) or
                               embedded as a list of steps (self-contained).
    StepOutcome              — one row per (step, world): stage + verdict +
                               reason + rule_kind.  The deterministic rule
                               class surfaces WHY a step was allowed/denied.
    WorldResult              — all step outcomes for a single world plus the
                               preview verdict and replay verdict.
    ScenarioDivergencePoint  — a step_index where at least two worlds produced
                               different (verdict, rule_kind) values.
    DivergenceReport         — the set of divergence points for a scenario
                               run plus ``all_agree`` for quick checks.
    ScenarioResult           — the full run: per-world results + divergence
                               + a fresh ``run_id`` and ``ran_at`` timestamp.

Nothing here executes.  These are pure value types.  The runner in
``scenario_runner.py`` composes them from existing primitives
(``check_compatibility``, ``ReplayEngine.replay_under_world``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional

from .review_models import CandidateStep


# ---------------------------------------------------------------------------
# Enums (as string Literals — keep serialisation trivial)
# ---------------------------------------------------------------------------


StepStage = Literal["preview", "replay", "skipped"]
StepVerdict = Literal["allow", "deny", "skip"]
RuleKind = Literal["capability", "schema", "taint", "policy", "execution"]
ReplayVerdict = Literal[
    "allow", "deny", "partial_failure", "denied_at_preview"
]


_VALID_STAGES = frozenset({"preview", "replay", "skipped"})
_VALID_VERDICTS = frozenset({"allow", "deny", "skip"})
_VALID_RULE_KINDS = frozenset(
    {"capability", "schema", "taint", "policy", "execution"}
)
_VALID_REPLAY_VERDICTS = frozenset(
    {"allow", "deny", "partial_failure", "denied_at_preview"}
)


# ---------------------------------------------------------------------------
# WorldRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorldRef:
    """A (world_id, version) pair used to pin a scenario to a concrete world.

    version is required and must be non-empty.  "latest" is forbidden: a
    scenario must be deterministic, and pinning to "latest" would let a new
    world release silently change the result.
    """

    world_id: str
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, str) or not self.world_id.strip():
            raise ValueError(
                f"WorldRef.world_id must be a non-empty string, got {self.world_id!r}"
            )
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError(
                f"WorldRef.version must be a non-empty string, got {self.version!r}"
            )
        if self.version.strip().lower() == "latest":
            raise ValueError(
                "WorldRef.version must be a concrete version; 'latest' is not "
                "permitted because it defeats scenario determinism."
            )

    @property
    def key(self) -> str:
        """Stable flat key for cross-world comparison ("id@version")."""
        return f"{self.world_id}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {"world_id": self.world_id, "version": self.version}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorldRef":
        return cls(world_id=str(data["world_id"]), version=str(data["version"]))


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


def make_scenario_run_id() -> str:
    """Generate a stable, unique scenario-run identifier."""
    return f"scn-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class Scenario:
    """One program bound to N worlds.

    Exactly one of ``program_id`` or ``program_steps`` must be set.

        program_id     — references a ReviewedProgram already in a ProgramStore.
        program_steps  — inline tuple of CandidateStep that the runner will
                         materialise into an ephemeral ReviewedProgram (useful
                         for bundled scenarios that ship with the package).

    worlds must contain at least two distinct WorldRefs — otherwise there is
    nothing to compare and the "comparative" part of the playground is moot.
    """

    scenario_id: str
    name: str
    worlds: tuple[WorldRef, ...]
    program_id: Optional[str] = field(default=None)
    program_steps: Optional[tuple[CandidateStep, ...]] = field(default=None)
    description: str = field(default="")
    input: Optional[dict[str, Any]] = field(default=None, hash=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError(
                f"Scenario.scenario_id must be a non-empty string, got {self.scenario_id!r}"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"Scenario.name must be a non-empty string, got {self.name!r}"
            )
        if not isinstance(self.worlds, tuple):
            raise TypeError(
                f"Scenario.worlds must be a tuple, got {type(self.worlds).__name__!r}"
            )
        if len(self.worlds) < 2:
            raise ValueError(
                "Scenario.worlds must contain at least two WorldRefs; "
                f"got {len(self.worlds)}"
            )
        for i, w in enumerate(self.worlds):
            if not isinstance(w, WorldRef):
                raise TypeError(
                    f"Scenario.worlds[{i}] must be a WorldRef, "
                    f"got {type(w).__name__!r}"
                )
        keys = [w.key for w in self.worlds]
        if len(set(keys)) != len(keys):
            raise ValueError(
                f"Scenario.worlds must not contain duplicate (id, version) "
                f"pairs; got {keys}"
            )

        has_id = self.program_id is not None and str(self.program_id).strip() != ""
        has_steps = self.program_steps is not None and len(self.program_steps) > 0
        if has_id == has_steps:
            raise ValueError(
                "Scenario must specify exactly one of program_id or "
                "program_steps (got both or neither)."
            )
        if has_steps:
            if not isinstance(self.program_steps, tuple):
                raise TypeError(
                    "Scenario.program_steps must be a tuple, "
                    f"got {type(self.program_steps).__name__!r}"
                )
            for i, s in enumerate(self.program_steps):
                if not isinstance(s, CandidateStep):
                    raise TypeError(
                        f"Scenario.program_steps[{i}] must be a CandidateStep, "
                        f"got {type(s).__name__!r}"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "program_id": self.program_id,
            "program_steps": (
                [s.to_dict() for s in self.program_steps]
                if self.program_steps is not None
                else None
            ),
            "worlds": [w.to_dict() for w in self.worlds],
            "input": self.input,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scenario":
        raw_steps = data.get("program_steps")
        steps: Optional[tuple[CandidateStep, ...]] = None
        if raw_steps:
            steps = tuple(CandidateStep.from_dict(s) for s in raw_steps)
        return cls(
            scenario_id=str(data["scenario_id"]),
            name=str(data.get("name") or data["scenario_id"]),
            description=str(data.get("description") or ""),
            program_id=data.get("program_id"),
            program_steps=steps,
            worlds=tuple(WorldRef.from_dict(w) for w in data["worlds"]),
            input=data.get("input"),
        )


# ---------------------------------------------------------------------------
# Per-step outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepOutcome:
    """One row per (step, world).

    ``stage`` describes where the verdict was produced:
        preview  — the compatibility pre-check decided this step's fate.
        replay   — the replay engine executed (or attempted) this step.
        skipped  — this step was never reached because a prior step denied.

    ``rule_kind`` names the class of deterministic rule that produced the
    verdict.  Every non-"allow" verdict carries a non-empty ``reason``.
    """

    step_index: int
    action: str
    stage: StepStage
    verdict: StepVerdict
    reason: str
    rule_kind: RuleKind

    def __post_init__(self) -> None:
        if self.stage not in _VALID_STAGES:
            raise ValueError(
                f"StepOutcome.stage must be one of {sorted(_VALID_STAGES)}, "
                f"got {self.stage!r}"
            )
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"StepOutcome.verdict must be one of {sorted(_VALID_VERDICTS)}, "
                f"got {self.verdict!r}"
            )
        if self.rule_kind not in _VALID_RULE_KINDS:
            raise ValueError(
                f"StepOutcome.rule_kind must be one of "
                f"{sorted(_VALID_RULE_KINDS)}, got {self.rule_kind!r}"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError(
                "StepOutcome.reason must be a non-empty string (deterministic "
                "explanation required for every outcome)."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "stage": self.stage,
            "verdict": self.verdict,
            "reason": self.reason,
            "rule_kind": self.rule_kind,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StepOutcome":
        return cls(
            step_index=int(data["step_index"]),
            action=str(data["action"]),
            stage=str(data["stage"]),  # type: ignore[arg-type]
            verdict=str(data["verdict"]),  # type: ignore[arg-type]
            reason=str(data["reason"]),
            rule_kind=str(data["rule_kind"]),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Per-world result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorldResult:
    """Result for one world inside a scenario run."""

    world_id: str
    world_version: str
    preview_compatible: bool
    replay_verdict: ReplayVerdict
    step_outcomes: tuple[StepOutcome, ...]

    def __post_init__(self) -> None:
        if self.replay_verdict not in _VALID_REPLAY_VERDICTS:
            raise ValueError(
                f"WorldResult.replay_verdict must be one of "
                f"{sorted(_VALID_REPLAY_VERDICTS)}, got {self.replay_verdict!r}"
            )
        if not isinstance(self.step_outcomes, tuple):
            raise TypeError(
                "WorldResult.step_outcomes must be a tuple, "
                f"got {type(self.step_outcomes).__name__!r}"
            )
        for i, o in enumerate(self.step_outcomes):
            if not isinstance(o, StepOutcome):
                raise TypeError(
                    f"WorldResult.step_outcomes[{i}] must be a StepOutcome, "
                    f"got {type(o).__name__!r}"
                )

    @property
    def key(self) -> str:
        return f"{self.world_id}@{self.world_version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "world_version": self.world_version,
            "preview_compatible": self.preview_compatible,
            "replay_verdict": self.replay_verdict,
            "step_outcomes": [o.to_dict() for o in self.step_outcomes],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorldResult":
        return cls(
            world_id=str(data["world_id"]),
            world_version=str(data["world_version"]),
            preview_compatible=bool(data["preview_compatible"]),
            replay_verdict=str(data["replay_verdict"]),  # type: ignore[arg-type]
            step_outcomes=tuple(
                StepOutcome.from_dict(o) for o in data.get("step_outcomes", [])
            ),
        )


# ---------------------------------------------------------------------------
# Divergence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioDivergencePoint:
    """A step index where at least two worlds disagreed.

    ``verdicts_by_world`` and ``reasons_by_world`` are keyed by the world's
    flat "id@version" key (matches ``WorldResult.key``).  Every world in the
    scenario contributes exactly one entry.
    """

    step_index: int
    action: str
    verdicts_by_world: Mapping[str, str]
    reasons_by_world: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "verdicts_by_world": dict(self.verdicts_by_world),
            "reasons_by_world": dict(self.reasons_by_world),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioDivergencePoint":
        return cls(
            step_index=int(data["step_index"]),
            action=str(data["action"]),
            verdicts_by_world=dict(data.get("verdicts_by_world", {})),
            reasons_by_world=dict(data.get("reasons_by_world", {})),
        )


@dataclass(frozen=True)
class DivergenceReport:
    """Summary of cross-world divergence for a scenario run."""

    scenario_id: str
    divergence_points: tuple[ScenarioDivergencePoint, ...]
    all_agree: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "all_agree": self.all_agree,
            "divergence_points": [p.to_dict() for p in self.divergence_points],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DivergenceReport":
        return cls(
            scenario_id=str(data["scenario_id"]),
            all_agree=bool(data["all_agree"]),
            divergence_points=tuple(
                ScenarioDivergencePoint.from_dict(p)
                for p in data.get("divergence_points", [])
            ),
        )


# ---------------------------------------------------------------------------
# ScenarioResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioResult:
    """Full outcome of a single ``run_scenario`` call.

    Only ``run_id`` and ``ran_at`` are non-deterministic across runs of the
    same scenario; every other field is a deterministic function of the
    program and the selected worlds.
    """

    scenario_id: str
    program_id: str
    world_results: tuple[WorldResult, ...]
    divergence: DivergenceReport
    run_id: str
    ran_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "program_id": self.program_id,
            "run_id": self.run_id,
            "ran_at": self.ran_at,
            "world_results": [w.to_dict() for w in self.world_results],
            "divergence": self.divergence.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioResult":
        return cls(
            scenario_id=str(data["scenario_id"]),
            program_id=str(data["program_id"]),
            world_results=tuple(
                WorldResult.from_dict(w) for w in data.get("world_results", [])
            ),
            divergence=DivergenceReport.from_dict(data["divergence"]),
            run_id=str(data["run_id"]),
            ran_at=str(data["ran_at"]),
        )

    def scrub_run_metadata(self) -> dict[str, Any]:
        """Return ``to_dict()`` with ``run_id`` and ``ran_at`` removed.

        Useful for stability assertions: two runs of the same scenario on
        identical inputs must produce identical scrubbed dicts.
        """
        d = self.to_dict()
        d.pop("run_id", None)
        d.pop("ran_at", None)
        return d


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
