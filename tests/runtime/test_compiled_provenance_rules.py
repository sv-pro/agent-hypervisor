"""
Tests for compiled provenance rules — second compiler/runtime boundary patch.

Four focused properties:

  1. Provenance rules are compiled at startup — the compiled artifact carries
     typed CompiledProvenanceRule objects, not raw YAML dicts.

  2. Runtime decisions use compiled structures — evaluate_provenance() returns
     correct verdicts using only frozen data, no YAML access.

  3. Raw YAML semantics are not re-interpreted on each decision — the compiled
     policy works correctly after the source YAML file is gone.

  4. Missing/unknown provenance paths fail closed — no-match default is deny,
     not allow or pass-through.

Run: pytest tests/runtime/test_compiled_provenance_rules.py
"""

from __future__ import annotations

import os
import textwrap

import pytest

from runtime import build_runtime
from runtime.compile import CompiledProvenanceRule, compile_world
from runtime.models import ArgumentProvenance, ProvenanceVerdict

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


# ── 1. Rules are compiled at startup ─────────────────────────────────────────

def test_provenance_rules_present_after_compilation():
    """
    compile_world() produces a CompiledPolicy whose provenance_rules tuple
    is non-empty when the manifest contains a provenance_rules section.
    """
    policy = compile_world(MANIFEST)
    assert len(policy.provenance_rules) > 0


def test_provenance_rules_are_compiled_rule_objects():
    """
    Each element in policy.provenance_rules is a CompiledProvenanceRule,
    not a raw dict. The YAML source dict is not preserved in the artifact.
    """
    policy = compile_world(MANIFEST)
    for rule in policy.provenance_rules:
        assert isinstance(rule, CompiledProvenanceRule), (
            f"Expected CompiledProvenanceRule, got {type(rule)}"
        )
        assert isinstance(rule.verdict, ProvenanceVerdict), (
            "rule.verdict must be a ProvenanceVerdict enum, not a string"
        )
        if rule.provenance is not None:
            assert isinstance(rule.provenance, ArgumentProvenance), (
                "rule.provenance must be an ArgumentProvenance enum, not a string"
            )


def test_rules_are_frozen():
    """
    CompiledProvenanceRule is a frozen dataclass — fields cannot be mutated
    after construction.
    """
    policy = compile_world(MANIFEST)
    rule = policy.provenance_rules[0]
    with pytest.raises((AttributeError, TypeError)):
        rule.verdict = ProvenanceVerdict.allow  # type: ignore[misc]


def test_provenance_rules_tuple_is_immutable():
    """
    policy.provenance_rules returns a tuple — not a list, not a mutable proxy.
    Reassignment to CompiledPolicy is blocked by the immutability mechanism.
    """
    policy = compile_world(MANIFEST)
    assert isinstance(policy.provenance_rules, tuple)
    with pytest.raises(AttributeError):
        policy._provenance_rules = ()  # type: ignore[misc]


def test_rule_ids_are_strings():
    """
    Each compiled rule carries a rule_id string derived from the manifest id field.
    The allow-read-data rule must appear by its declared id.
    """
    policy = compile_world(MANIFEST)
    ids = {r.rule_id for r in policy.provenance_rules}
    assert "allow-read-data" in ids
    assert "deny-email-external-recipient" in ids


# ── 2. Runtime decisions use compiled structures ──────────────────────────────

def test_read_data_evaluates_to_allow():
    """
    read_data is declared allow in the manifest.
    evaluate_provenance returns allow for any provenance chain.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance("read_data")
    assert verdict is ProvenanceVerdict.allow


def test_summarize_evaluates_to_allow():
    """
    summarize is declared allow in the manifest.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance("summarize")
    assert verdict is ProvenanceVerdict.allow


def test_send_email_with_external_recipient_is_denied():
    """
    send_email with argument=to and external_document in the provenance chain
    must evaluate to deny (RULE-01: external_document cannot authorize outbound email).
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance(
        tool="send_email",
        argument="to",
        chain_provenances=frozenset({ArgumentProvenance.external_document}),
    )
    assert verdict is ProvenanceVerdict.deny


def test_send_email_with_user_declared_recipient_is_ask():
    """
    send_email with argument=to and user_declared in the provenance chain
    (and no external_document) must evaluate to ask (confirmation required).

    deny > ask precedence: since there's no external_document here, only the
    ask rule fires.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance(
        tool="send_email",
        argument="to",
        chain_provenances=frozenset({ArgumentProvenance.user_declared}),
    )
    assert verdict is ProvenanceVerdict.ask


def test_send_email_external_beats_user_declared():
    """
    When both external_document and user_declared appear in the chain,
    deny (from the external_document rule) wins over ask (from the
    user_declared rule). Verdict precedence: deny > ask > allow.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance(
        tool="send_email",
        argument="to",
        chain_provenances=frozenset({
            ArgumentProvenance.external_document,
            ArgumentProvenance.user_declared,
        }),
    )
    assert verdict is ProvenanceVerdict.deny


def test_post_webhook_with_external_body_is_denied():
    """
    post_webhook with argument=body and external_document in chain → deny.
    Prevents SSRF / data exfiltration via webhooks.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance(
        tool="post_webhook",
        argument="body",
        chain_provenances=frozenset({ArgumentProvenance.external_document}),
    )
    assert verdict is ProvenanceVerdict.deny


def test_post_webhook_clean_is_ask():
    """
    post_webhook tool-level rule (no argument filter) → ask for clean data.
    """
    policy = compile_world(MANIFEST)
    # Evaluate without specifying an argument (whole-call level)
    verdict = policy.evaluate_provenance(
        tool="post_webhook",
        chain_provenances=frozenset({ArgumentProvenance.user_declared}),
    )
    assert verdict is ProvenanceVerdict.ask


