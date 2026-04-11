"""Tests for v0.3 design-time toolchain: simulate, differ, coverage, tune, test_runner.

Coverage:
  - simulate: trace replay, decision table correctness, taint propagation
  - differ: added/removed/changed actions, channels, world-model sections
  - coverage: hit counting, uncovered/over-restricted detection
  - tune: suggestions for DENY_ABSENT, DENY_POLICY (taint), REQUIRE_APPROVAL
  - test_runner: scenario pass/fail, validation, expect aliases
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_hypervisor.compiler.coverage import analyze_coverage, analyze_coverage_from_results
from agent_hypervisor.compiler.differ import ADDED, CHANGED, REMOVED, diff_manifests
from agent_hypervisor.compiler.observe import ExecutionTrace, ToolCall
from agent_hypervisor.compiler.simulate import (
    ALLOW,
    DENY_ABSENT,
    DENY_POLICY,
    REQUIRE_APPROVAL,
    SimDecision,
    simulate_trace,
    simulate_steps,
)
from agent_hypervisor.compiler.test_runner import (
    ScenarioValidationError,
    TestReport,
    run_scenarios,
    validate_scenario_file,
)
from agent_hypervisor.compiler.tune import (
    ADD_ACTION,
    ADD_PREDICATE,
    CHANGE_FIELD,
    RELAX_TAINT,
    suggest_edits,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_manifest(**overrides) -> dict:
    """Minimal valid v2 manifest dict."""
    import copy

    base = {
        "version": "2.0",
        "manifest": {"name": "test-manifest"},
        "actions": {
            "read_email": {
                "reversible": True,
                "side_effects": ["internal_read"],
                "action_class": "read_only",
                "required_capabilities": ["read_only"],
                "requires_approval": False,
                "external_boundary": False,
                "taint_passthrough": True,
                "confirmation_class": "auto",
            },
            "send_email": {
                "reversible": False,
                "side_effects": ["external_write"],
                "action_class": "external_boundary",
                "required_capabilities": ["external_boundary"],
                "requires_approval": False,
                "external_boundary": True,
                "taint_passthrough": True,
                "confirmation_class": "soft_confirm",
            },
            "delete_file": {
                "reversible": False,
                "side_effects": ["internal_write"],
                "action_class": "irreversible_internal",
                "required_capabilities": ["approve_irreversible"],
                "requires_approval": True,
                "external_boundary": False,
                "taint_passthrough": False,
                "confirmation_class": "hard_confirm",
            },
        },
        "trust_channels": {
            "user": {"trust_level": "TRUSTED", "taint_by_default": False},
            "email": {"trust_level": "UNTRUSTED", "taint_by_default": True},
        },
        "capability_matrix": {
            "TRUSTED": ["read_only", "external_boundary", "approve_irreversible"],
            "SEMI_TRUSTED": ["read_only"],
            "UNTRUSTED": [],
        },
    }
    base.update(overrides)
    return base


def _make_trace(*calls) -> ExecutionTrace:
    """Build a trace from (tool, params, safe) tuples."""
    tc = [
        ToolCall(tool=t, params=p, safe=s)
        for t, p, s in calls
    ]
    return ExecutionTrace(workflow_id="test", calls=tc)


# ── simulate: basic decisions ─────────────────────────────────────────────────


class TestSimulate:
    def test_known_action_allowed(self):
        manifest = _make_manifest()
        trace = _make_trace(("read_email", {}, True))
        result = simulate_trace(trace, manifest)
        assert len(result.decisions) == 1
        d = result.decisions[0]
        assert d.outcome == ALLOW
        assert d.action_name == "read_email"

    def test_unknown_tool_deny_absent(self):
        manifest = _make_manifest()
        trace = _make_trace(("unknown_tool", {}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == DENY_ABSENT

    def test_tainted_input_external_boundary_deny_policy(self):
        manifest = _make_manifest()
        trace = _make_trace(("send_email", {"recipients": ["x@y.com"]}, False))
        result = simulate_trace(trace, manifest)
        d = result.decisions[0]
        assert d.outcome == DENY_POLICY
        assert d.tainted is True
        assert "external boundary" in d.reason.lower()

    def test_clean_external_boundary_allowed(self):
        manifest = _make_manifest()
        trace = _make_trace(("send_email", {"recipients": ["x@y.com"]}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == ALLOW

    def test_requires_approval_action(self):
        manifest = _make_manifest()
        trace = _make_trace(("delete_file", {"file_id": "doc-1"}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == REQUIRE_APPROVAL

    def test_missing_capability_deny_policy(self):
        manifest = _make_manifest()
        manifest["capability_matrix"]["TRUSTED"] = ["read_only"]  # remove external_boundary
        trace = _make_trace(("send_email", {}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == DENY_POLICY
        assert "capabilit" in result.decisions[0].reason.lower()

    def test_multiple_steps_decision_table(self):
        manifest = _make_manifest()
        trace = _make_trace(
            ("read_email", {}, True),          # ALLOW
            ("unknown_tool", {}, True),         # DENY_ABSENT
            ("send_email", {}, False),          # DENY_POLICY (tainted)
            ("delete_file", {}, True),          # REQUIRE_APPROVAL
        )
        result = simulate_trace(trace, manifest)
        assert len(result.decisions) == 4
        assert result.decisions[0].outcome == ALLOW
        assert result.decisions[1].outcome == DENY_ABSENT
        assert result.decisions[2].outcome == DENY_POLICY
        assert result.decisions[3].outcome == REQUIRE_APPROVAL

    def test_summary_counts(self):
        manifest = _make_manifest()
        trace = _make_trace(
            ("read_email", {}, True),
            ("unknown_tool", {}, True),
            ("send_email", {}, False),
        )
        result = simulate_trace(trace, manifest)
        assert result.allowed_count == 1
        assert result.denied_count == 2
        assert result.absent_count == 1
        assert result.policy_count == 1

    def test_simulate_steps_api(self):
        manifest = _make_manifest()
        steps = [
            {"tool": "read_email", "params": {}, "tainted": False},
            {"tool": "send_email", "params": {}, "tainted": True},
        ]
        result = simulate_steps(steps, manifest)
        assert result.decisions[0].outcome == ALLOW
        assert result.decisions[1].outcome == DENY_POLICY

    def test_predicates_resolve_tool_to_action(self):
        manifest = _make_manifest()
        manifest["predicates"] = {
            "get_email": [
                {"action": "read_email", "match": {}}
            ]
        }
        trace = _make_trace(("get_email", {}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == ALLOW
        assert result.decisions[0].action_name == "read_email"

    def test_predicate_arg_present_routing(self):
        manifest = _make_manifest()
        manifest["actions"]["send_external"] = {
            "reversible": False,
            "side_effects": ["external_write"],
            "required_capabilities": ["external_boundary"],
            "requires_approval": False,
            "external_boundary": True,
            "taint_passthrough": True,
            "confirmation_class": "auto",
        }
        manifest["actions"]["store_internal"] = {
            "reversible": True,
            "side_effects": ["internal_write"],
            "required_capabilities": ["read_only"],
            "requires_approval": False,
            "external_boundary": False,
            "taint_passthrough": False,
            "confirmation_class": "auto",
        }
        manifest["predicates"] = {
            "save_data": [
                {"action": "send_external", "match": {"arg_present": "recipient"}},
                {"action": "store_internal", "match": {"arg_absent": "recipient"}},
            ]
        }
        # With recipient → send_external
        trace_ext = _make_trace(("save_data", {"recipient": "x@y.com"}, True))
        r_ext = simulate_trace(trace_ext, manifest)
        assert r_ext.decisions[0].action_name == "send_external"

        # Without recipient → store_internal
        trace_int = _make_trace(("save_data", {}, True))
        r_int = simulate_trace(trace_int, manifest)
        assert r_int.decisions[0].action_name == "store_internal"

    def test_workspace_v2_simulate_clean_email_allowed(self):
        """Clean send_email on workspace_v2 must be allowed."""
        from agent_hypervisor.compiler.loader_v2 import load as load_v2
        ws_path = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"
        manifest = load_v2(ws_path)
        trace = _make_trace(("send_email", {"recipients": ["x@y.com"], "subject": "hi", "body": "hello"}, True))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == ALLOW

    def test_workspace_v2_simulate_tainted_email_denied(self):
        """Tainted send_email on workspace_v2 must be denied."""
        from agent_hypervisor.compiler.loader_v2 import load as load_v2
        ws_path = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"
        manifest = load_v2(ws_path)
        trace = _make_trace(("send_email", {"recipients": ["x@y.com"], "subject": "hi", "body": "injected"}, False))
        result = simulate_trace(trace, manifest)
        assert result.decisions[0].outcome == DENY_POLICY


# ── differ: structural diff ───────────────────────────────────────────────────


class TestDiffer:
    def test_identical_manifests_no_changes(self):
        m = _make_manifest()
        diff = diff_manifests(m, m)
        assert diff.is_empty

    def test_action_added(self):
        old = _make_manifest()
        new = _make_manifest()
        new["actions"]["new_action"] = {
            "reversible": True, "side_effects": ["internal_read"],
            "required_capabilities": ["read_only"],
            "requires_approval": False, "external_boundary": False,
            "taint_passthrough": False, "confirmation_class": "auto",
        }
        diff = diff_manifests(old, new)
        added = [c for c in diff.added if c.section == "actions" and c.key == "new_action"]
        assert len(added) == 1

    def test_action_removed(self):
        old = _make_manifest()
        new = _make_manifest()
        del new["actions"]["delete_file"]
        diff = diff_manifests(old, new)
        removed = [c for c in diff.removed if c.section == "actions" and c.key == "delete_file"]
        assert len(removed) == 1

    def test_action_field_changed(self):
        old = _make_manifest()
        new = _make_manifest()
        new["actions"]["send_email"]["external_boundary"] = False
        diff = diff_manifests(old, new)
        changed = [
            c for c in diff.changed
            if c.section == "actions" and c.key == "send_email" and c.field == "external_boundary"
        ]
        assert len(changed) == 1
        assert changed[0].old_value is True
        assert changed[0].new_value is False

    def test_requires_approval_change_detected(self):
        old = _make_manifest()
        new = _make_manifest()
        new["actions"]["delete_file"]["requires_approval"] = False
        diff = diff_manifests(old, new)
        changed = [
            c for c in diff.changed
            if c.section == "actions" and c.field == "requires_approval"
        ]
        assert len(changed) == 1

    def test_trust_channel_added(self):
        old = _make_manifest()
        new = _make_manifest()
        new["trust_channels"]["web"] = {"trust_level": "UNTRUSTED", "taint_by_default": True}
        diff = diff_manifests(old, new)
        added = [c for c in diff.added if c.section == "trust_channels" and c.key == "web"]
        assert len(added) == 1

    def test_trust_channel_trust_level_changed(self):
        old = _make_manifest()
        new = _make_manifest()
        new["trust_channels"]["email"]["trust_level"] = "TRUSTED"
        diff = diff_manifests(old, new)
        changed = [
            c for c in diff.changed
            if c.section == "trust_channels" and c.field == "trust_level"
        ]
        assert len(changed) == 1
        assert changed[0].old_value == "UNTRUSTED"
        assert changed[0].new_value == "TRUSTED"

    def test_capability_matrix_change(self):
        old = _make_manifest()
        new = _make_manifest()
        new["capability_matrix"]["TRUSTED"] = ["read_only"]  # stripped external_boundary
        diff = diff_manifests(old, new)
        changed = [c for c in diff.changed if c.section == "capability_matrix"]
        assert len(changed) == 1

    def test_entity_added(self):
        old = _make_manifest()
        new = _make_manifest()
        new["entities"] = {"inbox": {"type": "mailbox", "data_class": "internal"}}
        diff = diff_manifests(old, new)
        added = [c for c in diff.added if c.section == "entities"]
        assert len(added) == 1

    def test_data_class_taint_label_changed(self):
        old = _make_manifest()
        old["data_classes"] = {"pii": {"taint_label": "pii", "confirmation": "hard_confirm"}}
        new = _make_manifest()
        new["data_classes"] = {"pii": {"taint_label": "sensitive", "confirmation": "hard_confirm"}}
        diff = diff_manifests(old, new)
        changed = [
            c for c in diff.changed
            if c.section == "data_classes" and c.field == "taint_label"
        ]
        assert len(changed) == 1

    def test_summary_string(self):
        old = _make_manifest()
        new = _make_manifest()
        new["actions"]["extra"] = {
            "reversible": True, "side_effects": [],
            "required_capabilities": [], "requires_approval": False,
            "external_boundary": False, "taint_passthrough": False,
            "confirmation_class": "auto",
        }
        diff = diff_manifests(old, new)
        assert "added" in diff.summary()

    def test_changes_in_section_filter(self):
        old = _make_manifest()
        new = _make_manifest()
        new["actions"]["extra"] = {
            "reversible": True, "side_effects": [],
            "required_capabilities": [], "requires_approval": False,
            "external_boundary": False, "taint_passthrough": False,
            "confirmation_class": "auto",
        }
        new["trust_channels"]["web"] = {"trust_level": "UNTRUSTED", "taint_by_default": True}
        diff = diff_manifests(old, new)
        assert len(diff.changes_in_section("actions")) >= 1
        assert len(diff.changes_in_section("trust_channels")) >= 1
        assert all(c.section == "actions" for c in diff.changes_in_section("actions"))


# ── coverage: action hit counting ────────────────────────────────────────────


class TestCoverage:
    def test_no_traces_all_uncovered(self):
        manifest = _make_manifest()
        report = analyze_coverage(manifest, [])
        assert set(report.uncovered_actions) == set(manifest["actions"].keys())
        assert report.covered_actions == []

    def test_single_hit_covers_action(self):
        manifest = _make_manifest()
        trace = _make_trace(("read_email", {}, True))
        report = analyze_coverage(manifest, [trace])
        assert "read_email" in report.covered_actions
        assert "send_email" in report.uncovered_actions
        assert "delete_file" in report.uncovered_actions

    def test_coverage_pct(self):
        manifest = _make_manifest()  # 3 actions
        trace = _make_trace(
            ("read_email", {}, True),
            ("send_email", {}, True),
        )
        report = analyze_coverage(manifest, [trace])
        # 2 out of 3 covered
        assert report.coverage_pct == pytest.approx(100.0 * 2 / 3, abs=0.1)

    def test_denied_tool_increases_hit_count(self):
        manifest = _make_manifest()
        # delete_file always requires approval — it still gets a hit
        trace = _make_trace(("delete_file", {"file_id": "x"}, True))
        report = analyze_coverage(manifest, [trace])
        assert "delete_file" in report.covered_actions

    def test_over_restricted_actions(self):
        manifest = _make_manifest()
        # send_email with tainted input — always denied
        trace = _make_trace(("send_email", {}, False))
        report = analyze_coverage(manifest, [trace])
        # send_email is hit but always denied by policy → over-restricted candidate
        assert "send_email" in report.over_restricted_actions

    def test_multiple_traces_accumulate(self):
        manifest = _make_manifest()
        t1 = _make_trace(("read_email", {}, True))
        t2 = _make_trace(("send_email", {}, True))
        report = analyze_coverage(manifest, [t1, t2])
        assert report.total_traces == 2
        assert "read_email" in report.covered_actions
        assert "send_email" in report.covered_actions

    def test_analyze_from_simulation_results(self):
        manifest = _make_manifest()
        trace = _make_trace(("read_email", {}, True), ("delete_file", {}, True))
        sim = simulate_trace(trace, manifest)
        report = analyze_coverage_from_results(manifest, [sim])
        assert "read_email" in report.covered_actions
        assert "delete_file" in report.covered_actions

    def test_workspace_v2_coverage(self):
        """workspace_v2 should have at least 10 declared actions to cover."""
        from agent_hypervisor.compiler.loader_v2 import load as load_v2
        ws_path = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"
        manifest = load_v2(ws_path)
        report = analyze_coverage(manifest, [])
        assert len(report.action_coverage) >= 10
        assert report.coverage_pct == 0.0
        assert len(report.uncovered_actions) == len(report.action_coverage)


# ── tune: manifest edit suggestions ──────────────────────────────────────────


class TestTune:
    def test_absent_tool_suggests_add_action(self):
        manifest = _make_manifest()
        failing = [
            SimDecision(tool="unknown_tool", params={}, outcome=DENY_ABSENT,
                        reason="'unknown_tool' is not declared in this manifest")
        ]
        result = suggest_edits(manifest, failing)
        assert any(s.kind == ADD_ACTION and s.key == "unknown_tool" for s in result)

    def test_absent_tool_may_suggest_predicate_if_similar_action_exists(self):
        manifest = _make_manifest()
        # "get_email" is similar to "read_email"
        failing = [
            SimDecision(tool="get_email", params={}, outcome=DENY_ABSENT,
                        reason="'get_email' is not declared")
        ]
        result = suggest_edits(manifest, failing)
        kinds = {s.kind for s in result}
        assert ADD_ACTION in kinds or ADD_PREDICATE in kinds

    def test_tainted_external_suggests_relax_or_remove_boundary(self):
        manifest = _make_manifest()
        failing = [
            SimDecision(
                tool="send_email",
                params={},
                outcome=DENY_POLICY,
                reason="Tainted input cannot cross external boundary",
                action_name="send_email",
                tainted=True,
            )
        ]
        result = suggest_edits(manifest, failing)
        kinds = {s.kind for s in result}
        assert CHANGE_FIELD in kinds or RELAX_TAINT in kinds

    def test_requires_approval_suggests_change_field(self):
        manifest = _make_manifest()
        failing = [
            SimDecision(
                tool="delete_file",
                params={},
                outcome=REQUIRE_APPROVAL,
                reason="Action 'delete_file' requires explicit approval",
                action_name="delete_file",
            )
        ]
        result = suggest_edits(manifest, failing)
        change_suggestions = [s for s in result if s.kind == CHANGE_FIELD and s.field == "requires_approval"]
        assert len(change_suggestions) == 1
        assert change_suggestions[0].suggested_value is False

    def test_empty_failing_list_no_suggestions(self):
        manifest = _make_manifest()
        result = suggest_edits(manifest, [])
        assert len(result) == 0
        assert result.summary() == "No suggestions — decisions appear correct."

    def test_no_duplicate_suggestions(self):
        manifest = _make_manifest()
        # Two identical failures should not produce duplicate suggestions
        failing = [
            SimDecision(tool="ghost", params={}, outcome=DENY_ABSENT, reason="not declared"),
            SimDecision(tool="ghost", params={}, outcome=DENY_ABSENT, reason="not declared"),
        ]
        result = suggest_edits(manifest, failing)
        add_actions = [s for s in result if s.kind == ADD_ACTION and s.key == "ghost"]
        assert len(add_actions) == 1

    def test_yaml_patch_for_add_action(self):
        manifest = _make_manifest()
        failing = [
            SimDecision(tool="new_tool", params={}, outcome=DENY_ABSENT,
                        reason="not declared", action_name="new_tool")
        ]
        result = suggest_edits(manifest, failing)
        add = next(s for s in result if s.kind == ADD_ACTION)
        patch = add.yaml_patch()
        assert "actions:" in patch
        assert "new_tool:" in patch
        assert "TODO" in patch

    def test_missing_capability_suggests_add_capability(self):
        manifest = _make_manifest()
        manifest["capability_matrix"]["TRUSTED"] = ["read_only"]  # stripped
        failing = [
            SimDecision(
                tool="send_email",
                params={},
                outcome=DENY_POLICY,
                reason="Missing capabilities: ['external_boundary']",
                action_name="send_email",
            )
        ]
        result = suggest_edits(manifest, failing)
        cap_suggestions = [s for s in result if s.kind == "ADD_CAPABILITY"]
        assert len(cap_suggestions) >= 1


# ── test_runner: scenario harness ─────────────────────────────────────────────


class TestTestRunner:
    def _scenarios_for_manifest(self):
        return [
            {"name": "Allow: read email", "tool": "read_email", "params": {}, "expect": "allow", "tainted": False},
            {"name": "Deny: unknown tool", "tool": "ghost_tool", "params": {}, "expect": "deny", "tainted": False},
            {"name": "Deny: tainted external", "tool": "send_email", "params": {}, "expect": "deny", "tainted": True},
            {"name": "Approval: delete file", "tool": "delete_file", "params": {}, "expect": "approval", "tainted": False},
            {"name": "Allow: clean send", "tool": "send_email", "params": {}, "expect": "allow", "tainted": False},
        ]

    def test_all_correct_scenarios_pass(self):
        manifest = _make_manifest()
        report = run_scenarios(self._scenarios_for_manifest(), manifest)
        assert report.all_passed
        assert report.passed_count == report.total

    def test_wrong_expect_fails(self):
        manifest = _make_manifest()
        scenarios = [
            {"name": "Wrong: expect allow but denied", "tool": "ghost_tool", "params": {}, "expect": "allow"}
        ]
        report = run_scenarios(scenarios, manifest)
        assert report.failed_count == 1

    def test_expect_absent_vs_policy(self):
        manifest = _make_manifest()
        # DENY_ABSENT for unknown tool
        absent = [{"name": "Absent", "tool": "ghost", "params": {}, "expect": "absent"}]
        r_absent = run_scenarios(absent, manifest)
        assert r_absent.all_passed

        # DENY_POLICY for tainted external
        policy = [{"name": "Policy", "tool": "send_email", "params": {}, "expect": "policy", "tainted": True}]
        r_policy = run_scenarios(policy, manifest)
        assert r_policy.all_passed

    def test_expect_deny_matches_both_absent_and_policy(self):
        manifest = _make_manifest()
        scenarios = [
            {"name": "Deny absent", "tool": "ghost", "params": {}, "expect": "deny"},
            {"name": "Deny policy", "tool": "send_email", "params": {}, "expect": "deny", "tainted": True},
        ]
        report = run_scenarios(scenarios, manifest)
        assert report.all_passed

    def test_scenario_summary(self):
        manifest = _make_manifest()
        report = run_scenarios(self._scenarios_for_manifest(), manifest)
        summary = report.summary()
        assert str(report.total) in summary
        assert "passed" in summary.lower()

    def test_scenario_file_roundtrip(self, tmp_path):
        manifest = _make_manifest()
        scenarios = [
            {"name": "Allow read", "tool": "read_email", "params": {}, "expect": "allow"},
            {"name": "Deny ghost", "tool": "ghost", "params": {}, "expect": "deny"},
        ]
        path = tmp_path / "test_scenarios.yaml"
        path.write_text(yaml.dump({"scenarios": scenarios}))

        from agent_hypervisor.compiler.test_runner import run_scenario_file
        report = run_scenario_file(path, manifest)
        assert report.all_passed

    def test_validate_scenario_file_valid(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text(yaml.dump({"scenarios": [
            {"name": "x", "tool": "y", "params": {}, "expect": "allow"}
        ]}))
        errors = validate_scenario_file(path)
        assert errors == []

    def test_validate_scenario_file_invalid_expect(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text(yaml.dump({"scenarios": [
            {"name": "x", "tool": "y", "expect": "maybe"}
        ]}))
        errors = validate_scenario_file(path)
        assert any("maybe" in e for e in errors)

    def test_validate_scenario_file_missing_tool(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text(yaml.dump({"scenarios": [
            {"name": "x", "expect": "allow"}
        ]}))
        errors = validate_scenario_file(path)
        assert any("tool" in e for e in errors)

    def test_workspace_v2_scenario_tainted_denial(self):
        """workspace_v2: tainted send_email must fail the 'allow' expect."""
        from agent_hypervisor.compiler.loader_v2 import load as load_v2
        ws_path = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"
        manifest = load_v2(ws_path)
        scenarios = [
            # These should pass as deny
            {"name": "Tainted email denied", "tool": "send_email",
             "params": {"recipients": [], "subject": "", "body": ""}, "expect": "deny", "tainted": True},
            # This should pass as allow
            {"name": "Clean read allowed", "tool": "get_unread_emails",
             "params": {}, "expect": "allow", "tainted": False},
        ]
        report = run_scenarios(scenarios, manifest)
        assert report.all_passed


# ── integration: simulate → coverage → tune cycle ────────────────────────────


class TestSimulateCoverageTuneCycle:
    """Tests that simulate, coverage, and tune work together as a coherent toolchain."""

    def test_simulate_then_coverage(self):
        manifest = _make_manifest()
        traces = [
            _make_trace(("read_email", {}, True)),
            _make_trace(("send_email", {}, True)),
        ]
        cov = analyze_coverage(manifest, traces)
        assert "read_email" in cov.covered_actions
        assert "send_email" in cov.covered_actions
        assert "delete_file" in cov.uncovered_actions

    def test_simulate_then_tune_absent(self):
        manifest = _make_manifest()
        trace = _make_trace(("mystery_tool", {}, True))
        result = simulate_trace(trace, manifest)
        failing = result.denied_decisions()
        assert len(failing) == 1
        assert failing[0].outcome == DENY_ABSENT

        suggestions = suggest_edits(manifest, failing)
        assert len(suggestions) > 0
        assert any(s.kind == ADD_ACTION for s in suggestions)

    def test_simulate_then_tune_taint(self):
        manifest = _make_manifest()
        trace = _make_trace(("send_email", {"recipients": ["a@b.com"]}, False))
        result = simulate_trace(trace, manifest)
        failing = result.denied_decisions()

        suggestions = suggest_edits(manifest, failing)
        kinds = {s.kind for s in suggestions}
        assert CHANGE_FIELD in kinds or RELAX_TAINT in kinds

    def test_full_cycle_identify_dead_rule(self):
        """Simulate multiple traces, find uncovered action, tune to check if it was expected."""
        manifest = _make_manifest()
        # Only exercise read and send — leave delete_file untouched
        traces = [
            _make_trace(("read_email", {}, True)),
            _make_trace(("send_email", {}, True)),
        ]
        cov = analyze_coverage(manifest, traces)
        assert "delete_file" in cov.uncovered_actions

        # This dead rule might be intentional (requires approval gate is never triggered
        # in these traces). No tuning needed — it's a coverage gap, not a bug.
        assert cov.coverage_pct < 100.0
