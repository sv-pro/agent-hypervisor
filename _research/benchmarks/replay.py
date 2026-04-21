"""
benchmarks/replay.py — Replay any recorded trace through the current policy.

Given a JSONL trace from run_scenarios.py, replays each scenario through
the current policy engine and compares the replayed outcome with the recorded
outcome.  This verifies:

  1. Determinism: same input → same outcome across runs and manifest edits.
  2. Drift detection: if a manifest change causes a verdict to change,
     replay immediately surfaces the divergence.

The walkthrough mode (--walkthrough) demonstrates the
Design → Compile → Deploy → Learn → Redesign cycle:

  Design:   author a world manifest rule
  Compile:  run_scenarios.py writes a trace (this is the "baseline")
  Deploy:   manifest is active at runtime
  Learn:    inspect the trace to understand why verdicts were reached
  Redesign: edit the manifest, re-run run_scenarios.py, compare traces

Usage:
    # Replay latest trace (determinism check)
    python _research/benchmarks/replay.py

    # Replay a specific trace file
    python _research/benchmarks/replay.py --trace _research/benchmarks/traces/run-<ts>.jsonl

    # Step-by-step walkthrough with cycle explanation
    python _research/benchmarks/replay.py --walkthrough
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths / imports
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
REPO_ROOT = _HERE.parent.parent
SRC_DIR = REPO_ROOT / "src" / "agent_hypervisor"

for p in (str(REPO_ROOT / "src"), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml
from hypervisor.policy_engine import PolicyEngine
from hypervisor.models import ToolCall, ValueRef, ProvenanceClass

TRACES_DIR = _HERE / "traces"
POLICIES_DIR = _HERE / "policies"
SCENARIOS_DIR = _HERE / "scenarios"

# ---------------------------------------------------------------------------
# Load scenario index (scenario_id → fixture dict) for full-arg replay
# ---------------------------------------------------------------------------

def _build_scenario_index() -> dict[str, dict]:
    import json as _json
    index: dict[str, dict] = {}
    for f in SCENARIOS_DIR.rglob("*.json"):
        try:
            data = _json.loads(f.read_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                sid = item.get("scenario_id")
                if sid:
                    index[sid] = item
        except Exception:
            pass
    return index

_SCENARIO_INDEX: dict[str, dict] | None = None


def _get_scenario(scenario_id: str) -> dict | None:
    global _SCENARIO_INDEX
    if _SCENARIO_INDEX is None:
        _SCENARIO_INDEX = _build_scenario_index()
    return _SCENARIO_INDEX.get(scenario_id)

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RED   = "\033[31m"
_GREEN = "\033[32m"
_CYAN  = "\033[36m"


def _g(t: str) -> str: return f"{_GREEN}{t}{_RESET}"
def _r(t: str) -> str: return f"{_RED}{t}{_RESET}"
def _b(t: str) -> str: return f"{_BOLD}{t}{_RESET}"
def _d(t: str) -> str: return f"{_DIM}{t}{_RESET}"
def _c(t: str) -> str: return f"{_CYAN}{t}{_RESET}"

# ---------------------------------------------------------------------------
# Channel → provenance
# ---------------------------------------------------------------------------

_CHANNEL_PROVENANCE: dict[str, ProvenanceClass] = {
    "user":   ProvenanceClass.user_declared,
    "email":  ProvenanceClass.external_document,
    "web":    ProvenanceClass.external_document,
    "file":   ProvenanceClass.external_document,
    "mcp":    ProvenanceClass.derived,
    "agent":  ProvenanceClass.derived,
    "system": ProvenanceClass.system,
}

_VERDICT_MAP = {"allow": "allow", "deny": "deny", "ask": "require_approval"}

_policy_cache: dict[str, PolicyEngine] = {}


def _load_policy(manifest: str) -> PolicyEngine:
    if manifest not in _policy_cache:
        policy_file = POLICIES_DIR / f"{manifest}.yaml"
        if policy_file.exists():
            data = yaml.safe_load(policy_file.read_text())
        else:
            default = REPO_ROOT / "src" / "agent_hypervisor" / "runtime" / "configs" / "default_policy.yaml"
            data = yaml.safe_load(default.read_text())
        _policy_cache[manifest] = PolicyEngine.from_dict(data)
    return _policy_cache[manifest]


def _replay_record(record: dict[str, Any]) -> dict[str, Any]:
    """Re-evaluate one trace record through the current policy engine.

    When the original scenario fixture is found, re-runs with full original
    arguments (true replay).  Falls back to a tool×channel verdict-level
    replay when the fixture is unavailable.
    """
    manifest = record.get("manifest", "email-safe-assistant")
    tool = record.get("tool", "unknown")
    channel = record.get("channel", "user")

    # Try to replay with full original args via the scenario fixture
    scenario = _get_scenario(record.get("scenario_id", ""))

    start = time.perf_counter()
    try:
        engine = _load_policy(manifest)

        if scenario is not None:
            # Full replay: re-run the original scenario
            from run_scenarios import evaluate_scenario
            result = evaluate_scenario(scenario)
            latency_ms = (time.perf_counter() - start) * 1000
            replayed_outcome = result.outcome
            matched_rule = result.matched_rule or "(default deny)"
            reason_chain = [{"check": "policy", "result": result.outcome, "detail": result.reason or ""}]
            error = result.error or ""
        else:
            # Fallback: verdict-level replay (tool × channel, no args)
            provenance = _CHANNEL_PROVENANCE.get(channel, ProvenanceClass.user_declared)
            ref = ValueRef("arg_0", "", provenance)
            call = ToolCall(tool=tool, args={"_": ref})
            evaluation = engine.evaluate(call, {"arg_0": ref})
            latency_ms = (time.perf_counter() - start) * 1000
            replayed_outcome = _VERDICT_MAP.get(evaluation.verdict.value, evaluation.verdict.value)
            matched_rule = evaluation.matched_rule or "(default deny)"
            reason_chain = [{"check": "policy", "result": evaluation.verdict.value, "detail": evaluation.reason or ""}]
            error = ""
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        replayed_outcome = "error"
        matched_rule = ""
        reason_chain = []
        error = str(exc)

    recorded_outcome = record.get("outcome", "")
    deterministic = (replayed_outcome == recorded_outcome) and not error

    return {
        "scenario_id": record.get("scenario_id", "?"),
        "scenario_class": record.get("scenario_class", "?"),
        "manifest": manifest,
        "tool": tool,
        "channel": channel,
        "recorded_outcome": recorded_outcome,
        "replayed_outcome": replayed_outcome,
        "matched_rule": matched_rule,
        "reason_chain": reason_chain,
        "deterministic": deterministic,
        "latency_ms": round(latency_ms, 4),
        "error": error,
    }


def _load_trace(path: Path) -> list[dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _print_walkthrough(record: dict, replay: dict) -> None:
    sid = record.get("scenario_id", "?")
    cls = record.get("scenario_class", "?")
    tool = record.get("tool", "?")
    channel = record.get("channel", "?")
    manifest = replay.get("manifest", "?")
    recorded = replay.get("recorded_outcome", "?")
    replayed = replay.get("replayed_outcome", "?")
    det = replay.get("deterministic", False)
    error = replay.get("error", "")

    print(f"\n{'─' * 62}")
    print(f"{_b('Scenario:')} {_c(sid)}  [{cls}]")
    print(f"  Manifest: {manifest}")
    print(f"  Tool:     {tool}  via  {channel}")
    print()
    print(f"  {_b('Policy evaluation chain:')}")
    for step in replay.get("reason_chain", []):
        symbol = _g("✓") if step["result"] == "pass" else (_d("!") if step["result"] == "escalate" else _r("✗"))
        print(f"    {symbol} [{step['check']}] {step['result'].upper()}: {_d(step['detail'])}")
    if error:
        print(f"    {_r('ERROR')}: {error}")

    recorded_col = _g(recorded) if recorded == replayed else _r(recorded)
    replayed_col = _g(replayed) if recorded == replayed else _r(replayed)
    print()
    print(f"  Recorded outcome:  {recorded_col}")
    print(f"  Replayed outcome:  {replayed_col}")
    print(f"  Deterministic:     {'YES ✓' if det else _r('NO — DRIFT DETECTED ✗')}")


def _print_cycle_explanation(trace_path: Path) -> None:
    print(f"\n{_b('Design → Compile → Deploy → Learn → Redesign')}")
    print(_d("─" * 62))
    print(f"  {_b('Design:')}   Author a World Manifest rule in manifests/ or policies/")
    print(f"  {_b('Compile:')}  run_scenarios.py evaluates all scenarios → trace JSONL")
    print(f"  {_b('Deploy:')}   Manifest is active; gateway enforces compiled policy")
    print(f"  {_b('Learn:')}    Inspect the trace below — each verdict is explained")
    print(f"  {_b('Redesign:')} Edit the manifest, re-run, replay to confirm no drift")
    print(f"\n  Trace: {_c(trace_path.name)}")
    print(f"  Re-run: {_d('python _research/benchmarks/run_scenarios.py')}")
    print(f"  Replay: {_d('python _research/benchmarks/replay.py --walkthrough')}")
    print()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Replay a benchmark trace and check determinism")
    parser.add_argument("--trace", default=None, help="Path to trace JSONL (default: latest)")
    parser.add_argument("--walkthrough", action="store_true",
                        help="Print step-by-step explanation and cycle walkthrough")
    args = parser.parse_args(argv)

    if args.trace:
        trace_path = Path(args.trace)
    else:
        files = sorted(TRACES_DIR.glob("run-*.jsonl"))
        if not files:
            print("No trace files found. Run run_scenarios.py first.", file=sys.stderr)
            return 1
        trace_path = files[-1]

    records = _load_trace(trace_path)
    if not records:
        print("Trace is empty.", file=sys.stderr)
        return 1

    if args.walkthrough:
        _print_cycle_explanation(trace_path)

    replays = [_replay_record(r) for r in records]
    all_deterministic = all(r["deterministic"] for r in replays)

    if args.walkthrough:
        for record, replay in zip(records, replays):
            _print_walkthrough(record, replay)
    else:
        for record, replay in zip(records, replays):
            det = replay["deterministic"]
            status = _g("OK  ") if det else _r("DRIFT")
            print(f"  [{status}] {replay['scenario_id']}: "
                  f"{replay['recorded_outcome']} → {replay['replayed_outcome']}")

    n = len(replays)
    det_count = sum(1 for r in replays if r["deterministic"])

    print()
    if all_deterministic:
        print(_g(f"✓ Determinism check PASSED — {det_count}/{n} outcomes stable"))
    else:
        print(_r(f"✗ Determinism check FAILED — {det_count}/{n} stable, {n - det_count} drifted"))

    print(_d(f"  Trace: {trace_path.name}  |  Replayed {n} scenarios"))

    return 0 if all_deterministic else 1


if __name__ == "__main__":
    sys.exit(main())
