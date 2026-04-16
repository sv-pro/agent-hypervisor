"""
program_world_compatibility_demo.py — SYS-2 light end-to-end demonstration.

Same program, different World, different verdict.

Flow:
    1. Create an empty ProgramStore and a WorldRegistry seeded with two
       worlds (world_strict, world_balanced).
    2. Propose → minimize → review → accept a program that uses
       count_words + normalize_text.
    3. List the registered worlds.
    4. Preview the accepted program under world_strict  → expect incompatible
       (world_strict does NOT allow normalize_text).
    5. Preview the accepted program under world_balanced → expect compatible.
    6. compare_program_across_worlds → print the divergence point.
    7. Replay under world_balanced  → allow.
    8. Replay under world_strict    → deny before execution.

The takeaway: historical acceptance does not grant ongoing authority.
The current World always decides.

Run:
    python examples/program_world_compatibility_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_hypervisor.program_layer import (
    CandidateStep,
    ProgramStore,
    ReplayEngine,
    WorldRegistry,
    accept_program,
    check_compatibility,
    compare_program_across_worlds,
    minimize_program,
    preview_program_under_world,
    propose_program,
    review_program,
)
from agent_hypervisor.program_layer.task_compiler import DeterministicTaskCompiler


BUNDLED_WORLDS_DIR = (
    Path(__file__).parent.parent
    / "src" / "agent_hypervisor" / "program_layer" / "worlds"
)


def _sep(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print("─" * 64)


def _print_compat(compat) -> None:
    verdict = "COMPATIBLE" if compat.compatible else "INCOMPATIBLE"
    print(
        f"\n  program={compat.program_id}  world={compat.world_id}@{compat.world_version}  "
        f"→ {verdict}"
    )
    for sr in compat.step_results:
        mark = "✓" if sr.allowed else "✗"
        print(f"    {mark} step[{sr.step_index}] {sr.action!r}  {sr.reason}")
    s = compat.summary
    print(f"  summary: allowed={s.allowed_steps}  denied={s.denied_steps}  "
          f"restricted={list(s.restricted_actions)}")


def _print_diff(diff) -> None:
    print(f"\n  program={diff.program_id}")
    print(f"  world_a={diff.world_a['id']}@{diff.world_a['version']}  "
          f"world_b={diff.world_b['id']}@{diff.world_b['version']}")
    print(f"  both_compatible={diff.both_compatible}")
    if not diff.divergence_points:
        print("  (no divergence points — worlds agree on every step)")
        return
    print("  divergence_points:")
    for d in diff.divergence_points:
        print(f"    step[{d.step_index}] {d.action!r}")
        print(f"      world_a: {d.world_a}")
        print(f"      world_b: {d.world_b}")
        print(f"      reason : {d.reason}")


def _print_replay(rt) -> None:
    print(
        f"\n  replay={rt.replay_id}  program={rt.program_id}  "
        f"world={rt.world_id}@{rt.world_version} (source={rt.world_source})"
    )
    print(f"  preview_compatible={rt.preview_compatible}  final_verdict={rt.final_verdict}")
    for st in rt.program_trace.step_traces:
        mark = "✓" if st.verdict == "allow" else "✗"
        print(f"    {mark} step[{st.step_index}] {st.action!r}  "
              f"verdict={st.verdict}  error={st.error}")


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ----------------------------------------------------------------
        # Step 1: Set up store + registry (copy bundled worlds in)
        # ----------------------------------------------------------------
        _sep("STEP 1 — Set up ProgramStore and WorldRegistry")
        store = ProgramStore(tmp / "programs")
        worlds_dir = tmp / "worlds"
        worlds_dir.mkdir()
        for yaml in BUNDLED_WORLDS_DIR.glob("*.yaml"):
            shutil.copy(yaml, worlds_dir / yaml.name)
        registry = WorldRegistry(worlds_dir=worlds_dir, active_file=tmp / "active.json")
        print(f"\n  programs dir: {tmp / 'programs'}")
        print(f"  worlds dir:   {worlds_dir}")

        # ----------------------------------------------------------------
        # Step 2: Propose → minimize → review → accept
        # ----------------------------------------------------------------
        _sep("STEP 2 — Accept a program via PL-3 lifecycle")
        steps = [
            CandidateStep(tool="count_words", params={"input": "the quick brown fox"}),
            CandidateStep(tool="normalize_text", params={"input": "HELLO WORLD"}),
        ]
        prog = propose_program(
            steps=steps,
            trace_id="demo-trace-001",
            world_version="1.0",
            store=store,
            program_id="prog-sys2-demo",
        )
        minimize_program(prog.id, store)
        review_program(prog.id, store, notes="Demo program for SYS-2 light.")
        accept_program(
            prog.id,
            store,
            allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS,
        )
        accepted = store.load(prog.id)
        print(f"\n  id={accepted.id}  status={accepted.status.value}  "
              f"steps={len(accepted.minimized_steps)}")

        # ----------------------------------------------------------------
        # Step 3: List worlds
        # ----------------------------------------------------------------
        _sep("STEP 3 — List available worlds")
        for w in registry.list_worlds():
            print(f"  {w.world_id}@{w.version}  actions={sorted(w.allowed_actions)}")

        # ----------------------------------------------------------------
        # Step 4: Preview under world_strict (expect incompatible)
        # ----------------------------------------------------------------
        _sep("STEP 4 — Preview under world_strict")
        strict = registry.get("world_strict", "1.0")
        compat_strict = check_compatibility(accepted, strict)
        _print_compat(compat_strict)

        # ----------------------------------------------------------------
        # Step 5: Preview under world_balanced (expect compatible)
        # ----------------------------------------------------------------
        _sep("STEP 5 — Preview under world_balanced")
        balanced = registry.get("world_balanced", "1.0")
        compat_balanced = preview_program_under_world(
            program_id=accepted.id,
            world_id="world_balanced",
            version="1.0",
            store=store,
            registry=registry,
        )
        _print_compat(compat_balanced)

        # ----------------------------------------------------------------
        # Step 6: Compare across worlds
        # ----------------------------------------------------------------
        _sep("STEP 6 — Compare across worlds")
        diff = compare_program_across_worlds(
            program_id=accepted.id,
            world_a_id="world_strict",
            world_a_version="1.0",
            world_b_id="world_balanced",
            world_b_version="1.0",
            store=store,
            registry=registry,
        )
        _print_diff(diff)

        # ----------------------------------------------------------------
        # Step 7: Replay under world_balanced (allow)
        # ----------------------------------------------------------------
        _sep("STEP 7 — Replay under world_balanced")
        engine = ReplayEngine()
        rt_balanced = engine.replay_under_world(
            accepted,
            balanced,
            preview_compatible=compat_balanced.compatible,
        )
        _print_replay(rt_balanced)

        # ----------------------------------------------------------------
        # Step 8: Replay under world_strict (deny before execution)
        # ----------------------------------------------------------------
        _sep("STEP 8 — Replay under world_strict")
        rt_strict = engine.replay_under_world(
            accepted,
            strict,
            preview_compatible=compat_strict.compatible,
        )
        _print_replay(rt_strict)

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        _sep("SUMMARY")
        print(f"""
  Program                : {accepted.id}  ({len(accepted.minimized_steps)} step(s))
  world_strict  preview  : {'compatible' if compat_strict.compatible else 'INCOMPATIBLE'}
  world_balanced preview : {'compatible' if compat_balanced.compatible else 'INCOMPATIBLE'}
  Divergence points      : {len(diff.divergence_points)}
  Replay in balanced     : {rt_balanced.final_verdict}
  Replay in strict       : {rt_strict.final_verdict}

  Moral: the program is the same. The World is what decides.
""")

        # Emit a single JSON blob with all the artifacts for audit/offline use.
        artifacts = {
            "program_id": accepted.id,
            "preview_strict": compat_strict.to_dict(),
            "preview_balanced": compat_balanced.to_dict(),
            "diff": diff.to_dict(),
            "replay_balanced": rt_balanced.to_dict(),
            "replay_strict": rt_strict.to_dict(),
        }
        print("  JSON artifacts (first 400 chars):")
        blob = json.dumps(artifacts, default=str)
        print("  " + blob[:400] + ("…" if len(blob) > 400 else ""))


if __name__ == "__main__":
    run_demo()
