"""
comparative_playground_demo.py — SYS-3 end-to-end demonstration.

ONE program, multiple worlds, divergent outcomes.  The program is loaded
via a Scenario; each world is evaluated via ``run_scenario`` which composes
``check_compatibility`` (preview) and ``ReplayEngine.replay_under_world``
(execution) without modifying the sealed runtime.

Flow:
    1. Build a ProgramStore and a WorldRegistry in a tempdir, seeded with
       the bundled strict/balanced worlds.
    2. Load the bundled ``memory_write_test`` scenario (program_steps:
       ``[count_words, normalize_text]``; worlds: ``world_strict``,
       ``world_balanced``).
    3. Call ``run_scenario`` — preview + replay runs under each world.
    4. Pretty-print per-world outcomes and the divergence report.

Expected outcome:
    world_strict  @1.0: preview=incompatible, replay=denied_at_preview,
                        step[1] normalize_text DENY (capability).
    world_balanced@1.0: preview=compatible,   replay=allow,
                        all steps ALLOW.
    Divergence points: [step[1] normalize_text].

Run:
    python examples/comparative_playground_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_hypervisor.program_layer import (
    ProgramStore,
    ScenarioRegistry,
    WorldRegistry,
    run_scenario,
)


BUNDLED_WORLDS_DIR = (
    Path(__file__).parent.parent
    / "src" / "agent_hypervisor" / "program_layer" / "worlds"
)
BUNDLED_SCENARIOS_DIR = (
    Path(__file__).parent.parent
    / "src" / "agent_hypervisor" / "program_layer" / "scenarios"
)


def _sep(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print("─" * 64)


def _print_world_result(wr) -> None:
    preview = "compatible" if wr.preview_compatible else "INCOMPATIBLE"
    print(f"\n  World: {wr.key}")
    print(f"    preview: {preview}")
    for o in wr.step_outcomes:
        mark = "✓" if o.verdict == "allow" else ("✗" if o.verdict == "deny" else "·")
        print(
            f"    {mark} step[{o.step_index}] {o.action:<18} "
            f"{o.verdict.upper():<5} ({o.stage}/{o.rule_kind}: {o.reason})"
        )
    print(f"    replay:  {wr.replay_verdict}")


def _print_divergence(report) -> None:
    print(f"\n  Divergence ({len(report.divergence_points)} point(s)):")
    if report.all_agree:
        print("    (worlds agreed on every step)")
        return
    for d in report.divergence_points:
        print(f"    step[{d.step_index}] {d.action}")
        for wk, v in d.verdicts_by_world.items():
            print(f"      {wk:<22} {v.upper():<5}  "
                  f"{d.reasons_by_world.get(wk, '')}")


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Step 1 — stores + registries
        _sep("STEP 1 — Set up ProgramStore, WorldRegistry, ScenarioRegistry")
        store = ProgramStore(tmp / "programs")
        worlds_dir = tmp / "worlds"
        worlds_dir.mkdir()
        for yaml in BUNDLED_WORLDS_DIR.glob("*.yaml"):
            shutil.copy(yaml, worlds_dir / yaml.name)
        registry = WorldRegistry(worlds_dir=worlds_dir, active_file=tmp / "active.json")
        scen_reg = ScenarioRegistry(BUNDLED_SCENARIOS_DIR)

        print(f"\n  programs dir:  {tmp / 'programs'}")
        print(f"  worlds dir:    {worlds_dir}")
        print(f"  scenarios dir: {BUNDLED_SCENARIOS_DIR}")
        print("\n  Registered worlds:")
        for w in registry.list_worlds():
            print(f"    {w.world_id}@{w.version}  "
                  f"actions={sorted(w.allowed_actions)}")
        print("\n  Bundled scenarios:")
        for s in scen_reg.list_scenarios():
            print(f"    {s.scenario_id:<24} ({len(s.worlds)} worlds)  {s.name}")

        # Step 2 — pick a scenario
        _sep("STEP 2 — Load scenario 'memory_write_test'")
        scenario = scen_reg.get("memory_write_test")
        print(f"\n  scenario_id: {scenario.scenario_id}")
        print(f"  name:        {scenario.name}")
        print(f"  description: {scenario.description.strip()}")
        if scenario.program_steps:
            print("  program_steps (inline):")
            for i, st in enumerate(scenario.program_steps):
                print(f"    [{i}] {st.tool}  params={st.params}")
        print("  worlds:")
        for w in scenario.worlds:
            print(f"    {w.world_id}@{w.version}")

        # Step 3 — run the scenario
        _sep("STEP 3 — run_scenario(...) across all worlds")
        result = run_scenario(
            scenario,
            registry=registry,
            store=store if scenario.program_id else None,
        )

        # Step 4 — report
        _sep("STEP 4 — Per-world results")
        for wr in result.world_results:
            _print_world_result(wr)

        _sep("STEP 5 — Divergence report")
        _print_divergence(result.divergence)

        # Summary
        _sep("SUMMARY")
        print(f"""
  Scenario           : {result.scenario_id}
  Program            : {result.program_id}
  Worlds compared    : {len(result.world_results)}
  Divergence points  : {len(result.divergence.divergence_points)}
  All worlds agree   : {result.divergence.all_agree}
  run_id             : {result.run_id}
  ran_at             : {result.ran_at}

  Moral: the program is the same.  The world is what decides.
""")

        blob = json.dumps(result.to_dict(), default=str)
        print("  JSON artifact (first 400 chars):")
        print("  " + blob[:400] + ("…" if len(blob) > 400 else ""))


if __name__ == "__main__":
    run_demo()
