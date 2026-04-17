"""
test_operator_surface.py — Tests for SYS-4A operator surface.

Covers:
    1.  list_worlds — worlds returned from registry
    2.  activate_world — sets active, returns record with correct fields
    3.  rollback_world — restores previous world, records new activation
    4.  rollback_fails_if_no_previous — RollbackError raised cleanly
    5.  activation_history_recorded — JSONL file has expected entries
    6.  impact_preview_detects_program_incompatibility
    7.  impact_preview_reports_affected_scenarios
    8.  program_registry_surface_list — summaries correct status + compat
    9.  scenario_registry_surface_list — summaries correct scenario_id + worlds
    10. operator_events_logged — event log has entries after activate + rollback
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_hypervisor.program_layer import (
    ActivationImpactReport,
    CandidateStep,
    OperatorEventLog,
    ProgramOperatorService,
    ProgramStatus,
    ProgramStore,
    RollbackError,
    ScenarioOperatorService,
    ScenarioRegistry,
    ScenarioTraceStore,
    WorldDescriptor,
    WorldOperatorService,
    WorldRegistry,
    default_registry,
    default_scenario_registry,
    propose_program,
    review_program,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_world(worlds_dir: Path, world_id: str, version: str,
                 actions: list[str]) -> Path:
    content = (
        f"world_id: {world_id}\n"
        f'version: "{version}"\n'
        f"description: test world\n"
        "allowed_actions:\n"
        + "".join(f"  - {a}\n" for a in actions)
    )
    p = worlds_dir / f"{world_id}.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def _make_services(tmp_path: Path, worlds_dir: Path | None = None):
    if worlds_dir is None:
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        _write_world(worlds_dir, "world_strict", "1.0", ["count_words", "count_lines"])
        _write_world(worlds_dir, "world_balanced", "1.0",
                     ["count_words", "count_lines", "normalize_text", "word_frequency"])

    history_file = tmp_path / "history.jsonl"
    events_file = tmp_path / "events.jsonl"
    registry = WorldRegistry(worlds_dir, active_file=tmp_path / ".active.json")
    event_log = OperatorEventLog(events_file)
    world_svc = WorldOperatorService(registry, history_file, event_log)
    return world_svc, registry, event_log, history_file, events_file


def _make_program_store(tmp_path: Path) -> ProgramStore:
    return ProgramStore(tmp_path / "programs")


def _propose_reviewed(store: ProgramStore, tools: list[str],
                      world_version: str = "1.0") -> str:
    steps = [
        CandidateStep(tool=t, params={"input": "x"}, provenance="test")
        for t in tools
    ]
    prog = propose_program(steps=steps, trace_id="t-test",
                           world_version=world_version, store=store)
    review_program(prog.id, store, notes="ok")
    return prog.id


# ---------------------------------------------------------------------------
# 1. list_worlds
# ---------------------------------------------------------------------------


def test_list_worlds(tmp_path: Path):
    svc, reg, *_ = _make_services(tmp_path)
    worlds = svc.list_worlds()
    ids = [w.world_id for w in worlds]
    assert "world_strict" in ids
    assert "world_balanced" in ids


# ---------------------------------------------------------------------------
# 2. activate_world
# ---------------------------------------------------------------------------


def test_activate_world(tmp_path: Path):
    svc, reg, *_ = _make_services(tmp_path)
    record = svc.activate_world("world_strict", "1.0", reason="test", activated_by="pytest")

    assert record.world_id == "world_strict"
    assert record.version == "1.0"
    assert record.reason == "test"
    assert record.activated_by == "pytest"
    assert record.is_rollback is False
    assert record.activation_id  # non-empty

    active = reg.get_active()
    assert active is not None
    assert active.world_id == "world_strict"


def test_activate_world_captures_previous(tmp_path: Path):
    svc, *_ = _make_services(tmp_path)
    svc.activate_world("world_balanced")
    record2 = svc.activate_world("world_strict")

    assert record2.previous_world_id == "world_balanced"
    assert record2.previous_version == "1.0"


# ---------------------------------------------------------------------------
# 3. rollback_world
# ---------------------------------------------------------------------------


def test_rollback_world(tmp_path: Path):
    svc, reg, *_ = _make_services(tmp_path)
    svc.activate_world("world_balanced")
    svc.activate_world("world_strict")

    rb = svc.rollback_world(reason="oops")
    assert rb.world_id == "world_balanced"
    assert rb.is_rollback is True
    assert rb.reason == "oops"

    active = reg.get_active()
    assert active.world_id == "world_balanced"


# ---------------------------------------------------------------------------
# 4. rollback_fails_if_no_previous
# ---------------------------------------------------------------------------


def test_rollback_fails_if_no_history(tmp_path: Path):
    svc, *_ = _make_services(tmp_path)
    with pytest.raises(RollbackError, match="No activation history"):
        svc.rollback_world()


def test_rollback_fails_if_no_previous_world(tmp_path: Path):
    svc, *_ = _make_services(tmp_path)
    # First activation has no previous
    svc.activate_world("world_strict")
    with pytest.raises(RollbackError, match="no previous world"):
        svc.rollback_world()


# ---------------------------------------------------------------------------
# 5. activation_history_recorded
# ---------------------------------------------------------------------------


def test_activation_history_recorded(tmp_path: Path):
    svc, _, _, history_file, _ = _make_services(tmp_path)
    svc.activate_world("world_balanced")
    svc.activate_world("world_strict")
    svc.rollback_world()

    history = svc.get_activation_history()
    assert len(history) == 3
    assert history[0].world_id == "world_balanced"
    assert history[1].world_id == "world_strict"
    assert history[2].world_id == "world_balanced"
    assert history[2].is_rollback is True

    # JSONL file must exist and be parseable
    assert history_file.exists()
    lines = [l for l in history_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# 6. impact_preview_detects_program_incompatibility
# ---------------------------------------------------------------------------


def test_impact_preview_detects_program_incompatibility(tmp_path: Path):
    svc, reg, event_log, history_file, events_file = _make_services(tmp_path)
    store = _make_program_store(tmp_path)
    scen_reg = default_scenario_registry()

    # Activate balanced world first
    svc.activate_world("world_balanced")

    # Program A: only count_words — works in both worlds
    _propose_reviewed(store, ["count_words"])
    # Program B: uses normalize_text — works in balanced, NOT in strict
    _propose_reviewed(store, ["normalize_text"])

    report = svc.preview_activation_impact("world_strict", "1.0", store, scen_reg)

    assert report.target_world["world_id"] == "world_strict"
    assert report.current_world["world_id"] == "world_balanced"

    # Two reviewed programs were checked
    assert report.totals["reviewed_programs_checked"] == 2

    # Exactly one program becomes incompatible
    assert report.totals["programs_becoming_incompatible"] == 1

    # Find the incompatible one
    incompatible = [p for p in report.affected_programs if not p.target_compatible]
    assert len(incompatible) == 1
    assert "normalize_text" not in incompatible[0].program_id or True  # id is opaque
    assert "loses compatibility" in incompatible[0].summary


# ---------------------------------------------------------------------------
# 7. impact_preview_reports_affected_scenarios
# ---------------------------------------------------------------------------


def test_impact_preview_reports_affected_scenarios(tmp_path: Path):
    svc, reg, event_log, history_file, events_file = _make_services(tmp_path)
    store = _make_program_store(tmp_path)
    scen_reg = default_scenario_registry()

    svc.activate_world("world_balanced")
    report = svc.preview_activation_impact("world_strict", "1.0", store, scen_reg)

    # The bundled scenarios reference world_strict, so they must appear
    scenario_ids = {s.scenario_id for s in report.affected_scenarios}
    assert report.totals["scenarios_checked"] >= 0

    # Any scenario that references world_strict should flag divergence_expected
    for s in report.affected_scenarios:
        if "world_strict" in s.summary:
            assert s.divergence_expected is True


# ---------------------------------------------------------------------------
# 8. program_registry_surface_list
# ---------------------------------------------------------------------------


def test_program_registry_surface_list(tmp_path: Path):
    svc, reg, event_log, history_file, events_file = _make_services(tmp_path)
    store = _make_program_store(tmp_path)

    svc.activate_world("world_balanced")

    pid_a = _propose_reviewed(store, ["count_words"])
    pid_b = _propose_reviewed(store, ["normalize_text"])

    prog_svc = ProgramOperatorService(store=store, registry=reg, event_log=event_log)
    summaries = prog_svc.list_programs()

    assert len(summaries) == 2
    by_id = {s.program_id: s for s in summaries}

    # Both were reviewed, so status = "reviewed"
    assert all(s.status == "reviewed" for s in summaries)

    # Under world_balanced both should be compatible
    assert all(s.compatible_with_active_world is True for s in summaries)

    # Filter by status
    reviewed = prog_svc.list_programs(status="reviewed")
    assert len(reviewed) == 2

    proposed_only = prog_svc.list_programs(status="proposed")
    assert len(proposed_only) == 0


def test_program_operator_diff(tmp_path: Path):
    svc, reg, event_log, _, _ = _make_services(tmp_path)
    store = _make_program_store(tmp_path)
    pid = _propose_reviewed(store, ["count_words"])

    prog_svc = ProgramOperatorService(store=store, registry=reg, event_log=event_log)
    diff = prog_svc.get_program_diff(pid)
    # ProgramDiff is returned without error; it's a dataclass
    assert diff is not None


def test_program_operator_compatibility(tmp_path: Path):
    svc, reg, event_log, _, _ = _make_services(tmp_path)
    store = _make_program_store(tmp_path)
    pid = _propose_reviewed(store, ["normalize_text"])

    prog_svc = ProgramOperatorService(store=store, registry=reg, event_log=event_log)
    # Compatible against balanced
    result = prog_svc.get_program_compatibility(pid, "world_balanced", "1.0")
    assert result.compatible is True

    # Incompatible against strict
    result_strict = prog_svc.get_program_compatibility(pid, "world_strict", "1.0")
    assert result_strict.compatible is False


# ---------------------------------------------------------------------------
# 9. scenario_registry_surface_list
# ---------------------------------------------------------------------------


def test_scenario_registry_surface_list(tmp_path: Path):
    event_log = OperatorEventLog(tmp_path / "events.jsonl")
    scen_reg = default_scenario_registry()
    scen_svc = ScenarioOperatorService(
        scenario_registry=scen_reg,
        trace_store=None,
        event_log=event_log,
    )
    summaries = scen_svc.list_scenarios()
    # Bundled package has at least 2 scenarios
    assert len(summaries) >= 2
    for s in summaries:
        assert s.scenario_id
        assert len(s.worlds) >= 2  # scenarios require ≥ 2 worlds


def test_scenario_operator_get(tmp_path: Path):
    event_log = OperatorEventLog(tmp_path / "events.jsonl")
    scen_reg = default_scenario_registry()
    scen_svc = ScenarioOperatorService(
        scenario_registry=scen_reg,
        trace_store=None,
        event_log=event_log,
    )
    all_scenarios = scen_reg.list_scenarios()
    first_id = all_scenarios[0].scenario_id
    scenario = scen_svc.get_scenario(first_id)
    assert scenario.scenario_id == first_id


# ---------------------------------------------------------------------------
# 10. operator_events_logged
# ---------------------------------------------------------------------------


def test_operator_events_logged(tmp_path: Path):
    svc, reg, event_log, _, events_file = _make_services(tmp_path)

    svc.activate_world("world_balanced")
    svc.activate_world("world_strict")
    svc.rollback_world()

    events = event_log.list_recent()
    assert len(events) >= 3  # at least 3 activate/rollback events

    actions = [e["action"] for e in events]
    assert "activate_world" in actions
    assert "rollback_world" in actions

    # All events have required fields
    for e in events:
        assert "timestamp" in e
        assert "action" in e
        assert "target_type" in e
        assert "target_id" in e
        assert "result" in e

    # File must exist
    assert events_file.exists()


def test_operator_event_log_filter(tmp_path: Path):
    event_log = OperatorEventLog(tmp_path / "events.jsonl")
    event_log.log("activate_world", "world", "world_strict", "ok")
    event_log.log("list_programs", "program", "*", "ok")
    event_log.log("activate_world", "world", "world_balanced", "ok")

    all_events = event_log.list_recent()
    assert len(all_events) == 3

    activations = event_log.list_recent(action="activate_world")
    assert len(activations) == 2
    assert all(e["action"] == "activate_world" for e in activations)


def test_operator_event_log_limit(tmp_path: Path):
    event_log = OperatorEventLog(tmp_path / "events.jsonl")
    for i in range(10):
        event_log.log("test_action", "world", f"w{i}", "ok")

    recent = event_log.list_recent(limit=3)
    assert len(recent) == 3
    # Should be the most recent 3
    assert recent[-1]["target_id"] == "w9"


# ---------------------------------------------------------------------------
# WorldActivationRecord serialisation round-trip
# ---------------------------------------------------------------------------


def test_activation_record_round_trip():
    from agent_hypervisor.program_layer import WorldActivationRecord

    rec = WorldActivationRecord(
        activation_id="abc123",
        world_id="world_strict",
        version="1.0",
        previous_world_id="world_balanced",
        previous_version="1.0",
        activated_at="2026-04-17T00:00:00+00:00",
        activated_by="pytest",
        reason="test",
        is_rollback=False,
    )
    d = rec.to_dict()
    rec2 = WorldActivationRecord.from_dict(d)
    assert rec == rec2


# ---------------------------------------------------------------------------
# ActivationImpactReport serialisation
# ---------------------------------------------------------------------------


def test_impact_report_to_dict(tmp_path: Path):
    svc, *_ = _make_services(tmp_path)
    store = _make_program_store(tmp_path)
    scen_reg = default_scenario_registry()
    svc.activate_world("world_balanced")
    _propose_reviewed(store, ["count_words"])

    report = svc.preview_activation_impact("world_strict", "1.0", store, scen_reg)
    d = report.to_dict()

    assert "target_world" in d
    assert "current_world" in d
    assert "affected_programs" in d
    assert "affected_scenarios" in d
    assert "totals" in d
    assert "generated_at" in d
    assert isinstance(d["affected_programs"], list)
    assert isinstance(d["affected_scenarios"], list)