def test_download_report_is_ask():
    """
    download_report is a tool-level ask rule.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance("download_report")
    assert verdict is ProvenanceVerdict.ask


def test_provenance_rules_are_consistent_across_two_compiles():
    """
    Two independent compile_world() calls from the same manifest produce
    equivalent provenance rule structures. The compilation is deterministic.
    """
    p1 = compile_world(MANIFEST)
    p2 = compile_world(MANIFEST)

    assert len(p1.provenance_rules) == len(p2.provenance_rules)
    for r1, r2 in zip(p1.provenance_rules, p2.provenance_rules):
        assert r1.rule_id == r2.rule_id
        assert r1.tool == r2.tool
        assert r1.verdict == r2.verdict
        assert r1.argument == r2.argument
        assert r1.provenance == r2.provenance


# ── 3. Raw YAML not re-interpreted on each decision ──────────────────────────

def test_evaluation_works_after_source_file_deleted(tmp_path):
    """
    compile_world() reads the manifest once. After that, evaluate_provenance()
    works correctly from the compiled structures — no file access.

    We compile from a temp file, delete the file, then evaluate. If the runtime
    were re-reading YAML on each call, this test would fail.
    """
    manifest = tmp_path / "world.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-delete
        actions:
          read_data:
            type: internal
          send_email:
            type: external
        trust:
          user: trusted
        capabilities:
          trusted: [internal, external]
        taint_rules: []
        provenance_rules:
          - id: allow-read-data
            tool: read_data
            verdict: allow
          - id: deny-email-external-to
            tool: send_email
            argument: to
            provenance: external_document
            verdict: deny
    """))

    policy = compile_world(str(manifest))

    # Delete the source file — the compiled policy must be self-contained
    manifest.unlink()
    assert not manifest.exists()

    # Evaluate using only compiled structures (no file access)
    assert policy.evaluate_provenance("read_data") is ProvenanceVerdict.allow
    assert policy.evaluate_provenance(
        "send_email", "to", frozenset({ArgumentProvenance.external_document})
    ) is ProvenanceVerdict.deny


# ── 4. Missing/unknown paths fail closed ─────────────────────────────────────

def test_unknown_tool_fails_closed():
    """
    A tool name not present in any provenance rule returns deny (fail-closed).
    There is no implicit allow for unknown tools.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance("unknown_tool_xyz")
    assert verdict is ProvenanceVerdict.deny


def test_empty_provenance_rules_section_fails_closed(tmp_path):
    """
    A manifest with no provenance_rules section compiles to an empty tuple.
    evaluate_provenance() returns deny for every query — fail-closed default.
    """
    manifest = tmp_path / "no_rules.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-no-rules
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
    """))

    policy = compile_world(str(manifest))
    assert policy.provenance_rules == ()
    # Every query fails closed
    assert policy.evaluate_provenance("read_data") is ProvenanceVerdict.deny
    assert policy.evaluate_provenance("send_email", "to") is ProvenanceVerdict.deny


def test_known_tool_unknown_argument_uses_tool_level_rule():
    """
    A tool-level rule (no argument filter) matches even when a specific
    argument is provided. The tool-level rule applies to all argument queries
    for that tool unless a more specific argument rule overrides it.

    Here: post_webhook has a tool-level ask rule.
    Querying with argument="url" (no argument-specific rule) should still
    match the tool-level rule → ask.
    """
    policy = compile_world(MANIFEST)
    verdict = policy.evaluate_provenance(
        tool="post_webhook",
        argument="url",  # no specific rule for this argument
        chain_provenances=frozenset({ArgumentProvenance.user_declared}),
    )
    # Tool-level ask rule fires (no arg filter → matches regardless of argument)
    assert verdict is ProvenanceVerdict.ask


def test_send_email_no_argument_fails_closed():
    """
    send_email has only argument-specific rules (for 'to').
    Querying at tool level with no argument provided and no matching tool-level
    rule → deny (fail-closed), because no rule matches.
    """
    policy = compile_world(MANIFEST)
    # No tool-level rule for send_email — only argument-specific rules
    verdict = policy.evaluate_provenance(
        tool="send_email",
        argument=None,
        chain_provenances=frozenset(),
    )
    assert verdict is ProvenanceVerdict.deny


def test_invalid_provenance_value_raises_at_compile_time(tmp_path):
    """
    An unknown provenance string in the manifest raises ValueError at
    compile_world() time — not at evaluation time.

    This proves validation happens at the compiler boundary, not lazily.
    """
    manifest = tmp_path / "bad_prov.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-bad
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
        provenance_rules:
          - id: bad-rule
            tool: read_data
            argument: content
            provenance: not_a_real_provenance_class
            verdict: deny
    """))

    with pytest.raises(ValueError):
        compile_world(str(manifest))


def test_invalid_verdict_value_raises_at_compile_time(tmp_path):
    """
    An unknown verdict string raises ValueError at compile_world() time.
    """
    manifest = tmp_path / "bad_verdict.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-bad-verdict
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
        provenance_rules:
          - id: bad-verdict-rule
            tool: read_data
            verdict: maybe
    """))

    with pytest.raises(ValueError):
        compile_world(str(manifest))


# ── Integration: build_runtime carries the compiled rules ────────────────────

def test_build_runtime_exposes_provenance_rules():
    """
    build_runtime() assembles a Runtime whose policy.provenance_rules is
    populated from the manifest. The compiled artifact is end-to-end present.
    """
    rt = build_runtime(MANIFEST)
    assert len(rt.policy.provenance_rules) > 0
    rule_ids = {r.rule_id for r in rt.policy.provenance_rules}
    assert "allow-read-data" in rule_ids
    assert "deny-email-external-recipient" in rule_ids
