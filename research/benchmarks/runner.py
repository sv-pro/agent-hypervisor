"""
benchmarks/runner.py — Baseline benchmark runner for the agent hypervisor.

Runs every scenario in benchmarks/scenarios/ through both:
  - baseline:    direct tool invocation with no policy (the "without hypervisor" path)
  - hypervisor:  full 5-check policy engine + MCP gateway (the "with hypervisor" path)

Outputs a structured result record per scenario, written to benchmarks/traces/.

Usage:
    python benchmarks/runner.py [--scenarios <dir>] [--output <dir>] [--mode baseline|hypervisor|both]

The same scenario fixture produces two result records — one per mode — so the
difference in outcome is directly comparable.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"
COMPILED_DIR = REPO_ROOT / "manifests" / "examples" / "compiled"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from boundary.semantic_event import SemanticEventFactory, TrustLevel
from boundary.intent_proposal import IntentProposal, IntentProposalBuilder
from policy.engine import PolicyEngine, Verdict
from gateway.proxy import MCPGateway, make_demo_registry


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_class: str
    mode: str              # "baseline" | "hypervisor"
    manifest: str
    tool: str
    channel: str
    trust_level: str
    taint: bool
    outcome: str           # final outcome string
    expected_outcome: str
    verdict_match: bool    # True if outcome matched expected
    denial_reason: str
    latency_ms: float
    reason_chain: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Channel → factory method mapping
# ---------------------------------------------------------------------------

def make_event(factory: SemanticEventFactory, channel: str, raw: str):
    if channel == "user":
        return factory.from_user(raw)
    elif channel == "email":
        return factory.from_email(raw)
    elif channel == "web":
        return factory.from_web(raw)
    elif channel == "file":
        return factory.from_file(raw)
    elif channel == "mcp":
        return factory.from_mcp(raw, tool_name="unknown")
    elif channel == "agent":
        return factory.from_agent(raw, agent_id="unknown")
    else:
        return factory.from_user(raw)


# ---------------------------------------------------------------------------
# Baseline runner (no hypervisor)
# ---------------------------------------------------------------------------

def run_baseline(scenario: dict) -> ScenarioResult:
    """
    Baseline: agent calls the tool directly with no policy enforcement.
    Every call succeeds with outcome 'executed' (no boundary).
    This is the unsafe reference point — demonstrates what happens without the hypervisor.
    """
    intent = scenario.get("intent", {})
    if not intent and "steps" in scenario:
        intent = scenario["steps"][-1]  # use last step for multi-step scenarios

    start = time.perf_counter()
    # Baseline has no policy — everything executes
    outcome = "executed"
    denial_reason = ""
    latency_ms = (time.perf_counter() - start) * 1000

    # For multi-step scenarios, use expected_final_outcome
    expected = scenario.get("expected_final_outcome") or scenario.get("expected_outcome", "allow")
    # Baseline always "executes" — so it matches only if expected is "allow"
    verdict_match = (expected == "allow")

    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        scenario_class=scenario["class"],
        mode="baseline",
        manifest=scenario.get("manifest", "unknown"),
        tool=intent.get("tool", "unknown"),
        channel=scenario.get("channel", "user"),
        trust_level="TRUSTED",  # baseline has no trust model
        taint=False,             # baseline ignores taint
        outcome=outcome,
        expected_outcome=expected,
        verdict_match=verdict_match,
        denial_reason=denial_reason,
        latency_ms=latency_ms,
        reason_chain=[],
    )


# ---------------------------------------------------------------------------
# Hypervisor runner (full policy engine + gateway)
# ---------------------------------------------------------------------------

def run_hypervisor(scenario: dict) -> ScenarioResult:
    """
    Hypervisor mode: full 5-check policy engine + MCP gateway.
    Produces a PolicyDecision with verdict and reason_chain.
    """
    manifest_name = scenario.get("manifest", "email-safe-assistant")
    compiled_dir = COMPILED_DIR / manifest_name
    factory = SemanticEventFactory()

    channel = scenario.get("channel", "user")
    raw_input = scenario.get("input", "")

    # For multi-step scenarios, use the last step
    intent_data = scenario.get("intent", {})
    if not intent_data and "steps" in scenario:
        intent_data = scenario["steps"][-1]

    tool = intent_data.get("tool", "unknown")
    args = intent_data.get("args", {})

    # Override channel/taint/trust for specific steps if provided
    if "steps" in scenario and len(scenario["steps"]) > 1:
        last_step = scenario["steps"][-1]
        channel = last_step.get("channel", channel)

    start = time.perf_counter()

    try:
        engine = PolicyEngine.from_compiled_dir(compiled_dir)
        event = make_event(factory, channel, raw_input)

        proposal = IntentProposalBuilder(event).build(tool, args)
        decision = engine.evaluate(proposal)

        latency_ms = (time.perf_counter() - start) * 1000

        # Map verdict to outcome string
        verdict_to_outcome = {
            Verdict.ALLOW: "allow",
            Verdict.DENY: "deny",
            Verdict.REQUIRE_APPROVAL: "require_approval",
            Verdict.SIMULATE: "simulate",
        }
        outcome = verdict_to_outcome.get(decision.verdict, decision.verdict)
        reason_chain = [
            {"check": s.check, "result": s.result, "detail": s.detail}
            for s in decision.reason_chain
        ]
        denial_reason = decision.final_reason if decision.verdict == Verdict.DENY else ""
        trust_level = proposal.trust_level
        taint = proposal.taint

    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        outcome = f"error: {exc}"
        reason_chain = []
        denial_reason = str(exc)
        trust_level = "unknown"
        taint = False

    # For multi-step scenarios, use expected_final_outcome
    expected = scenario.get("expected_final_outcome") or scenario.get("expected_outcome", "allow")
    verdict_match = (outcome == expected)

    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        scenario_class=scenario["class"],
        mode="hypervisor",
        manifest=manifest_name,
        tool=tool,
        channel=channel,
        trust_level=trust_level,
        taint=taint,
        outcome=outcome,
        expected_outcome=expected,
        verdict_match=verdict_match,
        denial_reason=denial_reason,
        latency_ms=latency_ms,
        reason_chain=reason_chain,
    )


# ---------------------------------------------------------------------------
# Load scenarios
# ---------------------------------------------------------------------------

def load_scenarios(scenarios_dir: Path) -> list[dict]:
    scenarios = []
    for json_file in sorted(scenarios_dir.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text())
            # Skip the taxonomy index if it exists
            if isinstance(data, list):
                scenarios.extend(data)
            elif "scenario_id" in data:
                scenarios.append(data)
        except Exception as exc:
            print(f"Warning: could not load {json_file}: {exc}", file=sys.stderr)
    return scenarios


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------

def run_all(
    scenarios_dir: Path,
    output_dir: Path,
    mode: str = "both",
) -> list[ScenarioResult]:
    scenarios = load_scenarios(scenarios_dir)
    results: list[ScenarioResult] = []

    for sc in scenarios:
        if mode in ("baseline", "both"):
            results.append(run_baseline(sc))
        if mode in ("hypervisor", "both"):
            results.append(run_hypervisor(sc))

    # Save traces
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_file = output_dir / f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.jsonl"
    with open(trace_file, "w") as f:
        for r in results:
            f.write(json.dumps(r.to_dict()) + "\n")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run hypervisor benchmark scenarios")
    parser.add_argument("--scenarios", default=str(REPO_ROOT / "benchmarks/scenarios"),
                        help="Directory containing scenario JSON fixtures")
    parser.add_argument("--output", default=str(REPO_ROOT / "benchmarks/traces"),
                        help="Directory to write run trace JSONL")
    parser.add_argument("--mode", default="both", choices=["baseline", "hypervisor", "both"],
                        help="Which mode to run")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    results = run_all(
        scenarios_dir=Path(args.scenarios),
        output_dir=Path(args.output),
        mode=args.mode,
    )

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.verdict_match)
    # Baseline failures on attack/ambiguous scenarios are expected — baseline has no policy.
    # Only count hypervisor failures as real failures.
    hypervisor_results = [r for r in results if r.mode == "hypervisor"]
    hypervisor_failed = sum(1 for r in hypervisor_results if not r.verdict_match)

    if not args.quiet:
        print(f"\nBenchmark run: {total} results ({passed} matched)\n")
        for r in results:
            status = "OK" if r.verdict_match else "FAIL"
            print(f"  [{status}] {r.scenario_id} ({r.mode}) → {r.outcome} (expected: {r.expected_outcome})")
        hv_total = len(hypervisor_results)
        hv_pass = hv_total - hypervisor_failed
        print(f"\nHypervisor: {hv_pass}/{hv_total} correct")
        baseline_results = [r for r in results if r.mode == "baseline"]
        bl_pass = sum(1 for r in baseline_results if r.verdict_match)
        print(f"Baseline:   {bl_pass}/{len(baseline_results)} correct (attacks succeed in baseline — expected)")

    return 0 if hypervisor_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
