"""
benchmarks/replay.py — Replay any recorded trace through the hypervisor.

Given a JSONL trace from benchmarks/runner.py, replay each scenario through
the current policy engine and compare the replayed outcome with the recorded
outcome. This verifies that:

  1. The system is deterministic: same input → same outcome across runs.
  2. Manifest/compiler changes can be validated against a known-good baseline.

Usage:
    python benchmarks/replay.py --trace benchmarks/traces/<run>.jsonl
    python benchmarks/replay.py  # replays latest trace
    python benchmarks/replay.py --walkthrough  # step-by-step explanation of each decision
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from boundary.semantic_event import SemanticEventFactory
from boundary.intent_proposal import IntentProposal
from policy.engine import PolicyEngine, Verdict


COMPILED_DIR = REPO_ROOT / "manifests" / "examples" / "compiled"


def load_trace(path: Path) -> list[dict[str, Any]]:
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def replay_result(record: dict) -> dict[str, Any]:
    """Replay one result record through the current policy engine."""
    if record["mode"] != "hypervisor":
        return {"skipped": True, "reason": "baseline records are not replayed"}

    manifest = record.get("manifest", "email-safe-assistant")
    compiled_dir = COMPILED_DIR / manifest

    try:
        engine = PolicyEngine.from_compiled_dir(compiled_dir)
        proposal = IntentProposal(
            tool=record["tool"],
            args={},  # args not stored in result record; replay validates verdict only
            taint=record["taint"],
            trust_level=record["trust_level"],
        )
        decision = engine.evaluate(proposal)

        verdict_map = {
            Verdict.ALLOW: "allow",
            Verdict.DENY: "deny",
            Verdict.REQUIRE_APPROVAL: "require_approval",
            Verdict.SIMULATE: "simulate",
        }
        replayed_outcome = verdict_map.get(decision.verdict, decision.verdict)
        recorded_outcome = record["outcome"]
        matches = (replayed_outcome == recorded_outcome)

        return {
            "scenario_id": record["scenario_id"],
            "mode": record["mode"],
            "recorded_outcome": recorded_outcome,
            "replayed_outcome": replayed_outcome,
            "deterministic": matches,
            "reason_chain": [
                {"check": s.check, "result": s.result, "detail": s.detail}
                for s in decision.reason_chain
            ],
        }
    except Exception as exc:
        return {
            "scenario_id": record.get("scenario_id", "unknown"),
            "error": str(exc),
            "deterministic": False,
        }


def walkthrough_decision(record: dict, replay: dict) -> str:
    """Format a step-by-step walkthrough of one scenario decision."""
    lines = [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Scenario: {record['scenario_id']}",
        f"Class:    {record['scenario_class']}",
        f"Manifest: {record['manifest']}",
        f"Channel:  {record['channel']} → trust_level={record['trust_level']}, taint={record['taint']}",
        f"Tool:     {record['tool']}",
        f"",
        f"Policy evaluation chain:",
    ]
    for step in replay.get("reason_chain", []):
        symbol = "✓" if step["result"] == "pass" else ("!" if step["result"] == "escalate" else "✗")
        lines.append(f"  {symbol} [{step['check']}] {step['result'].upper()}: {step['detail']}")

    recorded = replay.get("recorded_outcome", "?")
    replayed = replay.get("replayed_outcome", "?")
    det = replay.get("deterministic", False)

    lines += [
        f"",
        f"Recorded outcome:  {recorded}",
        f"Replayed outcome:  {replayed}",
        f"Deterministic:     {'YES ✓' if det else 'NO — DRIFT DETECTED ✗'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Replay a benchmark trace through the hypervisor")
    parser.add_argument("--trace", default=None, help="Path to trace JSONL")
    parser.add_argument("--walkthrough", action="store_true",
                        help="Print step-by-step explanation for each scenario")
    args = parser.parse_args(argv)

    traces_dir = REPO_ROOT / "benchmarks" / "traces"
    if args.trace:
        trace_path = Path(args.trace)
    else:
        files = sorted(traces_dir.glob("run-*.jsonl"))
        if not files:
            print("No trace files found. Run benchmarks/runner.py first.", file=sys.stderr)
            return 1
        trace_path = files[-1]

    print(f"Replaying trace: {trace_path.name}\n")

    records = load_trace(trace_path)
    hypervisor_records = [r for r in records if r.get("mode") == "hypervisor"]

    replays = []
    all_deterministic = True

    for record in hypervisor_records:
        replay = replay_result(record)
        replays.append((record, replay))
        if not replay.get("deterministic", False):
            all_deterministic = False

        if args.walkthrough:
            print(walkthrough_decision(record, replay))
        else:
            status = "OK" if replay.get("deterministic") else "DRIFT"
            print(f"  [{status}] {record['scenario_id']}: {replay.get('recorded_outcome')} → {replay.get('replayed_outcome')}")

    print(f"\nDeterminism check: {'PASSED — all outcomes stable' if all_deterministic else 'FAILED — some outcomes drifted'}")
    print(f"Replayed {len(replays)} hypervisor scenarios from {trace_path.name}")

    return 0 if all_deterministic else 1


if __name__ == "__main__":
    sys.exit(main())
