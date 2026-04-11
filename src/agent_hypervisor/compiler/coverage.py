"""coverage.py — Manifest action/rule coverage analysis.

Given a manifest and one or more execution traces (or simulation results),
identifies which manifest actions were exercised and which were never triggered.

Coverage dimensions:
  - Action coverage: which declared actions were hit at least once
  - Decision coverage: per-action breakdown of outcomes (allow/deny/approval)
  - Dead rules: actions declared in the manifest but never reached in any trace

Usage:
    from compiler.coverage import analyze_coverage, CoverageReport
    report = analyze_coverage(manifest_dict, [trace1, trace2])
    for dead in report.uncovered_actions:
        print(f"Never triggered: {dead}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .observe import ExecutionTrace
from .simulate import ALLOW, DENY_ABSENT, DENY_POLICY, REQUIRE_APPROVAL
from .simulate import SimulationResult, simulate_trace


@dataclass
class ActionCoverage:
    """Coverage data for a single manifest action."""

    action_name: str
    hit_count: int = 0
    allow_count: int = 0
    deny_policy_count: int = 0
    deny_absent_count: int = 0
    approval_count: int = 0

    @property
    def covered(self) -> bool:
        return self.hit_count > 0

    @property
    def only_denied(self) -> bool:
        """True if action was reached but always denied — may indicate over-restriction."""
        return self.hit_count > 0 and self.allow_count == 0 and self.approval_count == 0


@dataclass
class CoverageReport:
    """Coverage report: per-action hit counts and unreachable actions."""

    manifest_name: str
    total_traces: int
    total_calls: int
    action_coverage: dict[str, ActionCoverage] = field(default_factory=dict)

    @property
    def covered_actions(self) -> list[str]:
        return sorted(name for name, ac in self.action_coverage.items() if ac.covered)

    @property
    def uncovered_actions(self) -> list[str]:
        """Actions declared in the manifest but never triggered in any trace."""
        return sorted(name for name, ac in self.action_coverage.items() if not ac.covered)

    @property
    def coverage_pct(self) -> float:
        total = len(self.action_coverage)
        if total == 0:
            return 100.0
        return 100.0 * len(self.covered_actions) / total

    @property
    def over_restricted_actions(self) -> list[str]:
        """Actions that were triggered but always denied — candidates for tuning."""
        return sorted(
            name for name, ac in self.action_coverage.items() if ac.only_denied
        )

    def summary(self) -> str:
        covered = len(self.covered_actions)
        total = len(self.action_coverage)
        uncovered = len(self.uncovered_actions)
        pct = self.coverage_pct
        return (
            f"{covered}/{total} actions covered ({pct:.0f}%) — "
            f"{uncovered} never triggered"
        )


def analyze_coverage(
    manifest: dict[str, Any],
    traces: list[ExecutionTrace],
) -> CoverageReport:
    """Analyze which manifest actions were exercised across all traces.

    Args:
        manifest: Validated v2 manifest dict.
        traces:   List of ExecutionTrace objects to replay.

    Returns:
        CoverageReport with per-action hit counts and uncovered actions.
    """
    actions = manifest.get("actions", {})
    if isinstance(actions, list):
        actions = {a["name"]: a for a in actions}

    manifest_name = manifest.get("manifest", {}).get("name", "unknown")
    report = CoverageReport(
        manifest_name=manifest_name,
        total_traces=len(traces),
        total_calls=sum(len(t.calls) for t in traces),
        action_coverage={
            name: ActionCoverage(action_name=name) for name in actions
        },
    )

    for trace in traces:
        sim = simulate_trace(trace, manifest)
        _accumulate(sim, report)

    return report


def analyze_coverage_from_results(
    manifest: dict[str, Any],
    sim_results: list[SimulationResult],
) -> CoverageReport:
    """Analyze coverage from pre-computed SimulationResult objects.

    Use this when you already have simulation results and don't want to
    re-run the simulation.
    """
    actions = manifest.get("actions", {})
    if isinstance(actions, list):
        actions = {a["name"]: a for a in actions}

    manifest_name = manifest.get("manifest", {}).get("name", "unknown")
    report = CoverageReport(
        manifest_name=manifest_name,
        total_traces=len(sim_results),
        total_calls=sum(len(r.decisions) for r in sim_results),
        action_coverage={
            name: ActionCoverage(action_name=name) for name in actions
        },
    )

    for sim in sim_results:
        _accumulate(sim, report)

    return report


def _accumulate(sim: SimulationResult, report: CoverageReport) -> None:
    """Add decisions from a SimulationResult into the coverage report."""
    for decision in sim.decisions:
        action = decision.action_name
        if not action or action not in report.action_coverage:
            continue
        ac = report.action_coverage[action]
        ac.hit_count += 1
        if decision.outcome == ALLOW:
            ac.allow_count += 1
        elif decision.outcome == DENY_POLICY:
            ac.deny_policy_count += 1
        elif decision.outcome == DENY_ABSENT:
            ac.deny_absent_count += 1
        elif decision.outcome == REQUIRE_APPROVAL:
            ac.approval_count += 1
