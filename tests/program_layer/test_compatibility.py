"""
test_compatibility.py — Compatibility / preview / cross-world diff tests.

Covers:
    - check_compatibility: fully allowed, fully denied, mixed
    - preview_program_under_world: happy path, unknown program, unknown world
    - compare_program_across_worlds: identical verdicts, real divergence,
      divergence_points carry the denying world's reason
    - Empty minimized_steps is compatible under any world
    - Compatibility summary counts match step_results
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_hypervisor.program_layer import (
    CandidateStep,
    ProgramStore,
    WorldDescriptor,
    WorldRegistry,
    check_compatibility,
    compare_program_across_worlds,
    preview_program_under_world,
    propose_program,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def world_strict() -> WorldDescriptor:
    return WorldDescriptor(
        world_id="world_strict",
        version="1.0",
        allowed_actions=frozenset({"count_words", "count_lines"}),
        description="strict",
    )


@pytest.fixture
def world_balanced() -> WorldDescriptor:
    return WorldDescriptor(
        world_id="world_balanced",
        version="1.0",
        allowed_actions=frozenset(
            {"count_words", "count_lines", "normalize_text", "word_frequency"}
        ),
        description="balanced",
    )


@pytest.fixture
def store(tmp_path: Path) -> ProgramStore:
    return ProgramStore(tmp_path / "programs")


def _propose(store: ProgramStore, steps: list[CandidateStep]) -> str:
    return propose_program(
        steps=steps,
        trace_id="trace-1",
        world_version="1.0",
        store=store,
    ).id


# ---------------------------------------------------------------------------
# Per-program-world registry setup
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_with_both(tmp_path: Path) -> WorldRegistry:
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()
    (worlds_dir / "world_strict.yaml").write_text(
        "world_id: world_strict\n"
        "version: \"1.0\"\n"
        "allowed_actions: [count_words, count_lines]\n",
        encoding="utf-8",
    )
    (worlds_dir / "world_balanced.yaml").write_text(
        "world_id: world_balanced\n"
        "version: \"1.0\"\n"
        "allowed_actions: [count_words, count_lines, normalize_text, word_frequency]\n",
        encoding="utf-8",
    )
    return WorldRegistry(worlds_dir)


# ---------------------------------------------------------------------------
# check_compatibility — basic verdicts
# ---------------------------------------------------------------------------


def test_fully_compatible_program(store: ProgramStore, world_strict: WorldDescriptor):
    pid = _propose(store, [CandidateStep(tool="count_words", params={"input": "hi"})])
    prog = store.load(pid)
    verdict = check_compatibility(prog, world_strict)
    assert verdict.compatible
    assert verdict.summary.allowed_steps == 1
    assert verdict.summary.denied_steps == 0
    assert verdict.summary.restricted_actions == ()


def test_fully_incompatible_program(store: ProgramStore, world_strict: WorldDescriptor):
    pid = _propose(
        store,
        [
            CandidateStep(tool="normalize_text", params={"input": "HELLO"}),
            CandidateStep(tool="word_frequency", params={"input": "a b a"}),
        ],
    )
    prog = store.load(pid)
    verdict = check_compatibility(prog, world_strict)
    assert not verdict.compatible
    assert verdict.summary.denied_steps == 2
    assert verdict.summary.allowed_steps == 0
    assert set(verdict.summary.restricted_actions) == {"normalize_text", "word_frequency"}
    for sr in verdict.step_results:
        assert not sr.allowed
        assert sr.missing_capability == sr.action


def test_mixed_compatibility(store: ProgramStore, world_strict: WorldDescriptor):
    pid = _propose(
        store,
        [
            CandidateStep(tool="count_words", params={"input": "hi"}),
            CandidateStep(tool="normalize_text", params={"input": "HELLO"}),
            CandidateStep(tool="count_lines", params={"input": "a\nb"}),
        ],
    )
    prog = store.load(pid)
    verdict = check_compatibility(prog, world_strict)
    assert not verdict.compatible
    assert verdict.summary.allowed_steps == 2
    assert verdict.summary.denied_steps == 1
    assert verdict.summary.restricted_actions == ("normalize_text",)
    assert [sr.allowed for sr in verdict.step_results] == [True, False, True]


def test_empty_minimized_steps_is_compatible(
    store: ProgramStore, world_strict: WorldDescriptor
):
    # A program whose minimizer reduced everything away is still valid.
    # Propose a 1-step program, then synthesize an "empty minimized_steps"
    # ReviewedProgram by serializing/overriding via from_dict.
    import dataclasses

    pid = _propose(store, [CandidateStep(tool="count_words", params={"input": "hi"})])
    prog = store.load(pid)
    empty = dataclasses.replace(prog, minimized_steps=())
    store.save(empty)
    verdict = check_compatibility(store.load(pid), world_strict)
    assert verdict.compatible
    assert verdict.step_results == ()
    assert verdict.summary.allowed_steps == 0
    assert verdict.summary.denied_steps == 0


def test_check_compatibility_rejects_wrong_types(
    store: ProgramStore, world_strict: WorldDescriptor
):
    with pytest.raises(TypeError):
        check_compatibility("not a program", world_strict)  # type: ignore
    pid = _propose(store, [CandidateStep(tool="count_words", params={"input": "hi"})])
    prog = store.load(pid)
    with pytest.raises(TypeError):
        check_compatibility(prog, {"allowed_actions": {"count_words"}})  # type: ignore


def test_compatibility_to_dict_is_json_safe(
    store: ProgramStore, world_strict: WorldDescriptor
):
    import json

    pid = _propose(
        store,
        [
            CandidateStep(tool="count_words", params={}),
            CandidateStep(tool="normalize_text", params={}),
        ],
    )
    prog = store.load(pid)
    verdict = check_compatibility(prog, world_strict)
    json.dumps(verdict.to_dict())  # must not raise


def test_preview_same_result_as_check(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    """preview_program_under_world is just a store+registry-aware wrapper."""
    pid = _propose(
        store,
        [
            CandidateStep(tool="count_words", params={}),
            CandidateStep(tool="normalize_text", params={}),
        ],
    )
    strict = registry_with_both.get("world_strict", "1.0")
    from_direct = check_compatibility(store.load(pid), strict)
    from_preview = preview_program_under_world(
        program_id=pid,
        world_id="world_strict",
        version="1.0",
        store=store,
        registry=registry_with_both,
    )
    assert from_direct == from_preview


def test_preview_unknown_program_raises(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    with pytest.raises(KeyError):
        preview_program_under_world(
            program_id="prog-doesnotexist",
            world_id="world_strict",
            version="1.0",
            store=store,
            registry=registry_with_both,
        )


def test_preview_unknown_world_raises(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    from agent_hypervisor.program_layer import WorldNotFoundError

    pid = _propose(store, [CandidateStep(tool="count_words", params={})])
    with pytest.raises(WorldNotFoundError):
        preview_program_under_world(
            program_id=pid,
            world_id="world_nonexistent",
            version=None,
            store=store,
            registry=registry_with_both,
        )


# ---------------------------------------------------------------------------
# compare_program_across_worlds
# ---------------------------------------------------------------------------


def test_compare_finds_divergence_strict_vs_balanced(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    pid = _propose(
        store,
        [
            CandidateStep(tool="count_words", params={"input": "a b c"}),
            CandidateStep(tool="normalize_text", params={"input": "HELLO"}),
        ],
    )
    diff = compare_program_across_worlds(
        program_id=pid,
        world_a_id="world_strict",
        world_a_version="1.0",
        world_b_id="world_balanced",
        world_b_version="1.0",
        store=store,
        registry=registry_with_both,
    )
    assert not diff.both_compatible  # strict denies normalize_text
    assert len(diff.divergence_points) == 1
    point = diff.divergence_points[0]
    assert point.step_index == 1
    assert point.action == "normalize_text"
    assert point.world_a.startswith("denied")
    assert point.world_b == "allowed"


def test_compare_same_world_reports_no_divergence(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    pid = _propose(
        store,
        [
            CandidateStep(tool="count_words", params={}),
            CandidateStep(tool="normalize_text", params={}),
        ],
    )
    diff = compare_program_across_worlds(
        program_id=pid,
        world_a_id="world_balanced",
        world_a_version="1.0",
        world_b_id="world_balanced",
        world_b_version="1.0",
        store=store,
        registry=registry_with_both,
    )
    assert diff.divergence_points == ()
    assert diff.both_compatible


def test_compare_both_incompatible_no_divergence(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    pid = _propose(
        store,
        [CandidateStep(tool="normalize_text", params={})],  # denied by strict
    )
    # Swap balanced for a second strict world so BOTH deny
    worlds_dir = registry_with_both.worlds_dir
    (worlds_dir / "world_strict_2.yaml").write_text(
        "world_id: world_strict_2\n"
        "version: \"1.0\"\n"
        "allowed_actions: [count_words, count_lines]\n",
        encoding="utf-8",
    )
    diff = compare_program_across_worlds(
        program_id=pid,
        world_a_id="world_strict",
        world_a_version="1.0",
        world_b_id="world_strict_2",
        world_b_version="1.0",
        store=store,
        registry=registry_with_both,
    )
    assert diff.divergence_points == ()
    assert not diff.both_compatible


def test_compare_diff_to_dict_is_json_safe(
    store: ProgramStore, registry_with_both: WorldRegistry
):
    import json

    pid = _propose(
        store, [CandidateStep(tool="normalize_text", params={})]
    )
    diff = compare_program_across_worlds(
        program_id=pid,
        world_a_id="world_strict",
        world_a_version="1.0",
        world_b_id="world_balanced",
        world_b_version="1.0",
        store=store,
        registry=registry_with_both,
    )
    json.dumps(diff.to_dict())  # must not raise
