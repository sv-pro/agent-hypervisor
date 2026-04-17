import pytest
import json
import yaml
from pathlib import Path
from agent_hypervisor.program_layer import (
    WorldRegistry,
    ProgramStore,
    ScenarioRegistry,
    ScenarioTraceStore,
    CandidateStep,
    propose_program,
    ScenarioResult,
)
from agent_hypervisor.operator import (
    WorldOperatorService,
    ProgramOperatorService,
    ScenarioOperatorService,
)

@pytest.fixture
def temp_repo(tmp_path):
    worlds_dir = tmp_path / "worlds"
    programs_dir = tmp_path / "programs"
    scenarios_dir = tmp_path / "scenarios"
    data_dir = tmp_path / "data"
    
    worlds_dir.mkdir()
    programs_dir.mkdir()
    scenarios_dir.mkdir()
    data_dir.mkdir()
    
    # Create some worlds in WorldRegistry format
    w1_data = {
        "world_id": "w1",
        "version": "1.0",
        "description": "v1 world",
        "allowed_actions": ["t1"]
    }
    w2_data = {
        "world_id": "w1",
        "version": "2.0",
        "allowed_actions": ["t1", "t2"]
    }
    w3_data = {
        "world_id": "w1",
        "version": "3.0",
        "allowed_actions": ["t2"]
    }
    
    (worlds_dir / "w1_v1.yaml").write_text(yaml.dump(w1_data))
    (worlds_dir / "w1_v2.yaml").write_text(yaml.dump(w2_data))
    (worlds_dir / "w1_v3.yaml").write_text(yaml.dump(w3_data))
    
    # Create a program that uses t1
    store = ProgramStore(str(programs_dir))
    prog1 = propose_program(
        steps=[CandidateStep(tool="t1", params={})],
        trace_id="t-1",
        world_version="1.0",
        store=store,
        program_id="p1"
    )
    
    # Create a scenario (ScenarioRegistry format)
    scen_data = {
        "scenario_id": "scen1",
        "name": "Scenario 1",
        "program_id": "p1",
        "worlds": [{"world_id": "w1", "version": "1.0"}, {"world_id": "w1", "version": "2.0"}]
    }
    (scenarios_dir / "scen1.yaml").write_text(yaml.dump(scen_data))
    
    return {
        "worlds_dir": worlds_dir,
        "programs_dir": programs_dir,
        "scenarios_dir": scenarios_dir,
        "data_dir": data_dir,
        "world_reg": WorldRegistry(str(worlds_dir)),
        "prog_store": store,
        "scen_reg": ScenarioRegistry(str(scenarios_dir)),
        "trace_file": data_dir / "scenario_traces.jsonl",
        "activation_log": data_dir / "world_activation_history.jsonl",
        "event_log": data_dir / "operator_events.jsonl",
    }

def test_world_activation_log(temp_repo):
    svc = WorldOperatorService(
        temp_repo["world_reg"],
        temp_repo["activation_log"],
        temp_repo["event_log"]
    )
    
    # Initial state
    assert svc.get_active_world() is None
    
    # Activate w1@1.0
    record = svc.activate_world("w1", "1.0", reason="Initial", activated_by="op1")
    assert record.world_id == "w1"
    assert record.version == "1.0"
    assert record.previous_world_id is None
    
    active = svc.get_active_world()
    assert active["world_id"] == "w1"
    assert active["version"] == "1.0"
    
    # Check logs
    history = svc.get_activation_history()
    assert len(history) == 1
    assert history[0]["world_id"] == "w1"
    assert history[0]["reason"] == "Initial"
    assert history[0]["activated_by"] == "op1"

def test_rollback(temp_repo):
    svc = WorldOperatorService(
        temp_repo["world_reg"],
        temp_repo["activation_log"],
        temp_repo["event_log"]
    )
    
    # Activate 1.0 then 2.0
    svc.activate_world("w1", "1.0")
    svc.activate_world("w1", "2.0")
    
    assert svc.get_active_world()["version"] == "2.0"
    
    # Rollback
    record = svc.rollback_world(reason="mistake")
    assert record.world_id == "w1"
    assert record.version == "1.0"
    assert record.previous_world_id == "w1"
    assert record.previous_version == "2.0"
    
    assert svc.get_active_world()["version"] == "1.0"
    
    # Rollback again should fail because 1.0 didn't have a previous world when it was first activated
    # Wait, when we activated 1.0 (it was first), prev was None.
    # Then we activated 2.0, prev was 1.0.
    # Then we rolled back to 1.0, and set prev to 2.0.
    
    record2 = svc.rollback_world()
    assert record2.version == "2.0"
    
    # What if we clear active?
    temp_repo["world_reg"].clear_active()
    with pytest.raises(ValueError, match="No previous world info available"):
        svc.rollback_world()

