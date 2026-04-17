"""
test_scenario_model.py — SYS-3 dataclass invariants and serialisation.

Validates that the frozen value types in ``scenario_model.py`` enforce the
structural guarantees documented in ``docs/comparative-playground.md``:

- ``WorldRef`` rejects empty ids/versions and the literal ``"latest"``.
- ``Scenario`` requires ≥2 distinct worlds and exactly one of
  ``program_id`` or ``program_steps``.
- Every model round-trips through ``to_dict``/``from_dict`` byte-stably.
- ``ScenarioResult.scrub_run_metadata`` strips only the non-deterministic
  ``run_id`` / ``ran_at`` fields.
"""

from __future__ import annotations

import pytest

from agent_hypervisor.program_layer import (
    DivergenceReport,
    Scenario,
    ScenarioDivergencePoint,
    ScenarioResult,
    StepOutcome,
    WorldRef,
    WorldResult,
    make_scenario_run_id,
)
from agent_hypervisor.program_layer.review_models import CandidateStep


# ---------------------------------------------------------------------------
# WorldRef
# ---------------------------------------------------------------------------


def test_world_ref_requires_non_empty_fields():
    with pytest.raises(ValueError):
        WorldRef(world_id="", version="1.0")
    with pytest.raises(ValueError):
        WorldRef(world_id="world_a", version="")


@pytest.mark.parametrize("bad", ["latest", "LATEST", "  latest  "])
def test_world_ref_rejects_latest_version(bad: str):
    with pytest.raises(ValueError):
        WorldRef(world_id="world_a", version=bad)


def test_world_ref_round_trip():
    w = WorldRef(world_id="world_a", version="1.2")
    assert w.key == "world_a@1.2"
    assert WorldRef.from_dict(w.to_dict()) == w


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


def _two_worlds() -> tuple[WorldRef, WorldRef]:
    return (
        WorldRef(world_id="world_strict", version="1.0"),
        WorldRef(world_id="world_balanced", version="1.0"),
    )


def _two_steps() -> tuple[CandidateStep, CandidateStep]:
    return (
        CandidateStep(tool="count_words", params={"input": "hi"}),
        CandidateStep(tool="normalize_text", params={"input": "HI"}),
    )


def test_scenario_rejects_single_world():
    with pytest.raises(ValueError, match="at least two"):
        Scenario(
            scenario_id="s",
            name="s",
            worlds=(WorldRef("w", "1.0"),),
            program_steps=_two_steps(),
        )


def test_scenario_rejects_duplicate_worlds():
    w = WorldRef("world_a", "1.0")
    with pytest.raises(ValueError, match="duplicate"):
        Scenario(
            scenario_id="s",
            name="s",
            worlds=(w, w),
            program_steps=_two_steps(),
        )


def test_scenario_rejects_neither_program_form():
    with pytest.raises(ValueError, match="exactly one"):
        Scenario(
            scenario_id="s",
            name="s",
            worlds=_two_worlds(),
        )


def test_scenario_rejects_both_program_forms():
    with pytest.raises(ValueError, match="exactly one"):
        Scenario(
            scenario_id="s",
            name="s",
            worlds=_two_worlds(),
            program_id="prog-1",
            program_steps=_two_steps(),
        )


def test_scenario_round_trip_inline_steps():
    s = Scenario(
        scenario_id="s1",
        name="s1",
        description="demo",
        worlds=_two_worlds(),
        program_steps=_two_steps(),
    )
    s2 = Scenario.from_dict(s.to_dict())
    assert s2.scenario_id == s.scenario_id
    assert s2.worlds == s.worlds
    assert s2.program_steps == s.program_steps
    assert s2.program_id is None


def test_scenario_round_trip_program_id():
    s = Scenario(
        scenario_id="s1",
        name="s1",
        worlds=_two_worlds(),
        program_id="prog-abc",
    )
    s2 = Scenario.from_dict(s.to_dict())
    assert s2.program_id == "prog-abc"
    assert s2.program_steps is None


