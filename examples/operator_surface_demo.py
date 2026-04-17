"""
operator_surface_demo.py — Bundled demo for SYS-4A: Operator Surface Foundation.

This demo illustrates the lifecycle management of worlds and artifacts,
showing how an operator can preview and execute world transitions safely.
"""

import json
import os
import shutil
import tempfile
import yaml
from pathlib import Path
from datetime import datetime, timezone

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

# ── styling ──────────────────────────────────────────────────────────────────

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"

def print_header(text):
    print(f"\n{_BOLD}{_CYAN}== {text} =={_RESET}")

def print_step(n, text):
    print(f"\n{_BOLD}[{n}] {text}{_RESET}")

def print_json(data):
    print(_DIM + json.dumps(data, indent=2) + _RESET)

# ── setup ────────────────────────────────────────────────────────────────────

def setup_demo_env():
    tmp = Path(tempfile.mkdtemp(prefix="ah_operator_demo_"))
    worlds_dir = tmp / "worlds"
    programs_dir = tmp / "programs"
    scenarios_dir = tmp / "scenarios"
    data_dir = tmp / "data"
    
    worlds_dir.mkdir()
    programs_dir.mkdir()
    scenarios_dir.mkdir()
    data_dir.mkdir()
    
    # 1. Provide Worlds
    # World A: Basic (v1) - permits file_read
    w_basic_v1 = {
        "world_id": "world_basic",
        "version": "1.0",
        "description": "Basic measurement world (v1)",
        "allowed_actions": ["file_read"]
    }
    # World A: Premium (v2) - permits file_read, shell_exec
    w_basic_v2 = {
        "world_id": "world_basic",
        "version": "2.0",
        "description": "Premium world (v2) - security boundary expanded",
        "allowed_actions": ["file_read", "shell_exec"]
    }
    # World B: Strict (v1) - permits NOTHING
    w_strict = {
        "world_id": "world_strict",
        "version": "1.0",
        "description": "Strict lockdown world",
        "allowed_actions": []
    }
    
    for w in [w_basic_v1, w_basic_v2, w_strict]:
        path = worlds_dir / f"{w['world_id']}_{w['version']}.yaml"
        path.write_text(yaml.dump(w))
        
    # 2. Provide Programs
    store = ProgramStore(str(programs_dir))
    # Program 1: only reads (compatible with basic 1.0)
    propose_program(
        steps=[CandidateStep(tool="file_read", params={"path": "/etc/motd"})],
        trace_id="tr-001",
        world_version="1.0",
        store=store,
        program_id="read_motd"
    )
    # Program 2: needs shell_exec (incompatible with basic 1.0, compat with 2.0)
    propose_program(
        steps=[CandidateStep(tool="shell_exec", params={"command": "ls"})],
        trace_id="tr-002",
        world_version="2.0",
        store=store,
        program_id="check_files"
    )
    
    return tmp, worlds_dir, programs_dir, scenarios_dir, data_dir

def run_demo():
    tmp, worlds_dir, programs_dir, scenarios_dir, data_dir = setup_demo_env()
    
    world_reg = WorldRegistry(worlds_dir)
    prog_store = ProgramStore(programs_dir)
    scen_reg = ScenarioRegistry(scenarios_dir)
    
    world_svc = WorldOperatorService(
        world_reg, 
        data_dir / "world_activation_history.jsonl",
        data_dir / "operator_events.jsonl"
    )
    prog_svc = ProgramOperatorService(prog_store, world_reg, data_dir / "operator_events.jsonl")
    
    print_header("SYS-4A: Operator Surface Demo")
    print(f"{_DIM}Repository: {tmp}{_RESET}")
    
    # 1. List worlds
    print_step(1, "List available worlds")
    worlds = world_svc.list_worlds()
    for w in worlds:
        print(f"  {_BOLD}{w['world_id']}@{w['version']}{_RESET} - {w['description']}")
        
    # 2. Show active world
    print_step(2, "Inspect active world state")
    active = world_svc.get_active_world()
    if not active:
        print(f"  {_YELLOW}(no active world - runtime is in default DENY mode){_RESET}")
        
    # 3. List reviewed programs
    print_step(3, "List reviewed programs and compatibility")
    progs = prog_svc.list_programs()
    for p in progs:
        compat = f"{_RED}NO{_RESET}"
        print(f"  ID: {p.program_id:<15} Status: {p.status:<10} Compatible: {compat}")
        
    # 4. Preview impact
    target_id, target_ver = "world_basic", "1.0"
    print_step(4, f"Preview IMPACT of activating {target_id}@{target_ver}")
    report = world_svc.preview_activation_impact(target_id, target_ver, prog_store, scen_reg)
    
    for p in report.affected_programs:
        impact_col = _GREEN if p['impact'] == 'changed_behavior' else _RED
        print(f"  {p['program_id']:<15} -> {_BOLD}{impact_col}{p['impact'].upper()}{_RESET}: {p['summary']}")
        
    # 5. Activate world
    print_step(5, f"Executing activation: {target_id}@{target_ver}")
    world_svc.activate_world(target_id, target_ver, reason="Initial setup")
    print(f"  {_GREEN}✓ Action complete.{_RESET}")
    
    # 6. Show new state
    print_step(6, "Inspect new active world")
    active = world_svc.get_active_world()
    print_json(active)
    
    # 7. List programs again
    print_step(7, "Inspect programs under new world")
    progs = prog_svc.list_programs()
    for p in progs:
        compat = f"{_GREEN}YES{_RESET}" if p.compatible_with_active_world else f"{_RED}NO{_RESET}"
        print(f"  ID: {p.program_id:<15} Status: {p.status:<10} Compatible: {compat}")
        
    # 8. Upgrade world and see impact
    print_step(8, "Upgrading to world_basic@2.0 (expanding boundary)")
    world_svc.activate_world("world_basic", "2.0", reason="Upgrade for shell access")
    progs = prog_svc.list_programs()
    for p in progs:
        compat = f"{_GREEN}YES{_RESET}" if p.compatible_with_active_world else f"{_RED}NO{_RESET}"
        print(f"  ID: {p.program_id:<15} Status: {p.status:<10} Compatible: {compat}")
        
    # 9. Rollback
    print_step(9, "Emergency ROLLBACK to previous world")
    record = world_svc.rollback_world(reason="Audit failure on v2")
    print(f"  {_GREEN}✓ Rolled back to {record.world_id}@{record.version}{_RESET}")
    
    active = world_svc.get_active_world()
    print(f"  Current world: {_BOLD}{active['world_id']}@{active['version']}{_RESET}")

    # 10. Audit log
    print_step(10, "Inspect Activation History (Audit Trail)")
    history = world_svc.get_activation_history()
    for entry in history:
        prev = entry.get('previous_world_id', 'none')
        if prev != 'none': prev = f"{prev}@{entry['previous_version']}"
        print(f"  {entry['activated_at'][:19]} | {entry['world_id']}@{entry['version']} (prev: {prev}) - {entry['reason']}")

    print_header("Demo Complete")
    shutil.rmtree(tmp)

if __name__ == "__main__":
    run_demo()
