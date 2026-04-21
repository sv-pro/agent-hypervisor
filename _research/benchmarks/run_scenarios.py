"""
run_scenarios.py — Scenario runner using the current PolicyEngine API.

Evaluates every scenario fixture in benchmarks/scenarios/ against its declared
manifest policy (from benchmarks/policies/), producing a structured report.

Usage:
    python _research/benchmarks/run_scenarios.py [--class attack|safe|ambiguous|all]
    PYTHONPATH=src/agent_hypervisor python _research/benchmarks/run_scenarios.py

Output:
    Writes a markdown report to _research/benchmarks/reports/ and prints a summary.
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

_HERE = Path(__file__).parent
REPO_ROOT = _HERE.parent.parent
SRC_DIR = REPO_ROOT / "src" / "agent_hypervisor"

for p in (str(REPO_ROOT / "src"), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

SCENARIOS_DIR = _HERE / "scenarios"
POLICIES_DIR = _HERE / "policies"
REPORTS_DIR = _HERE / "reports"
TRACES_DIR = _HERE / "traces"

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

import yaml
from hypervisor.policy_engine import PolicyEngine
from hypervisor.models import ToolCall, ValueRef, ProvenanceClass

# ---------------------------------------------------------------------------
# Channel → ProvenanceClass
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

# Verdict string mapping: RuleVerdict value → scenario expected_outcome string
_VERDICT_MAP = {
    "allow": "allow",
    "deny":  "deny",
    "ask":   "require_approval",
}


def channel_to_provenance(channel: str) -> ProvenanceClass:
    return _CHANNEL_PROVENANCE.get(channel, ProvenanceClass.user_declared)


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_class: str
    manifest: str
    tool: str
    channel: str
    outcome: str
    expected_outcome: str
    verdict_match: bool
    matched_rule: str
    reason: str
    latency_ms: float
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Policy loader (cached per manifest name)
# ---------------------------------------------------------------------------

_policy_cache: dict[str, PolicyEngine] = {}


def load_policy(manifest: str) -> PolicyEngine:
    if manifest not in _policy_cache:
        policy_file = POLICIES_DIR / f"{manifest}.yaml"
        if policy_file.exists():
            data = yaml.safe_load(policy_file.read_text())
            _policy_cache[manifest] = PolicyEngine.from_dict(data)
        else:
            # Fall back to the default runtime policy (deny-heavy)
            default = REPO_ROOT / "src" / "agent_hypervisor" / "runtime" / "configs" / "default_policy.yaml"
            data = yaml.safe_load(default.read_text())
            _policy_cache[manifest] = PolicyEngine.from_dict(data)
    return _policy_cache[manifest]


# ---------------------------------------------------------------------------
# Build ToolCall from scenario step
# ---------------------------------------------------------------------------

def build_tool_call(tool: str, args: dict[str, Any], provenance: ProvenanceClass) -> tuple[ToolCall, dict[str, ValueRef]]:
    registry: dict[str, ValueRef] = {}
    call_args: dict[str, ValueRef] = {}
    for i, (key, val) in enumerate(args.items()):
        ref_id = f"arg_{i}_{key}"
        # Lists become a single comma-joined string ValueRef
        value = ", ".join(val) if isinstance(val, list) else val
        ref = ValueRef(ref_id, value, provenance)
        registry[ref_id] = ref
        call_args[key] = ref
    call = ToolCall(tool=tool, args=call_args)
    return call, registry


# ---------------------------------------------------------------------------
# Evaluate a single scenario
# ---------------------------------------------------------------------------

def evaluate_scenario(scenario: dict) -> ScenarioResult:
    manifest = scenario.get("manifest", "email-safe-assistant")
    channel = scenario.get("channel", "user")
    provenance = channel_to_provenance(channel)

    # For multi-step scenarios use the last step (it carries expected_final_outcome)
    if "steps" in scenario:
        last = scenario["steps"][-1]
        tool = last.get("tool", "unknown")
        args = last.get("args", {})
        step_channel = last.get("channel", channel)
        provenance = channel_to_provenance(step_channel)
        expected = scenario.get("expected_final_outcome", last.get("expected_outcome", "deny"))
    else:
        intent = scenario.get("intent", {})
        tool = intent.get("tool", "unknown")
        args = intent.get("args", {})
        expected = scenario.get("expected_outcome", "deny")

    start = time.perf_counter()
    try:
        engine = load_policy(manifest)
        call, registry = build_tool_call(tool, args, provenance)
        evaluation = engine.evaluate(call, registry)
        latency_ms = (time.perf_counter() - start) * 1000

        outcome = _VERDICT_MAP.get(evaluation.verdict.value, evaluation.verdict.value)
        matched_rule = evaluation.matched_rule or "(default deny)"
        reason = evaluation.reason
        error = ""
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        outcome = f"error"
        matched_rule = ""
        reason = str(exc)
        error = str(exc)

    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        scenario_class=scenario["class"],
        manifest=manifest,
        tool=tool,
        channel=channel,
        outcome=outcome,
        expected_outcome=expected,
        verdict_match=(outcome == expected),
        matched_rule=matched_rule,
        reason=reason,
        latency_ms=latency_ms,
        error=error,
    )


# ---------------------------------------------------------------------------
# Load scenarios
# ---------------------------------------------------------------------------

def load_scenarios(class_filter: str = "all") -> list[dict]:
    scenarios = []
    for json_file in sorted(SCENARIOS_DIR.rglob("*.json")):
        if json_file.name == "taxonomy.json":
            continue
        try:
            data = json.loads(json_file.read_text())
            if isinstance(data, list):
                scenarios.extend(data)
            elif "scenario_id" in data:
                scenarios.append(data)
        except Exception as exc:
            print(f"Warning: could not load {json_file}: {exc}", file=sys.stderr)
    if class_filter != "all":
        scenarios = [s for s in scenarios if s.get("class") == class_filter]
    return scenarios


# ---------------------------------------------------------------------------
# Generate report
# ---------------------------------------------------------------------------

def generate_report(results: list[ScenarioResult], trace_file: str) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.verdict_match)
    latencies = [r.latency_ms for r in results if not r.error]
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

    by_class: dict[str, list] = {"attack": [], "safe": [], "ambiguous": []}
    for r in results:
        by_class.setdefault(r.scenario_class, []).append(r)

    attack = by_class["attack"]
    safe = by_class["safe"]
    ambiguous = by_class["ambiguous"]

    attack_contained = sum(1 for r in attack if r.verdict_match)
    safe_allowed = sum(1 for r in safe if r.verdict_match)
    ambiguous_escalated = sum(1 for r in ambiguous if r.verdict_match)

    attack_containment = attack_contained / len(attack) * 100 if attack else 0.0
    false_deny = (len(safe) - safe_allowed) / len(safe) * 100 if safe else 0.0
    task_completion = (safe_allowed + ambiguous_escalated) / (len(safe) + len(ambiguous)) * 100 if (safe or ambiguous) else 0.0
    det_coverage = sum(1 for r in results if not r.error) / total * 100 if total else 0.0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Agent Hypervisor — Benchmark Report",
        f"",
        f"**Generated:** {now}  ",
        f"**Trace:** `{trace_file}`",
        f"",
        f"## Scenario coverage",
        f"",
        f"| Class | Count |",
        f"|-------|-------|",
        f"| attack | {len(attack)} |",
        f"| safe | {len(safe)} |",
        f"| ambiguous | {len(ambiguous)} |",
        f"| **total** | **{total}** |",
        f"",
        f"## Security metrics",
        f"",
        f"| Metric | Value | Interpretation |",
        f"|--------|-------|----------------|",
        f"| Attack containment rate | {attack_containment:.1f}% | Fraction of attack scenarios correctly denied |",
        f"| False deny rate | {false_deny:.1f}% | Safe scenarios incorrectly blocked (lower is better) |",
        f"",
        f"## Utility metrics",
        f"",
        f"| Metric | Value | Interpretation |",
        f"|--------|-------|----------------|",
        f"| Task completion rate | {task_completion:.1f}% | Safe+ambiguous scenarios reaching allow or require_approval |",
        f"| Deterministic coverage | {det_coverage:.1f}% | Scenarios with concrete verdict (no errors) |",
        f"| Mean latency | {mean_lat:.3f} ms | Policy evaluation latency per scenario |",
        f"",
        f"## Per-scenario results",
        f"",
        f"| ID | Class | Tool | Channel | Outcome | Expected | Match | Rule |",
        f"|----|-------|------|---------|---------|----------|-------|------|",
    ]
    for r in results:
        status = "✅" if r.verdict_match else "❌"
        lines.append(
            f"| `{r.scenario_id}` | {r.scenario_class} | `{r.tool}` | {r.channel} "
            f"| {r.outcome} | {r.expected_outcome} | {status} | `{r.matched_rule}` |"
        )

    overall = "✅ All scenarios matched" if passed == total else f"⚠️ {total - passed} scenario(s) did not match expected outcome"
    lines += [
        f"",
        f"## Summary",
        f"",
        f"**{passed}/{total} scenarios matched expected outcome.** {overall}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run agent hypervisor scenario suite")
    parser.add_argument("--class", dest="scenario_class", default="all",
                        choices=["all", "attack", "safe", "ambiguous"])
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    scenarios = load_scenarios(args.scenario_class)
    if not scenarios:
        print("No scenarios found.", file=sys.stderr)
        return 1

    results = [evaluate_scenario(s) for s in scenarios]

    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    trace_file = f"run-{ts}.jsonl"
    (TRACES_DIR / trace_file).write_text(
        "\n".join(json.dumps(r.to_dict()) for r in results) + "\n"
    )

    report = generate_report(results, trace_file)
    report_path = REPORTS_DIR / f"report-{ts}.md"
    report_path.write_text(report)

    if not args.quiet:
        total = len(results)
        passed = sum(1 for r in results if r.verdict_match)
        for r in results:
            status = "OK  " if r.verdict_match else "FAIL"
            print(f"  [{status}] {r.scenario_id} → {r.outcome} (expected: {r.expected_outcome})")
        print(f"\n{passed}/{total} matched  |  report: {report_path}")

    return 0 if all(r.verdict_match for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
