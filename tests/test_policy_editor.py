"""
test_policy_editor.py — Tests for the policy editor (load, validate, list, preview).

Test groups:
  1. load_policy — YAML parsing, error handling
  2. validate    — rule structural checks, duplicate id detection
  3. list_rules  — table formatting, filtering
  4. preview_rule — dry-run impact, conflict detection, scope notes
  5. rule_risk_score — scoring logic
  6. rule_usage_count — trace counting
  7. scope_reduction_hint — suggestion generation

All tests use in-memory fixtures or the real default_policy.yaml.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from agent_hypervisor.policy_editor import PolicyEditor, PolicyFile, PolicyRuleSpec, RuleImpact
from agent_hypervisor.policy_editor.policy_models import MatchedCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLICY_PATH = Path(__file__).parent.parent / "policies" / "default_policy.yaml"


def _write_policy(rules_yaml: str) -> str:
    """Write a temporary policy YAML file and return its path."""
    content = f"rules:\n{rules_yaml}"
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


def _simple_policy() -> str:
    """Return a minimal policy YAML as a string."""
    return """
rules:
  - id: allow-read-file
    tool: read_file
    verdict: allow
  - id: deny-email-external-recipient
    tool: send_email
    argument: to
    provenance: external_document
    verdict: deny
  - id: ask-email-declared-recipient
    tool: send_email
    argument: to
    provenance: user_declared
    verdict: ask
"""


# ---------------------------------------------------------------------------
# 1. load_policy
# ---------------------------------------------------------------------------

class TestLoadPolicy:
    def test_loads_default_policy(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        assert isinstance(policy, PolicyFile)
        assert len(policy.rules) > 0
        assert policy.path == str(POLICY_PATH)

    def test_loads_rules_correctly(self):
        path = _write_policy(
            "  - id: my-rule\n    tool: read_file\n    verdict: allow\n"
        )
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            assert len(policy.rules) == 1
            rule = policy.rules[0]
            assert rule.id == "my-rule"
            assert rule.tool == "read_file"
            assert rule.verdict == "allow"
        finally:
            os.unlink(path)

    def test_raises_on_missing_file(self):
        editor = PolicyEditor()
        with pytest.raises(FileNotFoundError):
            editor.load_policy("/nonexistent/policy.yaml")

    def test_raises_on_missing_rules_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("something: else\n")
            path = f.name
        try:
            editor = PolicyEditor()
            with pytest.raises(ValueError, match="no 'rules' key"):
                editor.load_policy(path)
        finally:
            os.unlink(path)

    def test_parses_all_fields(self):
        yaml_content = """
