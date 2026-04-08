"""
examples/record_and_compile.py – demonstrate Stage 0 (record) feeding Stage 1+.

Shows that the TraceRecorder is how traces are *produced* in the first place.
The fixture JSON files in fixtures/traces/ are the output of a recorder;
this example recreates the benign workflow from scratch in memory, then
runs the full pipeline on the freshly recorded trace.

Pipeline shown:
    Record  →  Profile  →  Compile  →  Enforce

Usage:
    python -m examples.record_and_compile
"""

from __future__ import annotations

import yaml  # type: ignore[import-untyped]

from awc.observe.recorder import TraceRecorder
from awc.compiler.profiler import derive_profile
from awc.compiler.compile_manifest import compile_manifest
from awc.policy.engine import evaluate_step, Decision
from awc.policy.taint import compute_trace_taint


def _banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def run() -> None:
    # ------------------------------------------------------------------ #
    # Stage 0 – Record                                                    #
    #                                                                     #
    # In a real deployment the agent would call the recorder after each   #
    # tool invocation.  Here we call it manually to simulate a benign     #
    # repository-maintenance workflow.                                     #
    # ------------------------------------------------------------------ #
    _banner("STAGE 0 — Record (simulate benign repo-maintenance workflow)")

    recorder = TraceRecorder(
        workflow="repo_maintenance",
        trace_id="trace-recorded-demo",
        description="Simulated benign workflow recorded by TraceRecorder.",
    )

    step_read = recorder.record(
        tool="fs_read",
        action="read",
        resource="repo://local/src/main.py",
        input_sources=["repo_local"],
        metadata={"bytes_read": 1240},
    )
    step_test = recorder.record(
        tool="shell_exec",
        action="exec",
        resource="shell://local",
        input_sources=["repo_local"],
        depends_on=[step_read],
        metadata={"command": "pytest tests/", "exit_code": 0},
    )
    step_add = recorder.record(
        tool="git_add",
        action="write",
        resource="repo://local/staging",
        input_sources=["repo_local"],
        depends_on=[step_test],
    )
    step_commit = recorder.record(
        tool="git_commit",
        action="write",
        resource="repo://local/commits",
        input_sources=["repo_local"],
        depends_on=[step_add],
        metadata={"message": "chore: update main module"},
    )
    recorder.record(
        tool="git_push",
        action="write",
        resource="repo://remote/origin/main",
        input_sources=["repo_local"],
        depends_on=[step_commit],
        metadata={"remote": "origin", "branch": "main"},
    )

    trace = recorder.to_dict()
    print(f"  Recorded {len(recorder)} steps for workflow '{recorder.workflow}'")
    for step in trace["steps"]:
        print(f"    {step['step_id']}  {step['tool']:<14} → {step['resource']}")

    # ------------------------------------------------------------------ #
    # Stage 1 – Profile (derive from the recorded trace, no file needed)  #
    # ------------------------------------------------------------------ #
    _banner("STAGE 1 — Profile (derive capability profile from recorded trace)")

    # save to a temp file so derive_profile (which expects a path) can load it
    import tempfile, json, pathlib

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp:
        json.dump(trace, tmp)
        tmp_path = pathlib.Path(tmp.name)

    profile = derive_profile([tmp_path], profile_id="repo_safe_write_recorded")
    print(yaml.dump(profile.to_dict(), default_flow_style=False, sort_keys=False))

    # ------------------------------------------------------------------ #
    # Stage 2 – Compile                                                   #
    # ------------------------------------------------------------------ #
    _banner("STAGE 2 — Compile (profile → World Manifest)")

    manifest = compile_manifest(
        profile,
        manifest_id="repo-safe-write-recorded",
        author="demo",
    )
    print(yaml.dump(manifest, default_flow_style=False, sort_keys=False))

    # ------------------------------------------------------------------ #
    # Stage 3 – Enforce (evaluate the recorded steps against the manifest) #
    # ------------------------------------------------------------------ #
    _banner("STAGE 3 — Enforce (evaluate recorded steps against compiled manifest)")

    steps = trace["steps"]
    taint_map = compute_trace_taint(steps, manifest.get("input_trust", {}))

    all_ok = True
    for step in steps:
        derived_taint, taint_reasons = taint_map[step["step_id"]]
        decision, reason = evaluate_step(step, manifest, derived_taint, taint_reasons)
        marker = "✓" if decision in (Decision.ALLOW, Decision.REQUIRE_APPROVAL) else "✗"
        print(
            f"  {marker} [{decision.value:>18}] "
            f"{step['step_id']} / {step['tool']} — {reason[:72]}"
        )
        if decision == Decision.DENY:
            all_ok = False

    print()
    print(f"  Result: {'PASS (no DENY)' if all_ok else 'FAIL (unexpected DENY)'}")

    _banner("DEMO COMPLETE")
    print()
    print("  The recorder is Stage 0 of the pipeline.")
    print("  Fixtures in fixtures/traces/ are the saved output of a recorder run.")
    print()

    tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
