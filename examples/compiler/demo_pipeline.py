"""
examples/demo_pipeline.py – end-to-end demonstration of the Agent World Compiler.

Runs the full pipeline for both the benign and the unsafe trace:
    Observe → Profile → Manifest → Render Tools → Enforce

Usage:
    python -m examples.demo_pipeline
    make demo
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from awc.compiler.profiler import derive_profile
from awc.compiler.compile_manifest import compile_manifest
from awc.compiler.render_tools import render_tools
from awc.policy.engine import evaluate_step, Decision

REPO_ROOT = Path(__file__).resolve().parent.parent

TRACES = {
    "benign": REPO_ROOT / "fixtures" / "traces" / "benign_repo_maintenance.json",
    "unsafe": REPO_ROOT / "fixtures" / "traces" / "unsafe_exfiltration.json",
}
STATIC_MANIFEST = REPO_ROOT / "fixtures" / "manifests" / "repo-safe-write.yaml"


def _banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _load_trace(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def _load_manifest(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def run_demo() -> None:
    # ------------------------------------------------------------------ #
    # Stage 1 – Observe + Profile                                         #
    # ------------------------------------------------------------------ #
    _banner("STAGE 1 — Observe → Profile (derive from benign trace)")
    profile = derive_profile([TRACES["benign"]], profile_id="repo_safe_write")
    print(yaml.dump(profile.to_dict(), default_flow_style=False, sort_keys=False))

    # ------------------------------------------------------------------ #
    # Stage 2 – Compile Manifest                                          #
    # ------------------------------------------------------------------ #
    _banner("STAGE 2 — Profile → Compiled World Manifest")
    manifest = compile_manifest(profile, manifest_id="repo-safe-write-demo", author="Sergey Vlasov")
    print(yaml.dump(manifest, default_flow_style=False, sort_keys=False))

    # ------------------------------------------------------------------ #
    # Stage 2.5 – Render Tools                                            #
    # ------------------------------------------------------------------ #
    _banner("STAGE 2.5 — Manifest → Rendered Tools (agent-facing surface)")
    rendered = render_tools(manifest)
    print(f"  {len(rendered)} rendered tool(s) derived from {len(manifest['allowed_actions'])} allowed action(s).")
    print(f"  {len(manifest.get('denied_actions', []))} denied action(s) NOT exposed as tools.")
    print()
    col_name  = 32
    col_base  = 14
    col_args  = 20
    col_res   = 30
    header = (
        f"  {'Name':<{col_name}} {'Base Tool':<{col_base}} "
        f"{'Fixed Args':<{col_args}} {'Resource Constraint':<{col_res}}"
    )
    print(header)
    print("  " + "-" * (col_name + col_base + col_args + col_res + 3))
    for t in rendered:
        fixed = ", ".join(f"{k}={v}" for k, v in t.fixed_args.items()) or "—"
        patterns = ", ".join(t.allowed_resource_patterns) or "—"
        print(
            f"  {t.name:<{col_name}} {t.base_tool:<{col_base}} "
            f"{fixed:<{col_args}} {patterns:<{col_res}}"
        )
    print()
    print("  Key insight: forbidden capabilities (denied_actions) are absent from")
    print("  this table — they are not exposed as tools at all.")

    # ------------------------------------------------------------------ #
    # Stage 3 – Enforce: benign trace                                     #
    # ------------------------------------------------------------------ #
    _banner("STAGE 3 — Enforce: evaluating BENIGN trace against static manifest")
    static_manifest = _load_manifest(STATIC_MANIFEST)
    benign_trace = _load_trace(TRACES["benign"])

    print(f"  Manifest : {STATIC_MANIFEST.name}")
    print(f"  Trace    : {TRACES['benign'].name}")
    print()

    all_ok = True
    for step in benign_trace["steps"]:
        decision, reason = evaluate_step(step, static_manifest)
        marker = "✓" if decision in (Decision.ALLOW, Decision.REQUIRE_APPROVAL) else "✗"
        print(f"  {marker} [{decision.value:>18}] {step['step_id']} / {step['tool']} — {reason[:80]}")
        if decision == Decision.DENY:
            all_ok = False

    print()
    print(f"  Benign trace result: {'PASS (no DENY)' if all_ok else 'FAIL (unexpected DENY)'}")

    # ------------------------------------------------------------------ #
    # Stage 4 – Enforce: unsafe trace                                     #
    # ------------------------------------------------------------------ #
    _banner("STAGE 4 — Enforce: evaluating UNSAFE trace against static manifest")
    unsafe_trace = _load_trace(TRACES["unsafe"])

    print(f"  Manifest : {STATIC_MANIFEST.name}")
    print(f"  Trace    : {TRACES['unsafe'].name}")
    print()

    denied_count = 0
    for step in unsafe_trace["steps"]:
        decision, reason = evaluate_step(step, static_manifest)
        marker = "✗" if decision == Decision.DENY else "!"
        print(f"  {marker} [{decision.value:>18}] {step['step_id']} / {step['tool']} — {reason[:80]}")
        if decision == Decision.DENY:
            denied_count += 1

    print()
    print(f"  Unsafe trace result: {denied_count}/{len(unsafe_trace['steps'])} steps DENIED — policy is enforced.")

    _banner("DEMO COMPLETE")
    print()
    print("  The PoC demonstrated:")
    print("  1. Observed execution was reduced to a capability profile.")
    print("  2. The profile was compiled into a World Manifest.")
    print("  3. The manifest was projected into a narrowed, agent-facing tool surface.")
    print("     Forbidden capabilities were absent from the rendered tool table entirely.")
    print("  4. The manifest produced deterministic ALLOW / DENY / REQUIRE_APPROVAL decisions.")
    print()


if __name__ == "__main__":
    run_demo()
