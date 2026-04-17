"""
scenario_runner.py — SYS-3 multi-world execution engine.

Given a ``Scenario`` (one program + N worlds), this module:

    1. Loads or materialises the ReviewedProgram exactly once.
    2. For each world:
         - Runs ``check_compatibility`` (the preview pass).
         - If compatible, invokes ``ReplayEngine.replay_under_world`` to run
           the same enforcement path used by live execution.
         - Otherwise records ``denied_at_preview`` and skips replay.
    3. Builds ``StepOutcome`` rows that carry a deterministic ``rule_kind``
       explanation for every (step, world) pair.
    4. Calls ``detect_divergence`` to find step indices where the worlds
       disagreed.
    5. Returns a frozen ``ScenarioResult``.

Nothing in this module adds new policy logic — it composes existing
primitives (``compatibility.py``, ``replay_engine.py``) so the authority
boundary remains exactly what SYS-2 and PL-3 already define.

The ``_classify_replay_reason`` helper maps the free-form error strings
produced by ``ProgramRunner`` into one of five deterministic rule classes:

    capability  — world validation said the action is not permitted
    schema      — task compiler rejected the intent shape
    taint       — (reserved) taint rule denial
    policy      — security validation or timeout denial
    execution   — a sandboxed runtime error surfaced from the handler
"""

from __future__ import annotations

from typing import Optional, Sequence

from .compatibility import check_compatibility
from .program_store import ProgramStore
from .replay_engine import ReplayEngine, ReplayTrace
from .review_models import (
    CandidateStep,
    ProgramDiff,
    ProgramMetadata,
    ProgramStatus,
    ReviewedProgram,
)
from .scenario_model import (
    DivergenceReport,
    RuleKind,
    Scenario,
    ScenarioDivergencePoint,
    ScenarioResult,
    StepOutcome,
    WorldResult,
    _utcnow_iso,
    make_scenario_run_id,
)
from .world_registry import WorldDescriptor, WorldRegistry


# ---------------------------------------------------------------------------
# Rule classification
# ---------------------------------------------------------------------------


def _classify_replay_reason(error: Optional[str]) -> RuleKind:
    """Map a ProgramRunner/ReplayEngine error string to a deterministic kind.

    The prefixes here mirror the error strings produced in
    ``replay_engine.py`` and ``program_runner.py``.  Any unrecognised error
    falls back to ``execution`` so the taxonomy is closed but forgiving.
    """
    if error is None:
        return "execution"
    e = error.lower()
    if e.startswith("world validation failed"):
        return "capability"
    if e.startswith("action ") and "is not a supported program workflow" in e:
        return "schema"
    if e.startswith("compile error"):
        return "schema"
    if e.startswith("security validation failed"):
        return "policy"
    if "exceeded timeout" in e:
        return "policy"
    return "execution"


# ---------------------------------------------------------------------------
# Program resolution
# ---------------------------------------------------------------------------