# ---------------------------------------------------------------------------
# StepOutcome / WorldResult / DivergenceReport
# ---------------------------------------------------------------------------


def test_step_outcome_rejects_invalid_enums():
    with pytest.raises(ValueError):
        StepOutcome(
            step_index=0, action="a", stage="bogus",  # type: ignore[arg-type]
            verdict="allow", reason="r", rule_kind="capability",
        )
    with pytest.raises(ValueError):
        StepOutcome(
            step_index=0, action="a", stage="preview",
            verdict="bogus",  # type: ignore[arg-type]
            reason="r", rule_kind="capability",
        )
    with pytest.raises(ValueError):
        StepOutcome(
            step_index=0, action="a", stage="preview",
            verdict="allow", reason="r",
            rule_kind="bogus",  # type: ignore[arg-type]
        )


def test_step_outcome_requires_non_empty_reason():
    with pytest.raises(ValueError, match="non-empty"):
        StepOutcome(
            step_index=0, action="a", stage="preview",
            verdict="allow", reason="   ", rule_kind="capability",
        )


def test_step_outcome_round_trip():
    o = StepOutcome(
        step_index=2, action="normalize_text", stage="replay",
        verdict="deny", reason="world validation failed: ...",
        rule_kind="capability",
    )
    assert StepOutcome.from_dict(o.to_dict()) == o


def test_world_result_round_trip():
    outcomes = (
        StepOutcome(0, "count_words", "replay", "allow", "ok", "execution"),
    )
    wr = WorldResult(
        world_id="world_a", world_version="1.0",
        preview_compatible=True, replay_verdict="allow",
        step_outcomes=outcomes,
    )
    assert wr.key == "world_a@1.0"
    assert WorldResult.from_dict(wr.to_dict()) == wr


def test_divergence_report_round_trip():
    point = ScenarioDivergencePoint(
        step_index=1, action="normalize_text",
        verdicts_by_world={"a@1.0": "allow", "b@1.0": "deny"},
        reasons_by_world={"a@1.0": "ok", "b@1.0": "denied"},
    )
    report = DivergenceReport(
        scenario_id="s",
        divergence_points=(point,),
        all_agree=False,
    )
    assert DivergenceReport.from_dict(report.to_dict()) == report


# ---------------------------------------------------------------------------
# ScenarioResult / scrub / run_id
# ---------------------------------------------------------------------------


def _build_minimal_result(run_id: str, ran_at: str) -> ScenarioResult:
    wr = WorldResult(
        world_id="world_a", world_version="1.0",
        preview_compatible=True, replay_verdict="allow",
        step_outcomes=(
            StepOutcome(0, "count_words", "replay", "allow", "ok", "execution"),
        ),
    )
    return ScenarioResult(
        scenario_id="s",
        program_id="prog-x",
        world_results=(wr,),
        divergence=DivergenceReport(scenario_id="s", divergence_points=(), all_agree=True),
        run_id=run_id,
        ran_at=ran_at,
    )


def test_scenario_result_round_trip():
    r = _build_minimal_result("scn-abc123abc123", "2026-01-01T00:00:00+00:00")
    assert ScenarioResult.from_dict(r.to_dict()) == r


def test_scrub_run_metadata_drops_only_non_deterministic_fields():
    a = _build_minimal_result("scn-aaa", "2026-01-01T00:00:00+00:00")
    b = _build_minimal_result("scn-bbb", "2026-02-01T00:00:00+00:00")
    # Different run_id / ran_at — but the rest is identical.
    assert a.scrub_run_metadata() == b.scrub_run_metadata()
    # And the scrub must drop exactly those two keys.
    scrubbed = a.scrub_run_metadata()
    assert "run_id" not in scrubbed
    assert "ran_at" not in scrubbed
    for k in ("scenario_id", "program_id", "world_results", "divergence"):
        assert k in scrubbed


def test_make_scenario_run_id_prefix_and_uniqueness():
    a = make_scenario_run_id()
    b = make_scenario_run_id()
    assert a.startswith("scn-") and b.startswith("scn-")
    assert a != b
