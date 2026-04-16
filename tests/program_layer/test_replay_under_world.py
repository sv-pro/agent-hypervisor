"""
test_replay_under_world.py — ReplayEngine.replay_under_world + ReplayTrace.

Covers:
    - Replay under a compatible world yields final_verdict='allow' and the
      trace records world_id, world_version, world_source='explicit'.
    - Replay under an incompatible world yields final_verdict='deny',
      ProgramTrace.ok is False, and the failing step's error mentions
      "world validation failed".
    - Replay without a world falls back to SUPPORTED_WORKFLOWS and records
      world_source='default' + world_id='default'.
    - preview_compatible annotation is stored verbatim on the trace.
    - final_verdict classification: allow / deny / partial_failure.
    - ReplayTrace.to_dict() is JSON-safe and stable.
    - ReplayEngine.replay() (the legacy method) is untouched: returns a bare
      ProgramTrace and is unaffected by the SYS-2 additions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_hypervisor.program_layer import (
    CandidateStep,
    ProgramStore,
    ProgramTrace,
    ReplayEngine,
    ReplayTrace,
    WorldDescriptor,
    accept_program,
    check_compatibility,
    minimize_program,
    propose_program,
    review_program,
)
from agent_hypervisor.program_layer.program_trace import StepTrace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ProgramStore:
    return ProgramStore(tmp_path / "programs")


@pytest.fixture
def world_strict() -> WorldDescriptor:
    return WorldDescriptor(
        world_id="world_strict",
        version="1.0",
        allowed_actions=frozenset({"count_words", "count_lines"}),
    )


@pytest.fixture
def world_balanced() -> WorldDescriptor:
    return WorldDescriptor(
        world_id="world_balanced",
        version="1.0",
        allowed_actions=frozenset(
            {"count_words", "count_lines", "normalize_text", "word_frequency"}
        ),
    )


def _accept_program(store: ProgramStore, steps: list[CandidateStep]) -> str:
    """Propose → minimize → review → accept, return program id."""
    prog = propose_program(
        steps=steps,
        trace_id="trace-1",
        world_version="1.0",
        store=store,
    )
    minimize_program(prog.id, store)
    review_program(prog.id, store)
    accept_program(
        prog.id,
        store,
        allowed_actions={"count_words", "count_lines", "normalize_text", "word_frequency"},
    )
    return prog.id


# ---------------------------------------------------------------------------
# Replay under a compatible world
# ---------------------------------------------------------------------------


def test_replay_under_compatible_world_allows(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "a b c"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world_balanced)
    assert isinstance(trace, ReplayTrace)
    assert trace.world_id == "world_balanced"
    assert trace.world_version == "1.0"
    assert trace.world_source == "explicit"
    assert trace.final_verdict == "allow"
    assert trace.program_trace.ok is True
    assert all(st.allowed for st in trace.program_trace.step_traces)


# ---------------------------------------------------------------------------
# Replay under an incompatible world
# ---------------------------------------------------------------------------


def test_replay_under_incompatible_world_denies_before_execution(
    store: ProgramStore, world_strict: WorldDescriptor
):
    # normalize_text is absent from world_strict
    pid = _accept_program(
        store, [CandidateStep(tool="normalize_text", params={"input": "HELLO"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world_strict)
    assert trace.world_id == "world_strict"
    assert trace.final_verdict == "deny"
    assert trace.program_trace.ok is False
    assert trace.program_trace.step_traces[0].denied
    assert "world validation failed" in (
        trace.program_trace.step_traces[0].error or ""
    )


def test_replay_under_incompatible_world_does_not_execute_later_steps(
    store: ProgramStore, world_strict: WorldDescriptor
):
    pid = _accept_program(
        store,
        [
            CandidateStep(tool="normalize_text", params={"input": "HI"}),  # denied
            CandidateStep(tool="count_words", params={"input": "a b"}),   # would be ok
        ],
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world_strict)
    # Pre-execution validation rejects the whole program — second step never runs.
    assert trace.final_verdict == "deny"
    # No 'allow' step trace should exist
    assert not any(st.allowed for st in trace.program_trace.step_traces)


# ---------------------------------------------------------------------------
# No-world (default) fallback
# ---------------------------------------------------------------------------


def test_replay_without_world_uses_default_set(store: ProgramStore):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "hi"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world=None)
    assert trace.world_source == "default"
    assert trace.world_id == "default"
    assert trace.world_version == "unspecified"
    assert trace.final_verdict == "allow"


def test_replay_under_world_rejects_non_descriptor(store: ProgramStore):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={})]
    )
    prog = store.load(pid)
    with pytest.raises(TypeError):
        ReplayEngine().replay_under_world(prog, world="not_a_descriptor")  # type: ignore


# ---------------------------------------------------------------------------
# Preview-compatible annotation
# ---------------------------------------------------------------------------


def test_preview_flag_is_recorded_on_replay_trace(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "hi"})]
    )
    prog = store.load(pid)
    preview = check_compatibility(prog, world_balanced)
    trace = ReplayEngine().replay_under_world(
        prog, world_balanced, preview_compatible=preview.compatible
    )
    assert trace.preview_compatible is True


def test_preview_flag_defaults_to_none(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "hi"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world_balanced)
    assert trace.preview_compatible is None


# ---------------------------------------------------------------------------
# world_source: active vs explicit
# ---------------------------------------------------------------------------


def test_world_source_is_propagated(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={})]
    )
    prog = store.load(pid)
    t_explicit = ReplayEngine().replay_under_world(
        prog, world_balanced, world_source="explicit"
    )
    t_active = ReplayEngine().replay_under_world(
        prog, world_balanced, world_source="active"
    )
    assert t_explicit.world_source == "explicit"
    assert t_active.world_source == "active"


# ---------------------------------------------------------------------------
# final_verdict classification helper
# ---------------------------------------------------------------------------


def _manual_verdict(steps_data):
    """Synthesize a ProgramTrace with arbitrary step outcomes for classifier testing."""
    pt = ProgramTrace(program_id="prog-x")
    pt.step_traces = [
        StepTrace(
            step_index=i, action=s["action"], verdict=s["verdict"],
            result=None, error=s.get("error"), duration_seconds=0.0,
        )
        for i, s in enumerate(steps_data)
    ]
    pt.ok = all(s["verdict"] == "allow" for s in steps_data)
    if not pt.ok:
        pt.aborted_at_step = next(
            (i for i, s in enumerate(steps_data) if s["verdict"] == "deny"), None
        )
    return pt


def test_classify_verdict_allow():
    from agent_hypervisor.program_layer.replay_engine import _classify_verdict

    t = _manual_verdict([{"action": "a", "verdict": "allow"}])
    assert _classify_verdict(t) == "allow"


def test_classify_verdict_deny_when_first_step_denied():
    from agent_hypervisor.program_layer.replay_engine import _classify_verdict

    t = _manual_verdict(
        [
            {"action": "a", "verdict": "deny", "error": "x"},
            {"action": "b", "verdict": "skip"},
        ]
    )
    assert _classify_verdict(t) == "deny"


def test_classify_verdict_partial_failure():
    from agent_hypervisor.program_layer.replay_engine import _classify_verdict

    t = _manual_verdict(
        [
            {"action": "a", "verdict": "allow"},
            {"action": "b", "verdict": "deny", "error": "x"},
        ]
    )
    assert _classify_verdict(t) == "partial_failure"


def test_classify_verdict_empty_trace_is_deny():
    from agent_hypervisor.program_layer.replay_engine import _classify_verdict

    t = ProgramTrace(program_id="prog-empty")
    t.ok = False
    assert _classify_verdict(t) == "deny"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_replay_trace_to_dict_is_json_safe(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "hi"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay_under_world(prog, world_balanced)
    data = trace.to_dict()
    # All SYS-2 fields must be present
    for k in (
        "replay_id", "program_id", "world_id", "world_version",
        "world_source", "preview_compatible", "final_verdict",
        "replayed_at", "program_trace",
    ):
        assert k in data
    json.dumps(data, default=str)  # must not raise


# ---------------------------------------------------------------------------
# Legacy replay() is still a plain ProgramTrace (non-breaking)
# ---------------------------------------------------------------------------


def test_legacy_replay_is_untouched(
    store: ProgramStore, world_balanced: WorldDescriptor
):
    pid = _accept_program(
        store, [CandidateStep(tool="count_words", params={"input": "hi"})]
    )
    prog = store.load(pid)
    trace = ReplayEngine().replay(prog)
    assert isinstance(trace, ProgramTrace)
    # The new wrapper type must not leak into the legacy method.
    assert not isinstance(trace, ReplayTrace)
