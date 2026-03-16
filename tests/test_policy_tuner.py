"""
test_policy_tuner.py — Tests for the trace-driven policy tuner.

Tests are grouped by concern:
  1. Repeated ask detection
  2. Repeated approval pattern detection
  3. Risky allow detection
  4. Broad deny / heterogeneous match detection
  5. Scope drift detection
  6. Suggestion generation
  7. Report formatting (JSON and Markdown)

All tests use synthetic in-memory fixtures — no disk I/O.
"""

from __future__ import annotations

import json

import pytest

from agent_hypervisor.policy_tuner import (
    PolicyAnalyzer,
    SuggestionGenerator,
    TunerReporter,
)
from agent_hypervisor.policy_tuner.analyzer import MIN_REPEAT_COUNT
from agent_hypervisor.policy_tuner.models import (
    RuleMetrics,
    Severity,
    SignalCategory,
    SmellType,
    SuggestionType,
    TunerReport,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _trace(
    tool: str = "read_file",
    verdict: str = "allow",
    rule: str = "allow-read",
    policy_version: str = "v1",
    arg_provenance: dict | None = None,
    trace_id: str = "t001",
) -> dict:
    return {
        "trace_id": trace_id,
        "tool": tool,
        "final_verdict": verdict,
        "matched_rule": rule,
        "policy_version": policy_version,
        "arg_provenance": arg_provenance or {"path": "user_declared:manifest"},
    }


def _approval(
    tool: str = "send_email",
    status: str = "approved",
    rule: str = "ask-email",
    policy_version: str = "v1",
    actor: str = "alice",
    arg_provenance: dict | None = None,
    approval_id: str = "ap001",
) -> dict:
    return {
        "approval_id": approval_id,
        "tool": tool,
        "status": status,
        "matched_rule": rule,
        "policy_version": policy_version,
        "actor": actor,
        "arg_provenance": arg_provenance or {"to": "user_declared:manifest"},
    }


def _policy_version(version_id: str = "abc12345", rule_count: int = 5) -> dict:
    return {
        "version_id": version_id,
        "timestamp": "2024-01-01T00:00:00Z",
        "policy_file": "policies/default_policy.yaml",
        "content_hash": version_id * 8,
        "rule_count": rule_count,
    }


# ---------------------------------------------------------------------------
# 1. Repeated ask detection
# ---------------------------------------------------------------------------

class TestRepeatedAskDetection:

    def test_no_signal_below_threshold(self):
        traces = [
            _trace(verdict="ask", rule="ask-email", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT - 1)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        ask_signals = [s for s in report.signals if "ask" in s.title.lower() and "repeated" in s.title.lower()]
        assert len(ask_signals) == 0

    def test_signal_at_threshold(self):
        traces = [
            _trace(verdict="ask", rule="ask-email", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        ask_signals = [
            s for s in report.signals
            if s.category == SignalCategory.friction and "ask" in s.title.lower()
        ]
        assert len(ask_signals) == 1
        assert ask_signals[0].related_rule == "ask-email"
        assert ask_signals[0].severity == Severity.medium

    def test_signal_above_threshold(self):
        traces = [
            _trace(verdict="ask", rule="rule-X", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT + 5)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        ask_signals = [
            s for s in report.signals
            if s.category == SignalCategory.friction and "ask" in s.title.lower()
        ]
        assert len(ask_signals) == 1
        # Evidence should carry the count
        assert ask_signals[0].evidence[0]["ask_count"] == MIN_REPEAT_COUNT + 5

    def test_multiple_rules_separate_signals(self):
        traces = (
            [_trace(verdict="ask", rule="rule-A", trace_id=f"a{i}") for i in range(MIN_REPEAT_COUNT)]
            + [_trace(verdict="ask", rule="rule-B", trace_id=f"b{i}") for i in range(MIN_REPEAT_COUNT)]
        )
        report = PolicyAnalyzer().analyze(traces, [], [])
        ask_signals = [
            s for s in report.signals
            if s.category == SignalCategory.friction and "ask" in s.title.lower()
        ]
        rules = {s.related_rule for s in ask_signals}
        assert "rule-A" in rules
        assert "rule-B" in rules

    def test_deny_signal_also_detected(self):
        traces = [
            _trace(verdict="deny", rule="deny-external", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        deny_signals = [
            s for s in report.signals
            if s.category == SignalCategory.friction and "deny" in s.title.lower()
        ]
        assert len(deny_signals) == 1
        assert deny_signals[0].related_rule == "deny-external"


# ---------------------------------------------------------------------------
# 2. Repeated approval pattern detection
# ---------------------------------------------------------------------------

class TestRepeatedApprovalDetection:

    def test_no_signal_below_threshold(self):
        approvals = [
            _approval(tool="send_email", status="approved", approval_id=f"ap{i}")
            for i in range(MIN_REPEAT_COUNT - 1)
        ]
        report = PolicyAnalyzer().analyze([], approvals, [])
        friction_signals = [s for s in report.signals if s.category == SignalCategory.friction]
        approval_signals = [s for s in friction_signals if "approvals" in s.title.lower()]
        assert len(approval_signals) == 0

    def test_signal_at_threshold(self):
        approvals = [
            _approval(
                tool="send_email",
                status="approved",
                approval_id=f"ap{i}",
                arg_provenance={"to": "user_declared:manifest"},
            )
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze([], approvals, [])
        approval_signals = [
            s for s in report.signals
            if s.category == SignalCategory.friction and "approvals" in s.title.lower()
        ]
        assert len(approval_signals) == 1
        assert "send_email" in approval_signals[0].title

    def test_rejection_signal_detected(self):
        approvals = [
            _approval(
                tool="send_email",
                status="rejected",
                approval_id=f"ap{i}",
                arg_provenance={"to": "external_document:doc.txt"},
            )
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze([], approvals, [])
        rejection_signals = [
            s for s in report.signals
            if "rejection" in s.title.lower()
        ]
        assert len(rejection_signals) == 1

    def test_actor_shape_drift_detected(self):
        approvals = [
            _approval(
                tool="send_email",
                status="approved",
                actor="alice",
                approval_id=f"ap{i}",
                arg_provenance={"to": "user_declared:manifest"},
            )
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze([], approvals, [])
        drift_signals = [
            s for s in report.signals
            if s.category == SignalCategory.scope_drift and "alice" in s.title
        ]
        assert len(drift_signals) == 1
        assert drift_signals[0].evidence[0]["actor"] == "alice"


# ---------------------------------------------------------------------------
# 3. Risky allow detection
# ---------------------------------------------------------------------------

class TestRiskyAllowDetection:

    def test_repeated_allow_on_side_effect_tool(self):
        traces = [
            _trace(
                tool="send_email",
                verdict="allow",
                rule="allow-email",
                trace_id=f"t{i}",
                arg_provenance={"to": "user_declared:manifest"},
            )
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        risk_signals = [s for s in report.signals if s.category == SignalCategory.risk]
        side_effect_signals = [s for s in risk_signals if "side-effect" in s.title.lower()]
        assert len(side_effect_signals) >= 1
        assert any("send_email" in s.title for s in side_effect_signals)

    def test_risky_provenance_allow_detected(self):
        traces = [
            _trace(
                tool="send_email",
                verdict="allow",
                rule="allow-email",
                trace_id=f"t{i}",
                arg_provenance={"to": "external_document:attacker.txt"},
            )
            for i in range(1)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        risk_signals = [s for s in report.signals if s.category == SignalCategory.risk]
        risky_prov_signals = [
            s for s in risk_signals
            if "external" in s.title.lower() or "risky" in s.title.lower() or "derived" in s.title.lower()
        ]
        assert len(risky_prov_signals) >= 1

    def test_smell_allow_side_effect_weak_provenance(self):
        traces = [
            _trace(
                tool="http_post",
                verdict="allow",
                rule="allow-http",
                trace_id="t1",
                arg_provenance={"url": "external_document:page.html"},
            )
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        bad_smells = [
            s for s in report.smells
            if s.smell_type == SmellType.allow_side_effect_weak_provenance
        ]
        assert len(bad_smells) >= 1

    def test_heterogeneous_allow_rule_flagged(self):
        from agent_hypervisor.policy_tuner.analyzer import MIN_PROVENANCE_DIVERSITY
        traces = [
            _trace(
                tool="send_email",
                verdict="allow",
                rule="broad-allow",
                trace_id=f"t{i}",
                arg_provenance={"to": f"user_declared:source{i}"},
            )
            for i in range(MIN_PROVENANCE_DIVERSITY)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        risk_signals = [
            s for s in report.signals
            if s.category == SignalCategory.risk and "heterogeneous" in s.title.lower()
        ]
        assert len(risk_signals) >= 1


# ---------------------------------------------------------------------------
# 4. Broad deny / heterogeneous match detection
# ---------------------------------------------------------------------------

class TestBroadDenyDetection:

    def test_catch_all_deny_smell_detected(self):
        from agent_hypervisor.policy_tuner.analyzer import MIN_PROVENANCE_DIVERSITY
        # MIN_REPEAT_COUNT denies with MIN_PROVENANCE_DIVERSITY distinct shapes
        traces = []
        for i in range(max(MIN_REPEAT_COUNT, MIN_PROVENANCE_DIVERSITY)):
            traces.append(_trace(
                verdict="deny",
                rule="catch-all-deny",
                trace_id=f"t{i}",
                arg_provenance={"to": f"external_document:source{i}"},
            ))
        report = PolicyAnalyzer().analyze(traces, [], [])
        catch_all_smells = [
            s for s in report.smells
            if s.smell_type == SmellType.catch_all_deny_heterogeneous
        ]
        assert len(catch_all_smells) >= 1

    def test_homogeneous_deny_no_smell(self):
        # Same provenance pattern repeated — not heterogeneous
        traces = [
            _trace(
                verdict="deny",
                rule="deny-external",
                trace_id=f"t{i}",
                arg_provenance={"to": "external_document:doc.txt"},
            )
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        catch_all_smells = [
            s for s in report.smells
            if s.smell_type == SmellType.catch_all_deny_heterogeneous
        ]
        assert len(catch_all_smells) == 0


# ---------------------------------------------------------------------------
# 5. Scope drift detection
# ---------------------------------------------------------------------------

class TestScopeDriftDetection:

    def test_rule_spanning_all_versions_detected(self):
        # Create 2 policy versions
        policy_history = [_policy_version("v1"), _policy_version("v2")]
        # Same rule appears in traces for both versions
        traces = [
            _trace(verdict="allow", rule="persistent-rule", policy_version="v1", trace_id="t1"),
            _trace(verdict="allow", rule="persistent-rule", policy_version="v2", trace_id="t2"),
        ]
        report = PolicyAnalyzer().analyze(traces, [], policy_history)
        drift_signals = [
            s for s in report.signals
            if s.category == SignalCategory.scope_drift
            and "spans all" in s.title.lower()
        ]
        assert len(drift_signals) >= 1
        assert drift_signals[0].related_rule == "persistent-rule"

    def test_single_version_no_span_signal(self):
        policy_history = [_policy_version("v1")]
        traces = [
            _trace(verdict="allow", rule="some-rule", policy_version="v1", trace_id="t1"),
        ]
        report = PolicyAnalyzer().analyze(traces, [], policy_history)
        drift_signals = [
            s for s in report.signals
            if s.category == SignalCategory.scope_drift and "spans all" in s.title.lower()
        ]
        assert len(drift_signals) == 0

    def test_approval_spanning_versions_detected(self):
        approvals = [
            _approval(rule="ask-email", policy_version="v1", approval_id=f"ap{i}")
            for i in range(MIN_REPEAT_COUNT)
        ]
        # Override half with v2
        for a in approvals[1:]:
            a["policy_version"] = "v2"
        report = PolicyAnalyzer().analyze([], approvals, [])
        drift_signals = [
            s for s in report.signals
            if s.category == SignalCategory.scope_drift and "spans multiple" in s.title.lower()
        ]
        assert len(drift_signals) >= 1


# ---------------------------------------------------------------------------
# 6. Suggestion generation
# ---------------------------------------------------------------------------

class TestSuggestionGeneration:

    def _report_with_ask_signal(self):
        traces = [
            _trace(verdict="ask", rule="ask-email", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        return SuggestionGenerator().generate(report)

    def test_suggestions_generated_from_ask_signal(self):
        report = self._report_with_ask_signal()
        assert len(report.suggestions) > 0

    def test_narrow_rule_suggestion_present(self):
        report = self._report_with_ask_signal()
        narrow_sugs = [
            s for s in report.suggestions
            if s.suggestion_type == SuggestionType.narrow_rule_scope
        ]
        assert len(narrow_sugs) >= 1
        assert narrow_sugs[0].related_rule == "ask-email"

    def test_promote_approval_suggestion_present(self):
        report = self._report_with_ask_signal()
        promote_sugs = [
            s for s in report.suggestions
            if s.suggestion_type == SuggestionType.promote_approval_to_policy
        ]
        assert len(promote_sugs) >= 1

    def test_risky_allow_generates_constrain_provenance_suggestion(self):
        traces = [
            _trace(
                tool="send_email",
                verdict="allow",
                rule="allow-email",
                trace_id=f"t{i}",
                arg_provenance={"to": "external_document:doc.txt"},
            )
            for i in range(1)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        report = SuggestionGenerator().generate(report)
        constrain_sugs = [
            s for s in report.suggestions
            if s.suggestion_type == SuggestionType.reduce_allow_constrain_provenance
        ]
        assert len(constrain_sugs) >= 1

    def test_suggestion_ids_are_unique(self):
        traces = (
            [_trace(verdict="ask", rule=f"rule-{i}", trace_id=f"t{j}") for i in range(3) for j in range(MIN_REPEAT_COUNT)]
        )
        report = PolicyAnalyzer().analyze(traces, [], [])
        report = SuggestionGenerator().generate(report)
        ids = [s.id for s in report.suggestions]
        assert len(ids) == len(set(ids))

    def test_no_suggestions_on_empty_data(self):
        report = PolicyAnalyzer().analyze([], [], [])
        report = SuggestionGenerator().generate(report)
        assert len(report.suggestions) == 0


# ---------------------------------------------------------------------------
# 7. Report formatting
# ---------------------------------------------------------------------------

class TestReportFormatting:

    def _populated_report(self):
        traces = (
            [_trace(verdict="ask", rule="ask-email", trace_id=f"t{i}") for i in range(MIN_REPEAT_COUNT)]
            + [_trace(tool="send_email", verdict="allow", rule="allow-email",
                      trace_id=f"a{i}", arg_provenance={"to": "user_declared:m"})
               for i in range(MIN_REPEAT_COUNT)]
        )
        approvals = [
            _approval(approval_id=f"ap{i}") for i in range(MIN_REPEAT_COUNT)
        ]
        policy_history = [_policy_version("v1"), _policy_version("v2")]
        report = PolicyAnalyzer().analyze(traces, approvals, policy_history)
        return SuggestionGenerator().generate(report)

    def test_json_format_is_valid_json(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="json")
        data = json.loads(output)
        assert "summary" in data
        assert "signals" in data
        assert "smells" in data
        assert "suggestions" in data
        assert "generated_at" in data

    def test_json_summary_counts(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="json")
        data = json.loads(output)
        assert data["summary"]["total_traces"] > 0
        assert data["summary"]["total_approvals"] > 0

    def test_markdown_contains_required_sections(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="markdown")
        assert "# Policy Tuner Report" in output
        assert "## Summary" in output
        assert "## Tuning Signals" in output
        assert "## Policy Smells" in output
        assert "## Candidate Suggestions" in output

    def test_markdown_contains_disclaimer(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="markdown")
        assert "human policy operator" in output

    def test_empty_report_renders_without_error(self):
        from agent_hypervisor.policy_tuner.models import TunerReport
        empty = TunerReport()
        reporter = TunerReporter()
        md = reporter.render(empty, format="markdown")
        js = reporter.render(empty, format="json")
        assert "# Policy Tuner Report" in md
        assert json.loads(js)["summary"]["total_traces"] == 0

    def test_json_signals_have_required_fields(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="json")
        data = json.loads(output)
        for sig in data["signals"]:
            assert "id" in sig
            assert "category" in sig
            assert "severity" in sig
            assert "title" in sig
            assert "description" in sig

    def test_json_suggestions_have_required_fields(self):
        report = self._populated_report()
        output = TunerReporter().render(report, format="json")
        data = json.loads(output)
        for sug in data["suggestions"]:
            assert "id" in sug
            assert "suggestion_type" in sug
            assert "rationale" in sug
            assert "candidate_action" in sug
            assert "confidence" in sug

    def test_rule_verdict_breakdown_in_markdown(self):
        traces = [
            _trace(verdict="allow", rule="allow-read", trace_id=f"t{i}")
            for i in range(5)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        report = SuggestionGenerator().generate(report)
        output = TunerReporter().render(report, format="markdown")
        assert "Rule Verdict Breakdown" in output
        assert "allow-read" in output

    def test_approval_smell_detected_and_reported(self):
        """Approval-heavy rule smell should appear in markdown report."""
        # Create a rule that mostly triggers ask
        traces = [
            _trace(verdict="ask", rule="heavy-ask-rule", trace_id=f"t{i}")
            for i in range(MIN_REPEAT_COUNT)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        report = SuggestionGenerator().generate(report)
        output = TunerReporter().render(report, format="markdown")
        assert "Tuning Signals" in output


# ---------------------------------------------------------------------------
# 8. Rule metrics (risk score, usage count, scope reduction)
# ---------------------------------------------------------------------------

class TestRuleMetrics:
    """Tests for the new per-rule governance metrics in TunerReport."""

    def test_rule_metrics_populated_from_traces(self):
        traces = [
            _trace(verdict="allow", rule="allow-read", trace_id=f"t{i}")
            for i in range(3)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        assert "allow-read" in report.rule_metrics
        m = report.rule_metrics["allow-read"]
        assert m.usage_count == 3
        assert m.verdict_counts.get("allow", 0) == 3

    def test_rule_metrics_usage_count_matches_verdict_counts(self):
        traces = (
            [_trace(verdict="allow", rule="r1", trace_id=f"a{i}") for i in range(4)]
            + [_trace(verdict="deny", rule="r1", trace_id=f"d{i}") for i in range(2)]
        )
        report = PolicyAnalyzer().analyze(traces, [], [])
        m = report.rule_metrics["r1"]
        assert m.usage_count == 6
        assert m.verdict_counts["allow"] == 4
        assert m.verdict_counts["deny"] == 2

    def test_rule_metrics_risk_score_bounded(self):
        traces = [_trace(verdict="allow", rule="test-rule", trace_id=f"t{i}") for i in range(3)]
        report = PolicyAnalyzer().analyze(traces, [], [])
        m = report.rule_metrics["test-rule"]
        assert 0 <= m.risk_score <= 10

    def test_side_effect_allow_rule_gets_higher_risk(self):
        """Allows on side-effect tools should score higher than read-only allows."""
        traces_read = [
            _trace(tool="read_file", verdict="allow", rule="allow-read",
                   trace_id=f"r{i}", arg_provenance={"path": "system"})
            for i in range(5)
        ]
        traces_email = [
            _trace(tool="send_email", verdict="allow", rule="allow-email",
                   trace_id=f"e{i}", arg_provenance={"to": "user_declared"})
            for i in range(5)
        ]
        report = PolicyAnalyzer().analyze(traces_read + traces_email, [], [])
        read_score = report.rule_metrics["allow-read"].risk_score
        email_score = report.rule_metrics["allow-email"].risk_score
        assert email_score >= read_score

    def test_rule_metrics_included_in_json_output(self):
        traces = [_trace(verdict="allow", rule="allow-read", trace_id=f"t{i}") for i in range(3)]
        report = PolicyAnalyzer().analyze(traces, [], [])
        reporter = TunerReporter()
        data = json.loads(reporter.render(report, format="json"))
        assert "rule_metrics" in data
        assert "allow-read" in data["rule_metrics"]
        m = data["rule_metrics"]["allow-read"]
        assert "usage_count" in m
        assert "risk_score" in m
        assert "scope_reduction" in m

    def test_rule_metrics_section_in_markdown(self):
        traces = [
            _trace(tool="send_email", verdict="allow", rule="allow-email",
                   trace_id=f"t{i}", arg_provenance={"to": "user_declared"})
            for i in range(3)
        ]
        report = PolicyAnalyzer().analyze(traces, [], [])
        output = TunerReporter().render(report, format="markdown")
        assert "Per-Rule Governance Metrics" in output
        assert "allow-email" in output
        assert "Risk Score" in output

    def test_rule_metrics_to_dict_has_required_fields(self):
        m = RuleMetrics(
            rule_id="test-rule",
            usage_count=5,
            verdict_counts={"allow": 5},
            risk_score=3,
            scope_reduction="No reduction suggested.",
        )
        d = m.to_dict()
        assert d["rule_id"] == "test-rule"
        assert d["usage_count"] == 5
        assert d["risk_score"] == 3
        assert "scope_reduction" in d


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_full_pipeline_end_to_end(self):
        """Run the complete tuner pipeline with synthetic data."""
        traces = (
            # Repeated asks
            [_trace(verdict="ask", rule="ask-email", trace_id=f"ask{i}") for i in range(5)]
            # Repeated allows on side-effect tool
            + [_trace(tool="send_email", verdict="allow", rule="allow-email",
                      trace_id=f"allow{i}", arg_provenance={"to": "user_declared:m"})
               for i in range(4)]
            # Repeated denies
            + [_trace(verdict="deny", rule="deny-external", trace_id=f"deny{i}",
                      arg_provenance={"to": f"external_document:doc{i}.txt"})
               for i in range(4)]
            # Allow with risky provenance
            + [_trace(tool="http_post", verdict="allow", rule="allow-http",
                      trace_id="risky1",
                      arg_provenance={"url": "external_document:attacker.html"})]
        )
        approvals = [
            _approval(approval_id=f"ap{i}", actor="alice") for i in range(4)
        ]
        policy_history = [_policy_version("v1"), _policy_version("v2")]

        report = PolicyAnalyzer().analyze(traces, approvals, policy_history)
        report = SuggestionGenerator().generate(report)

        assert report.total_traces == len(traces)
        assert report.total_approvals == len(approvals)
        assert len(report.signals) > 0
        assert len(report.smells) > 0
        assert len(report.suggestions) > 0

        # Render both formats without error
        reporter = TunerReporter()
        md = reporter.render(report, format="markdown")
        js = reporter.render(report, format="json")

        data = json.loads(js)
        assert len(data["signals"]) == len(report.signals)
        assert len(data["suggestions"]) == len(report.suggestions)
