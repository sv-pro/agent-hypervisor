"""
operator_surface_demo.py — SYS-4A Operator Surface Foundation demo.

Demonstrates the full operator lifecycle:
  1. list worlds
  2. show active world
  3. list reviewed programs
  4. preview activation impact for another world
  5. activate target world
  6. show new active world
  7. list programs now incompatible or changed
  8. rollback
  9. show restored state

Run with:
    python examples/operator_surface_demo.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Ensure the package root is importable when run directly.
_ROOT = Path(__file__).parent.parent / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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
    WorldOperatorService,
    WorldRegistry,
    default_registry,
    default_scenario_registry,
    propose_program,
    review_program,
)

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_G = "\033[32m"
_R = "\033[31m"
_Y = "\033[33m"
_B = "\033[1m"
_D = "\033[2m"
_X = "\033[0m"


def _hdr(title: str) -> None:
    width = 60
    print()
    print(_B + "─" * width + _X)
    print(_B + f"  {title}" + _X)
    print(_B + "─" * width + _X)


def _ok(msg: str) -> None:
    print(f"  {_G}✓{_X}  {msg}")


def _info(msg: str) -> None:
    print(f"  {_D}{msg}{_X}")


# ── Fixture programs ──────────────────────────────────────────────────────────


def _build_fixture_programs(store: ProgramStore) -> list[str]:
    """
    Create two programs in the store:
      prog_A — uses only count_words/count_lines (compatible with world_strict)
      prog_B — uses normalize_text (incompatible with world_strict)
    """
    ids: list[str] = []

    steps_a = [
        CandidateStep(tool="count_words", params={"input": "hello world"}, provenance="demo"),
        CandidateStep(tool="count_lines", params={"input": "line1\nline2"}, provenance="demo"),
    ]
    prog_a = propose_program(
        steps=steps_a,
        trace_id="trace-demo-a",
        world_version="1.0",
        store=store,
    )
    review_program(prog_a.id, store, notes="looks good")
    ids.append(prog_a.id)

    steps_b = [
        CandidateStep(tool="count_words", params={"input": "hello world"}, provenance="demo"),
        CandidateStep(tool="normalize_text", params={"input": "Hello WORLD"}, provenance="demo"),
    ]
    prog_b = propose_program(
        steps=steps_b,
        trace_id="trace-demo-b",
        world_version="1.0",
        store=store,
    )
    review_program(prog_b.id, store, notes="uses normalize_text")
    ids.append(prog_b.id)

    return ids


# ── Main demo ─────────────────────────────────────────────────────────────────


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="op_demo_") as tmpdir:
        tmp = Path(tmpdir)
        history_file = tmp / "world_activation_history.jsonl"
        events_file = tmp / "operator_events.jsonl"
        store_dir = tmp / "programs"

        # Wire services
        worlds_reg = default_registry(active_file=tmp / ".active.json")
        event_log = OperatorEventLog(events_file)
        world_svc = WorldOperatorService(
            registry=worlds_reg,
            history_file=history_file,
            event_log=event_log,
        )
        store = ProgramStore(store_dir)
        prog_svc = ProgramOperatorService(
            store=store,
            registry=worlds_reg,
            event_log=event_log,
        )
        scen_reg = default_scenario_registry()
        scen_svc = ScenarioOperatorService(
            scenario_registry=scen_reg,
            trace_store=None,
            event_log=event_log,
        )

        # ── 1. List worlds ────────────────────────────────────────────────
        _hdr("Step 1 — List Worlds")
        worlds = world_svc.list_worlds()
        for w in worlds:
            _info(f"{w.world_id:<18} v{w.version}  {len(w.allowed_actions)} actions")

        # ── 2. Activate starting world (world_balanced) ───────────────────
        _hdr("Step 2 — Activate Starting World (world_balanced)")
        rec = world_svc.activate_world("world_balanced", reason="demo start", activated_by="demo")
        _ok(f"activated {rec.world_id} {rec.version}  id={rec.activation_id}")

        active = world_svc.get_active_world()
        _info(f"active: {active.world_id} {active.version}")

        # ── 3. Build & list reviewed programs ────────────────────────────
        _hdr("Step 3 — Create & List Reviewed Programs")
        prog_ids = _build_fixture_programs(store)
        summaries = prog_svc.list_programs()
        print(f"  {'program_id':<28} {'status':<12} {'compat':>8}")
        print(f"  {'─' * 54}")
        for s in summaries:
            compat = (
                f"{_G}yes{_X}" if s.compatible_with_active_world is True
                else (f"{_R}no{_X}" if s.compatible_with_active_world is False else "–")
            )
            print(f"  {s.program_id:<28} {s.status:<12} {compat:>8}")

        # ── 4. Preview impact of switching to world_strict ────────────────
        _hdr("Step 4 — Preview Impact: world_strict")
        report = world_svc.preview_activation_impact(
            "world_strict", "1.0", store, scen_reg
        )
        print(f"  target:  {report.target_world['world_id']} {report.target_world['version']}")
        print(f"  current: {report.current_world['world_id']} {report.current_world['version']}")
        print()
        for p in report.affected_programs:
            cur = "–" if p.current_compatible is None else ("✓" if p.current_compatible else "✗")
            tgt = f"{_G}✓{_X}" if p.target_compatible else f"{_R}✗{_X}"
            print(f"  {p.program_id:<28}  current={cur}  target={tgt}  {_D}{p.summary}{_X}")
        print()
        t = report.totals
        col = _R if t["programs_becoming_incompatible"] else _G
        print(f"  programs becoming incompatible: "
              f"{col}{t['programs_becoming_incompatible']}{_X} / {t['reviewed_programs_checked']}")

        # ── 5. Activate world_strict ──────────────────────────────────────
        _hdr("Step 5 — Activate world_strict")
        rec2 = world_svc.activate_world(
            "world_strict", reason="testing strict mode", activated_by="demo"
        )
        _ok(f"activated {rec2.world_id} {rec2.version}  id={rec2.activation_id}")
        _info(f"previous was: {rec2.previous_world_id} {rec2.previous_version}")

        # ── 6. Show new active world ──────────────────────────────────────
        _hdr("Step 6 — Active World After Switch")
        active2 = world_svc.get_active_world()
        print(f"  {_B}{active2.world_id}{_X}  v{active2.version}")
        print(f"  allowed actions: {sorted(active2.allowed_actions)}")

        # ── 7. List programs — some are now incompatible ──────────────────
        _hdr("Step 7 — Programs Under world_strict")
        summaries2 = prog_svc.list_programs()
        for s in summaries2:
            compat = (
                f"{_G}compatible{_X}" if s.compatible_with_active_world is True
                else (f"{_R}incompatible{_X}" if s.compatible_with_active_world is False else "–")
            )
            print(f"  {s.program_id:<28} {compat}")

        # ── 8. Rollback ───────────────────────────────────────────────────
        _hdr("Step 8 — Rollback")
        rb = world_svc.rollback_world(reason="demo rollback")
        _ok(f"rolled back to {rb.world_id} {rb.version}  id={rb.activation_id}")

        # ── 9. Restored state ─────────────────────────────────────────────
        _hdr("Step 9 — Restored State")
        active3 = world_svc.get_active_world()
        print(f"  active world: {_B}{active3.world_id}{_X}  v{active3.version}")

        summaries3 = prog_svc.list_programs()
        all_compat = all(s.compatible_with_active_world is True for s in summaries3)
        print(f"  all programs compatible: "
              f"{_G}yes{_X}" if all_compat else f"  all programs compatible: {_R}no{_X}")

        history = world_svc.get_activation_history()
        print(f"  activation history entries: {len(history)}")

        # ── Summary ───────────────────────────────────────────────────────
        _hdr("Done")
        _ok("lifecycle made visible")
        _ok("world switching safe and reversible")
        _ok("impact preview ran before activation")
        _ok("rollback restored prior state")
        print()


if __name__ == "__main__":
    main()
