"""
test_scenario_runner.py — SYS-3 orchestration invariants.

Covers the five acceptance invariants from the spec:

    1. Same program runs under two worlds and produces opposite verdicts.
    2. ``detect_divergence`` flags only the diverging step index.
    3. ``denied_at_preview`` skips the ReplayEngine entirely
       (verified with a spy engine that records every call).
    4. Every StepOutcome has a non-empty ``reason`` and a valid ``rule_kind``.
    5. Running the same scenario twice on identical inputs produces identical
       ``ScenarioResult`` data after scrubbing ``run_id`` / ``ran_at``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import pytest

from agent_hypervisor.program_layer import (
    ProgramStore,
    ReplayEngine,
    Scenario,
    WorldRef,
    WorldRegistry,
    detect_divergence,
    run_scenario,
)
from agent_hypervisor.program_layer.review_models import CandidateStep
from agent_hypervisor.program_layer.replay_engine import ReplayTrace


BUNDLED_WORLDS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "agent_hypervisor" / "program_layer" / "worlds"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> WorldRegistry:
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    for yaml in BUNDLED_WORLDS_DIR.glob("*.yaml"):
        shutil.copy(yaml, worlds_dir / yaml.name)
    return WorldRegistry(
        worlds_dir=worlds_dir,
        active_file=tmp_path / "active.json",
    )


@pytest.fixture
def store(tmp_path: Path) -> ProgramStore:
    return ProgramStore(tmp_path / "programs")


@pytest.fixture
def memory_write_scenario() -> Scenario:
    return Scenario(
        scenario_id="memory_write_test",
        name="memory write",
        description="count then normalize",
        worlds=(
            WorldRef("world_strict", "1.0"),
            WorldRef("world_balanced", "1.0"),
        ),
        program_steps=(
            CandidateStep(tool="count_words", params={"input": "alpha beta"}),
            CandidateStep(tool="normalize_text", params={"input": "HELLO"}),
        ),
    )


# ---------------------------------------------------------------------------
# Spy ReplayEngine — records every replay_under_world call.
# ---------------------------------------------------------------------------


class _SpyReplayEngine(ReplayEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def replay_under_world(self, program, world=None, world_source="explicit",
                          preview_compatible=None, runner=None,
                          context=None) -> ReplayTrace:
        self.calls.append(
            {
                "program_id": program.id,
                "world_id": world.world_id if world is not None else None,
                "world_version": world.version if world is not None else None,
                "preview_compatible": preview_compatible,
            }
        )
        return super().replay_under_world(
            program=program,
            world=world,
            world_source=world_source,
            preview_compatible=preview_compatible,
            runner=runner,
            context=context,
        )


# ---------------------------------------------------------------------------
# Invariant 1 — same program, two worlds, opposite verdicts.
# ---------------------------------------------------------------------------


def test_same_program_two_worlds_produce_opposite_verdicts(
    registry, memory_write_scenario
):
    result = run_scenario(memory_write_scenario, registry=registry)

    assert len(result.world_results) == 2
    by_key = {wr.key: wr for wr in result.world_results}

    strict = by_key["world_strict@1.0"]
    balanced = by_key["world_balanced@1.0"]

    assert strict.preview_compatible is False
    assert strict.replay_verdict == "denied_at_preview"
    # normalize_text must be the denied step under strict.
    strict_by_idx = {o.step_index: o for o in strict.step_outcomes}
    assert strict_by_idx[1].verdict == "deny"
    assert strict_by_idx[1].action == "normalize_text"

    assert balanced.preview_compatible is True
    assert balanced.replay_verdict == "allow"
    assert all(o.verdict == "allow" for o in balanced.step_outcomes)


# ---------------------------------------------------------------------------
# Invariant 2 — detect_divergence flags only the diverging step index.
# ---------------------------------------------------------------------------


def test_detect_divergence_flags_only_diverging_step(
    registry, memory_write_scenario
):
    result = run_scenario(memory_write_scenario, registry=registry)
    report = result.divergence

    assert report.all_agree is False
    # Only step[1] (normalize_text) must diverge — step[0] was allowed by both.
    assert [p.step_index for p in report.divergence_points] == [1]
    point = report.divergence_points[0]
    assert point.action == "normalize_text"
    assert set(point.verdicts_by_world.keys()) == {
        "world_strict@1.0", "world_balanced@1.0",
    }
    assert point.verdicts_by_world["world_strict@1.0"] == "deny"
    assert point.verdicts_by_world["world_balanced@1.0"] == "allow"
    # Reasons are populated.
    for reason in point.reasons_by_world.values():
        assert reason.strip() != ""


def test_detect_divergence_returns_all_agree_for_empty_input():
    report = detect_divergence("scn-1", [])
    assert report.all_agree is True
    assert report.divergence_points == ()


# ---------------------------------------------------------------------------
# Invariant 3 — denied_at_preview must NOT invoke the ReplayEngine.
# ---------------------------------------------------------------------------


def test_denied_at_preview_skips_replay_engine(registry):
    """Scenario where BOTH worlds deny preview — replay must never be called."""
    scenario = Scenario(
        scenario_id="never_replay",
        name="never replay",
        worlds=(
            WorldRef("world_strict", "1.0"),
            # world_strict again isn't legal (duplicate).  Instead use the
            # balanced world but drive it through a step the balanced world
            # does NOT allow — none exists, so craft two distinct strict
            # references by exploiting the fact that two different copies of
            # world_strict with different versions would be distinct.  Simpler:
            # use the balanced world but put a step neither allows.  Neither
            # world allows "save_memory_external", so both worlds preview-deny.
            WorldRef("world_balanced", "1.0"),
        ),
        program_steps=(
            CandidateStep(tool="save_memory_external", params={}),
        ),
    )
    spy = _SpyReplayEngine()

    result = run_scenario(scenario, registry=registry, replay_engine=spy)

    # Neither world should have reached the replay engine.
    assert spy.calls == []
    for wr in result.world_results:
        assert wr.preview_compatible is False
        assert wr.replay_verdict == "denied_at_preview"
        # The single step is denied at preview on both worlds.
        assert wr.step_outcomes[0].verdict == "deny"
        assert wr.step_outcomes[0].stage == "preview"
        assert wr.step_outcomes[0].rule_kind == "capability"


def test_spy_engine_called_only_for_compatible_worlds(
    registry, memory_write_scenario
):
    """The spy should see exactly one call — only the balanced world replays."""
    spy = _SpyReplayEngine()
    run_scenario(memory_write_scenario, registry=registry, replay_engine=spy)

    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["world_id"] == "world_balanced"
    assert call["preview_compatible"] is True


# ---------------------------------------------------------------------------
# Invariant 4 — every StepOutcome carries a non-empty reason and a valid
# rule_kind ∈ {capability, schema, taint, policy, execution}.
# ---------------------------------------------------------------------------


_VALID_KINDS = {"capability", "schema", "taint", "policy", "execution"}


def test_every_step_outcome_has_reason_and_valid_rule_kind(
    registry, memory_write_scenario
):
    result = run_scenario(memory_write_scenario, registry=registry)

    seen = 0
    for wr in result.world_results:
        for o in wr.step_outcomes:
            assert o.reason.strip() != ""
            assert o.rule_kind in _VALID_KINDS
            assert o.verdict in {"allow", "deny", "skip"}
            seen += 1
    assert seen > 0


# ---------------------------------------------------------------------------
# Invariant 5 — stability across runs on identical inputs.
# ---------------------------------------------------------------------------


def test_scenario_result_stable_across_repeated_runs(
    registry, memory_write_scenario
):
    a = run_scenario(memory_write_scenario, registry=registry)
    b = run_scenario(memory_write_scenario, registry=registry)

    assert a.run_id != b.run_id  # non-deterministic by design
    assert a.scrub_run_metadata() == b.scrub_run_metadata()


# ---------------------------------------------------------------------------
# Program resolution: program_id path requires a store.
# ---------------------------------------------------------------------------


def test_scenario_with_program_id_requires_store(registry):
    scenario = Scenario(
        scenario_id="needs_store",
        name="needs store",
        worlds=(
            WorldRef("world_strict", "1.0"),
            WorldRef("world_balanced", "1.0"),
        ),
        program_id="prog-absent",
    )
    with pytest.raises(ValueError, match="no ProgramStore"):
        run_scenario(scenario, registry=registry, store=None)


def test_scenario_with_unknown_program_id_raises(registry, store):
    scenario = Scenario(
        scenario_id="unknown_prog",
        name="unknown prog",
        worlds=(
            WorldRef("world_strict", "1.0"),
            WorldRef("world_balanced", "1.0"),
        ),
        program_id="prog-does-not-exist",
    )
    with pytest.raises(KeyError):
        run_scenario(scenario, registry=registry, store=store)