def test_reactivate_same_world(temp_repo):
    svc = WorldOperatorService(
        temp_repo["world_reg"],
        temp_repo["activation_log"],
        temp_repo["event_log"]
    )
    
    svc.activate_world("w1", "1.0")
    # Activate same world again
    record = svc.activate_world("w1", "1.0")
    assert record.previous_world_id == "w1"
    assert record.previous_version == "1.0"

def test_impact_preview(temp_repo):
    svc = WorldOperatorService(
        temp_repo["world_reg"],
        temp_repo["activation_log"],
        temp_repo["event_log"]
    )
    
    # Currently None active.
    # Preview w1@1.0
    report = svc.preview_activation_impact("w1", "1.0", temp_repo["prog_store"], temp_repo["scen_reg"])
    assert report.totals["reviewed_programs_checked"] == 1
    # p1 uses t1, w1@1.0 has t1. Impact should be changed_behavior
    assert len(report.affected_programs) == 1
    assert report.affected_programs[0]["program_id"] == "p1"
    assert report.affected_programs[0]["impact"] == "changed_behavior"
    
    # Activate w1@1.0
    svc.activate_world("w1", "1.0")
    
    # Preview w1@3.0 (which drops t1)
    report2 = svc.preview_activation_impact("w1", "3.0", temp_repo["prog_store"], temp_repo["scen_reg"])
    assert report2.affected_programs[0]["impact"] == "incompatible"
    assert report2.totals["programs_becoming_incompatible"] == 1
    
    # Scenarios: scen1 uses p1 and binds to 1.0 and 2.0.
    assert len(report2.affected_scenarios) == 1
    assert report2.affected_scenarios[0]["scenario_id"] == "scen1"
    assert report2.affected_scenarios[0]["impact"] == "incompatible"

def test_program_summary(temp_repo):
    svc = ProgramOperatorService(temp_repo["prog_store"], temp_repo["world_reg"], temp_repo["event_log"])
    
    # No active world
    sums = svc.list_programs()
    assert len(sums) == 1
    assert sums[0].compatible_with_active_world is False
    
    # Activate compat world
    WorldOperatorService(temp_repo["world_reg"], temp_repo["activation_log"], temp_repo["event_log"]).activate_world("w1", "1.0")
    
    sums = svc.list_programs()
    assert sums[0].compatible_with_active_world is True
    assert sums[0].compatibility_checked_against["world_id"] == "w1"

def test_scenario_summary(temp_repo):
    trace_store = ScenarioTraceStore(temp_repo["trace_file"])
    svc = ScenarioOperatorService(temp_repo["scen_reg"], trace_store, temp_repo["world_reg"], temp_repo["event_log"])
    
    sums = svc.list_scenarios()
    assert len(sums) == 1
    assert sums[0].last_run_at is None
    
    # Simulate a run
    trace_store.append(ScenarioResult.from_dict({
        "scenario_id": "scen1",
        "program_id": "p1",
        "run_id": "r1",
        "ran_at": "2024-01-01T00:00:00Z",
        "divergence": {"scenario_id": "scen1", "all_agree": False, "divergence_points": []},
        "world_results": []
    }))
    
    sums = svc.list_scenarios()
    assert sums[0].last_run_at == "2024-01-01T00:00:00Z"
    assert sums[0].last_diverged is True

def test_event_logging(temp_repo):
    svc = WorldOperatorService(
        temp_repo["world_reg"],
        temp_repo["activation_log"],
        temp_repo["event_log"]
    )
    svc.activate_world("w1", "1.0")
    
    event_logger = svc.event_logger
    events = event_logger.read_all()
    assert len(events) >= 1
    assert events[0]["action"] == "activate_world"
    assert events[0]["target_object"] == "w1@1.0"
    assert events[0].get("timestamp") is not None