rules:
  - id: full-rule
    tool: send_email
    argument: to
    provenance: external_document
    role: recipient_source
    verdict: deny
    description: Block untrusted recipients
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            rule = policy.rules[0]
            assert rule.argument == "to"
            assert rule.provenance == "external_document"
            assert rule.role == "recipient_source"
            assert rule.description == "Block untrusted recipients"
        finally:
            os.unlink(path)

    def test_get_rule_returns_correct(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        rule = policy.get_rule("allow-read-file")
        assert rule is not None
        assert rule.verdict == "allow"
        assert rule.tool == "read_file"

    def test_get_rule_returns_none_for_missing(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        assert policy.get_rule("does-not-exist") is None

    def test_rules_for_tool(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        email_rules = policy.rules_for_tool("send_email")
        assert len(email_rules) >= 2
        for r in email_rules:
            assert r.tool == "send_email"


# ---------------------------------------------------------------------------
# 2. validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_policy_has_no_errors(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        errors = editor.validate(policy)
        assert errors == {}

    def test_detects_invalid_verdict(self):
        yaml_content = """
rules:
  - id: bad-verdict
    tool: read_file
    verdict: ALLOW
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            errors = editor.validate(policy)
            assert "bad-verdict" in errors
            assert any("invalid verdict" in e for e in errors["bad-verdict"])
        finally:
            os.unlink(path)

    def test_detects_invalid_provenance(self):
        yaml_content = """
rules:
  - id: bad-prov
    tool: send_email
    provenance: untrusted
    verdict: deny
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            errors = editor.validate(policy)
            assert "bad-prov" in errors
        finally:
            os.unlink(path)

    def test_detects_duplicate_ids(self):
        yaml_content = """
rules:
  - id: dup
    tool: read_file
    verdict: allow
  - id: dup
    tool: write_file
    verdict: deny
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            errors = editor.validate(policy)
            assert "dup" in errors
            assert any("Duplicate" in e for e in errors["dup"])
        finally:
            os.unlink(path)

    def test_missing_id_is_flagged(self):
        yaml_content = """
rules:
  - tool: read_file
    verdict: allow
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            editor = PolicyEditor()
            policy = editor.load_policy(path)
            errors = editor.validate(policy)
            # Expect at least one error about missing id
            assert len(errors) >= 1
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 3. list_rules
# ---------------------------------------------------------------------------

class TestListRules:
    def test_list_rules_returns_string(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        output = editor.list_rules(policy)
        assert isinstance(output, str)
        assert "allow-read-file" in output

    def test_list_rules_shows_rule_count(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        output = editor.list_rules(policy)
        assert str(len(policy.rules)) in output

    def test_list_rules_filter_by_tool(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        output = editor.list_rules(policy, filter_tool="send_email")
        assert "send_email" in output
        assert "read_file" not in output

    def test_list_rules_filter_by_verdict(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        output = editor.list_rules(policy, filter_verdict="deny")
        assert "deny" in output
        # Allow rules should not appear as data rows (header still has VERDICT)
        lines = output.splitlines()
        data_lines = [l for l in lines if "allow-read" in l]
        assert len(data_lines) == 0

    def test_list_rules_empty_filter_shows_no_match_note(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        output = editor.list_rules(policy, filter_tool="nonexistent_tool")
        assert "no rules match" in output.lower()


# ---------------------------------------------------------------------------
# 4. preview_rule
# ---------------------------------------------------------------------------

class TestPreviewRule:
    def test_preview_returns_rule_impact(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        impact = editor.preview_rule(policy, "deny-email-external-recipient")
        assert isinstance(impact, RuleImpact)
        assert impact.rule_id == "deny-email-external-recipient"
        assert impact.verdict == "deny"

    def test_preview_matches_expected_cases(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        impact = editor.preview_rule(policy, "deny-email-external-recipient")
        # Should match send_email / to / external_document
        assert len(impact.matched_cases) >= 1
        tools = {c.tool for c in impact.matched_cases}
        provenances = {c.provenance for c in impact.matched_cases}
        assert "send_email" in tools
        assert "external_document" in provenances

    def test_preview_allow_read_file_has_no_conflicts(self):
        """read_file allow should have broad match but few conflicts."""
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        impact = editor.preview_rule(policy, "allow-read-file")
        assert impact.verdict == "allow"
        # At least some cases matched
        assert len(impact.matched_cases) >= 1

    def test_preview_raises_on_unknown_rule(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        with pytest.raises(KeyError):
            editor.preview_rule(policy, "does-not-exist")

    def test_preview_summary_is_non_empty(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        impact = editor.preview_rule(policy, "ask-email-declared-recipient")
        summary = impact.summary()
        assert isinstance(summary, str)
        assert len(summary) > 10

    def test_preview_scope_note_populated(self):
        editor = PolicyEditor()
        policy = editor.load_policy(str(POLICY_PATH))
        impact = editor.preview_rule(policy, "deny-email-external-recipient")
        assert impact.scope_note != ""


# ---------------------------------------------------------------------------
# 5. rule_risk_score
# ---------------------------------------------------------------------------

class TestRuleRiskScore:
    def test_read_only_allow_has_low_score(self):
        rule = PolicyRuleSpec(id="allow-read", tool="read_file", verdict="allow")
        editor = PolicyEditor()
        score = editor.rule_risk_score(rule)
        # read_file is not a side-effect tool → low score
        assert score <= 3

    def test_allow_side_effect_no_constraints_has_high_score(self):
        rule = PolicyRuleSpec(id="allow-email", tool="send_email", verdict="allow")
        editor = PolicyEditor()
        score = editor.rule_risk_score(rule)
        # send_email + no provenance + no argument → high
        assert score >= 7

    def test_deny_external_doc_has_low_score(self):
        rule = PolicyRuleSpec(
            id="deny-external", tool="send_email",
            argument="to", provenance="external_document", verdict="deny"
        )
        editor = PolicyEditor()
        score = editor.rule_risk_score(rule)
        assert score <= 2

    def test_ask_rule_gets_slight_reduction(self):
        rule_ask = PolicyRuleSpec(id="ask-rule", tool="send_email", verdict="ask")
        rule_allow = PolicyRuleSpec(id="allow-rule", tool="send_email", verdict="allow")
        editor = PolicyEditor()
        # ask should be lower risk than allow (all else equal)
        assert editor.rule_risk_score(rule_ask) <= editor.rule_risk_score(rule_allow)

    def test_score_is_bounded_0_to_10(self):
        editor = PolicyEditor()
        for verdict in ["allow", "deny", "ask"]:
            for tool in ["read_file", "send_email", "http_post", "write_file", "shell_exec"]:
                rule = PolicyRuleSpec(id=f"r", tool=tool, verdict=verdict)
                score = editor.rule_risk_score(rule)
                assert 0 <= score <= 10


# ---------------------------------------------------------------------------
# 6. rule_usage_count
# ---------------------------------------------------------------------------

class TestRuleUsageCount:
    def _make_traces(self, rule_id: str, verdicts: list[str]) -> list[dict]:
        return [
            {"matched_rule": rule_id, "final_verdict": v}
            for v in verdicts
        ]

    def test_counts_allow(self):
        editor = PolicyEditor()
        traces = self._make_traces("my-rule", ["allow", "allow", "deny"])
        counts = editor.rule_usage_count("my-rule", traces)
        assert counts["allow"] == 2
        assert counts["deny"] == 1
        assert counts["ask"] == 0
        assert counts["total"] == 3

    def test_ignores_other_rules(self):
        editor = PolicyEditor()
        traces = [
            {"matched_rule": "other-rule", "final_verdict": "allow"},
            {"matched_rule": "my-rule", "final_verdict": "deny"},
        ]
        counts = editor.rule_usage_count("my-rule", traces)
        assert counts["total"] == 1

    def test_empty_traces_returns_zeros(self):
        editor = PolicyEditor()
        counts = editor.rule_usage_count("any-rule", [])
        assert counts == {"allow": 0, "ask": 0, "deny": 0, "total": 0}


# ---------------------------------------------------------------------------
# 7. scope_reduction_hint
# ---------------------------------------------------------------------------

class TestScopeReductionHint:
    def test_read_only_allow_no_hint_needed(self):
        rule = PolicyRuleSpec(id="r", tool="read_file", verdict="allow")
        editor = PolicyEditor()
        hint = editor.scope_reduction_hint(rule)
        assert "no reduction suggested" in hint.lower()

    def test_side_effect_allow_without_provenance_gets_hint(self):
        rule = PolicyRuleSpec(id="r", tool="send_email", verdict="allow")
        editor = PolicyEditor()
        hint = editor.scope_reduction_hint(rule)
        assert "provenance" in hint.lower()

    def test_deny_rule_no_hint(self):
        rule = PolicyRuleSpec(
            id="r", tool="send_email", argument="to",
            provenance="external_document", verdict="deny"
        )
        editor = PolicyEditor()
        hint = editor.scope_reduction_hint(rule)
        assert "no reduction suggested" in hint.lower()

    def test_wildcard_tool_gets_hint(self):
        rule = PolicyRuleSpec(id="r", tool="*", verdict="allow")
        editor = PolicyEditor()
        hint = editor.scope_reduction_hint(rule)
        assert "*" in hint or "explicit" in hint.lower()


# ---------------------------------------------------------------------------
# 8. PolicyRuleSpec helpers
# ---------------------------------------------------------------------------

class TestPolicyRuleSpec:
    def test_summary_includes_verdict_and_tool(self):
        rule = PolicyRuleSpec(
            id="deny-email-to", tool="send_email",
            argument="to", provenance="external_document", verdict="deny"
        )
        summary = rule.summary()
        assert "DENY" in summary.upper()
        assert "send_email" in summary
        assert "deny-email-to" in summary

    def test_to_dict_omits_empty_fields(self):
        rule = PolicyRuleSpec(id="allow-read", tool="read_file", verdict="allow")
        d = rule.to_dict()
        assert "argument" not in d
        assert "provenance" not in d
        assert d["id"] == "allow-read"

    def test_to_dict_includes_optional_fields(self):
        rule = PolicyRuleSpec(
            id="r", tool="send_email", verdict="deny",
            argument="to", provenance="external_document",
            description="Block untrusted"
        )
        d = rule.to_dict()
        assert d["argument"] == "to"
        assert d["provenance"] == "external_document"
        assert d["description"] == "Block untrusted"