def _materialise_program(
    scenario: Scenario,
    store: Optional[ProgramStore],
) -> ReviewedProgram:
    """Return the ReviewedProgram the scenario should run.

    - If ``scenario.program_id`` is set, load it via ``store.load``.  A store
      is required in that case.
    - Otherwise construct an ephemeral ACCEPTED program from
      ``scenario.program_steps`` (never persisted).
    """
    if scenario.program_id is not None:
        if store is None:
            raise ValueError(
                f"Scenario {scenario.scenario_id!r} references program_id "
                f"{scenario.program_id!r} but no ProgramStore was provided."
            )
        try:
            return store.load(scenario.program_id)
        except KeyError as exc:
            raise KeyError(
                f"Scenario {scenario.scenario_id!r}: program "
                f"{scenario.program_id!r} not found in store"
            ) from exc

    # Inline program_steps path — build an ephemeral ACCEPTED program.
    steps: tuple[CandidateStep, ...] = scenario.program_steps or ()
    prog_id = f"scn-inline-{scenario.scenario_id}"
    metadata = ProgramMetadata(
        created_from_trace=None,
        world_version="scenario-inline",
        created_at=_utcnow_iso(),
        reviewer_notes=f"Inline program for scenario {scenario.scenario_id!r}.",
    )
    return ReviewedProgram(
        id=prog_id,
        status=ProgramStatus.ACCEPTED,
        original_steps=steps,
        minimized_steps=steps,
        diff=ProgramDiff(),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Per-world execution
# ---------------------------------------------------------------------------


def _outcomes_from_preview_only(
    program: ReviewedProgram,
    world: WorldDescriptor,
) -> tuple[WorldResult, bool]:
    """Run ``check_compatibility`` and synthesise StepOutcome rows.

    Returns ``(world_result, compatible)``.  If incompatible, the caller
    should NOT replay; this function builds a full row set already, marking
    the first denied step as ``deny`` and every subsequent step as
    ``skipped``.
    """
    compat = check_compatibility(program, world)
    outcomes: list[StepOutcome] = []
    denied_seen = False
    for sr in compat.step_results:
        if sr.allowed:
            # Compatible step under an incompatible-overall program: still
            # reported as ``preview/allow`` so the per-step matrix is complete.
            outcomes.append(
                StepOutcome(
                    step_index=sr.step_index,
                    action=sr.action,
                    stage="preview",
                    verdict="allow",
                    reason=sr.reason or "action present in world",
                    rule_kind="capability",
                )
            )
        else:
            if not denied_seen:
                outcomes.append(
                    StepOutcome(
                        step_index=sr.step_index,
                        action=sr.action,
                        stage="preview",
                        verdict="deny",
                        reason=sr.reason or "capability absent from world",
                        rule_kind="capability",
                    )
                )
                denied_seen = True
            else:
                outcomes.append(
                    StepOutcome(
                        step_index=sr.step_index,
                        action=sr.action,
                        stage="skipped",
                        verdict="skip",
                        reason="skipped after earlier preview denial",
                        rule_kind="capability",
                    )
                )

    result = WorldResult(
        world_id=world.world_id,
        world_version=world.version,
        preview_compatible=compat.compatible,
        replay_verdict="allow" if compat.compatible else "denied_at_preview",
        step_outcomes=tuple(outcomes),
    )
    return result, compat.compatible


def _outcomes_from_replay(
    program: ReviewedProgram,
    world: WorldDescriptor,
    preview_outcomes: Sequence[StepOutcome],
    replay_trace: ReplayTrace,
) -> WorldResult:
    """Combine the preview pass (all ``allow``) with the replay trace.

    After a successful preview, every ``preview_outcomes`` entry has
    ``verdict="allow"`` and ``stage="preview"``.  Replay then produces a
    ``StepTrace`` per step.  For any step that replay actually executed we
    replace the preview row with a ``stage="replay"`` row that carries the
    real verdict and a classified rule_kind.  Steps that replay marked as
    ``skip`` keep their preview row but are reported as ``stage="skipped"``.
    """
    by_index = {o.step_index: o for o in preview_outcomes}
    merged: list[StepOutcome] = []

    for st in replay_trace.program_trace.step_traces:
        if st.verdict == "allow":
            reason = "executed successfully"
            rule_kind: RuleKind = "execution"
        elif st.verdict == "deny":
            reason = st.error or "denied by replay engine"
            rule_kind = _classify_replay_reason(st.error)
        else:  # skip
            reason = "skipped after earlier replay denial"
            rule_kind = "capability"
        merged.append(
            StepOutcome(
                step_index=st.step_index,
                action=st.action,
                stage="replay" if st.verdict != "skip" else "skipped",
                verdict=st.verdict,
                reason=reason,
                rule_kind=rule_kind,
            )
        )

    # Replay may return fewer step_traces than the program has (e.g. empty
    # minimized_steps path).  Fill any gaps from the preview rows so the
    # matrix is always complete.
    seen = {o.step_index for o in merged}
    for idx in sorted(by_index):
        if idx not in seen:
            merged.append(by_index[idx])
    merged.sort(key=lambda o: o.step_index)

    return WorldResult(
        world_id=world.world_id,
        world_version=world.version,
        preview_compatible=True,
        replay_verdict=replay_trace.final_verdict,
        step_outcomes=tuple(merged),
    )


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


def detect_divergence(
    scenario_id: str,
    world_results: Sequence[WorldResult],
) -> DivergenceReport:
    """Identify step indices where worlds disagreed.

    A divergence at step ``i`` means at least two worlds produced different
    ``(verdict, rule_kind)`` tuples at that index.  Order is preserved from
    the input ``world_results`` sequence so cross-run comparisons stay
    stable (scenarios use tuples, so this is already deterministic).
    """
    if not world_results:
        return DivergenceReport(
            scenario_id=scenario_id,
            divergence_points=(),
            all_agree=True,
        )

    # Determine the union of step indices observed across worlds.
    all_indices: set[int] = set()
    for wr in world_results:
        for o in wr.step_outcomes:
            all_indices.add(o.step_index)

    divergences: list[ScenarioDivergencePoint] = []
    for idx in sorted(all_indices):
        rows_by_world: dict[str, StepOutcome] = {}
        action_seen: Optional[str] = None
        for wr in world_results:
            for o in wr.step_outcomes:
                if o.step_index == idx:
                    rows_by_world[wr.key] = o
                    action_seen = action_seen or o.action
                    break

        verdicts = {k: o.verdict for k, o in rows_by_world.items()}
        # Divergence is measured on verdict alone.  A step that every world
        # allowed is not divergent, even if one world allowed it at preview
        # (no replay) and another allowed it after running the handler.
        if len(set(verdicts.values())) <= 1:
            continue

        reasons = {k: o.reason for k, o in rows_by_world.items()}
        divergences.append(
            ScenarioDivergencePoint(
                step_index=idx,
                action=action_seen or "",
                verdicts_by_world=verdicts,
                reasons_by_world=reasons,
            )
        )

    return DivergenceReport(
        scenario_id=scenario_id,
        divergence_points=tuple(divergences),
        all_agree=not divergences,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_scenario(
    scenario: Scenario,
    *,
    registry: WorldRegistry,
    store: Optional[ProgramStore] = None,
    replay_engine: Optional[ReplayEngine] = None,
) -> ScenarioResult:
    """Run a scenario across its worlds and return a frozen ``ScenarioResult``.

    Execution is deterministic apart from ``run_id`` and ``ran_at``:

        - the program is loaded once and reused across worlds (no mutation).
        - each world is resolved via ``registry.get(world_id, version)``;
          concrete versions are required (``WorldRef.__post_init__`` rejects
          "latest").
        - compatibility preview runs before replay; if preview denies,
          ``replay_verdict`` is ``denied_at_preview`` and ``ReplayEngine`` is
          NOT called for that world.
        - replay is delegated to ``ReplayEngine.replay_under_world`` with
          ``world_source="explicit"`` and ``preview_compatible=True`` so the
          underlying ReplayTrace carries accurate audit metadata.

    The ``input`` attribute on ``Scenario`` is forwarded to replay as the
    ``context`` argument — useful when a scenario wants to seed shared state
    across steps.  Its shape is not validated here.

    Raises:
        KeyError:            program_id unknown in store.
        ValueError:          scenario references program_id but no store.
        WorldNotFoundError:  a world_id/version pair is unknown.
    """
    if not isinstance(scenario, Scenario):
        raise TypeError(
            f"run_scenario() requires a Scenario, got {type(scenario).__name__!r}"
        )
    if not isinstance(registry, WorldRegistry):
        raise TypeError(
            f"run_scenario() requires a WorldRegistry, got {type(registry).__name__!r}"
        )

    program = _materialise_program(scenario, store)
    engine = replay_engine if replay_engine is not None else ReplayEngine()

    world_results: list[WorldResult] = []
    for wref in scenario.worlds:
        world = registry.get(wref.world_id, wref.version)

        preview_result, compatible = _outcomes_from_preview_only(program, world)
        if not compatible:
            world_results.append(preview_result)
            continue

        replay_trace = engine.replay_under_world(
            program=program,
            world=world,
            world_source="explicit",
            preview_compatible=True,
            context=scenario.input,
        )
        world_results.append(
            _outcomes_from_replay(
                program, world, preview_result.step_outcomes, replay_trace
            )
        )

    divergence = detect_divergence(scenario.scenario_id, world_results)

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        program_id=program.id,
        world_results=tuple(world_results),
        divergence=divergence,
        run_id=make_scenario_run_id(),
        ran_at=_utcnow_iso(),
    )
