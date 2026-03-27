"""
test_constraint_engine.py — Comprehensive tests for the fail-closed constraint engine.

Covers all 15 invariants and all mandatory test cases from the spec:

  INV-001  Unknown action => deny
  INV-002  Missing manifest => deny
  INV-003  Raw tool call resolves to exactly one action or deny
  INV-004  Schema mismatch => deny before execution
  INV-005  Capability missing => deny
  INV-006  Tainted external action => deny
  INV-007  High-risk action => requireapproval
  INV-008  Episode state is scoped; taint reset between episodes
  INV-009  Same manifest + same input => same decision
  INV-010  Every decision produces explainable trace
  INV-011  Provenance propagates through transformations
  INV-012  Actions not in ontology do not exist
  INV-013  Input normalisation is strict and type-safe
  INV-014  Irreversible internal actions require approval
  INV-015  Approval path is explicit, narrow, auditable
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ah_defense.action_resolver import (
    ResolutionError,
    extract_tool_args,
    extract_tool_name,
    make_raw_tool_call,
    normalize_tool_call_to_intent,
)
from ah_defense.intent_validator import (
    check_action_exists,
    check_capability,
    check_escalation,
    check_manifest_loaded,
    check_schema,
    check_taint_containment,
    validate_intent,
)
from ah_defense.manifest_compiler import ManifestCompileError, load_and_compile
from ah_defense.pipeline import evaluate_tool_call, start_episode
from ah_defense.policy_types import (
    ALLOW,
    DENY,
    REQUIRE_APPROVAL,
    CompiledManifest,
    EpisodeContext,
    NormalizedIntent,
    RawToolCall,
    TaintSummary,
)
from ah_defense.taint_tracker import ProvTaintState, TaintState

MANIFESTS_DIR = Path(__file__).parent.parent / "ah_defense" / "manifests"
V2_MANIFEST_PATH = MANIFESTS_DIR / "workspace_v2.yaml"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def manifest() -> CompiledManifest:
    return load_and_compile(V2_MANIFEST_PATH)


@pytest.fixture
def clean_prov_taint() -> ProvTaintState:
    t = ProvTaintState()
    t.reset_episode_state()
    return t


@pytest.fixture
def tainted_prov_taint(clean_prov_taint: ProvTaintState) -> ProvTaintState:
    clean_prov_taint.seed_from_semantic_event(
        source_channel="email",
        trust_level="untrusted",
        description="email_content",
        node_id="node_email_001",
    )
    return clean_prov_taint


@pytest.fixture
def trusted_episode(manifest: CompiledManifest) -> EpisodeContext:
    return start_episode(manifest, trust_level="trusted")


@pytest.fixture
def untrusted_episode(manifest: CompiledManifest) -> EpisodeContext:
    return start_episode(manifest, trust_level="untrusted")


def make_intent(
    raw_tool: str,
    action: str,
    args: dict[str, Any] | None = None,
    source_channel: str = "user",
) -> NormalizedIntent:
    return NormalizedIntent(
        raw_tool_name=raw_tool,
        action_name=action,
        args=args or {},
        call_id="test_call_001",
        source_channel=source_channel,
    )


def make_fc(function: str, args: dict | None = None, call_id: str = "call_001") -> MagicMock:
    """Create a mock FunctionCall-like object."""
    tc = MagicMock()
    tc.function = function
    tc.args = args or {}
    tc.id = call_id
    return tc


# ═══════════════════════════════════════════════════════════════════════════════
# INV-002: Missing manifest => deny
# ═══════════════════════════════════════════════════════════════════════════════

class TestMissingManifest:
    def test_check_manifest_loaded_none(self):
        step, early = check_manifest_loaded(None)
        assert step.verdict == DENY
        assert step.reason_code == "MISSING_MANIFEST"
        assert step.invariant == "INV-002"
        assert early is not None

    def test_validate_intent_no_manifest(self):
        intent = make_intent("send_email", "send_email", {"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=None, taint_state=None, trust_level="trusted")
        assert result.verdict == DENY
        assert result.reason_code == "MISSING_MANIFEST"
        assert result.violated_invariant == "INV-002"

    def test_missing_manifest_trace_has_step(self):
        intent = make_intent("foo", "foo")
        result = validate_intent(intent, manifest=None, taint_state=None)
        assert any(s.step_name == "check_manifest_loaded" for s in result.trace.steps)

    def test_start_episode_no_manifest_denies_all(self):
        episode = start_episode(None, trust_level="trusted")
        tc = make_fc("search_emails")
        result = evaluate_tool_call(tc, episode)
        assert result.verdict == DENY
        assert result.reason_code == "MISSING_MANIFEST"

    def test_manifest_file_not_found_raises(self):
        with pytest.raises(ManifestCompileError):
            load_and_compile(MANIFESTS_DIR / "nonexistent_suite_v2.yaml")


# ═══════════════════════════════════════════════════════════════════════════════
# INV-001 / INV-012: Unknown action => deny
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnknownAction:
    def test_unknown_action_denied(self, manifest: CompiledManifest):
        intent = make_intent("hack_the_planet", "hack_the_planet")
        result = validate_intent(intent, manifest=manifest, taint_state=None, trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == DENY
        assert result.reason_code == "UNKNOWN_ACTION"
        assert result.violated_invariant == "INV-001"

    def test_check_action_exists_missing(self, manifest: CompiledManifest):
        step, action_def, early = check_action_exists("nonexistent_action", manifest)
        assert step.verdict == DENY
        assert action_def is None
        assert early is not None

    def test_undefined_action_cannot_be_proposed(self, trusted_episode: EpisodeContext):
        tc = make_fc("hack_the_planet")
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == DENY

    def test_action_not_in_ontology_denied(self, manifest: CompiledManifest):
        # Create intent for action that doesn't exist
        step, adef, early = check_action_exists("fly_spaceship", manifest)
        assert early is not None
        assert early[0] == DENY


# ═══════════════════════════════════════════════════════════════════════════════
# INV-013: Input normalisation is strict and type-safe
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputNormalisation:
    def test_non_string_tool_name_denied(self):
        tc = MagicMock()
        tc.function = 42
        tc.args = {}
        tc.id = "call_001"
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_name(tc)
        assert exc_info.value.reason_code == "NON_STRING_TOOL_NAME"
        assert exc_info.value.invariant == "INV-013"

    def test_empty_tool_name_denied(self):
        tc = MagicMock()
        tc.function = ""
        tc.args = {}
        tc.id = "call_001"
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_name(tc)
        assert exc_info.value.reason_code == "EMPTY_TOOL_NAME"

    def test_whitespace_only_tool_name_denied(self):
        tc = MagicMock()
        tc.function = "   "
        tc.args = {}
        tc.id = "call_001"
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_name(tc)
        assert exc_info.value.reason_code == "EMPTY_TOOL_NAME"

    def test_missing_function_denied(self):
        tc = MagicMock(spec=[])  # spec=[] means no attributes
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_name(tc)
        # Should raise because no 'function' attribute
        assert exc_info.value.reason_code in (
            "MISSING_FUNCTION", "INVALID_TOOL_CALL_TYPE",
        )

    def test_none_function_denied(self):
        tc = MagicMock()
        tc.function = None
        tc.args = {}
        tc.id = "call_001"
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_name(tc)
        assert exc_info.value.reason_code == "MISSING_FUNCTION"

    def test_invalid_args_type_denied(self):
        tc = MagicMock()
        tc.function = "search_emails"
        tc.args = "not_a_dict"
        tc.id = "call_001"
        with pytest.raises(ResolutionError) as exc_info:
            extract_tool_args(tc)
        assert exc_info.value.reason_code == "INVALID_ARGS_TYPE"

    def test_evaluate_non_string_name_returns_deny(self, trusted_episode: EpisodeContext):
        tc = MagicMock()
        tc.function = 123
        tc.args = {}
        tc.id = "call_001"
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == DENY
        assert result.reason_code == "NON_STRING_TOOL_NAME"

    def test_evaluate_empty_name_returns_deny(self, trusted_episode: EpisodeContext):
        tc = make_fc("")
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == DENY
        assert result.reason_code == "EMPTY_TOOL_NAME"

    def test_evaluate_missing_function_returns_deny(self, trusted_episode: EpisodeContext):
        tc = MagicMock(spec=["args", "id"])
        tc.args = {}
        tc.id = "call_001"
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == DENY


# ═══════════════════════════════════════════════════════════════════════════════
# INV-003: Action resolution
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionResolution:
    def test_create_calendar_event_personal_resolves(self, manifest: CompiledManifest):
        raw = RawToolCall(function_name="create_calendar_event", raw_args={
            "title": "Lunch", "start_time": "12:00", "end_time": "13:00"
        }, call_id="c1")
        intent = normalize_tool_call_to_intent(raw, manifest)
        assert intent.action_name == "create_calendar_event_personal"

    def test_create_calendar_event_with_participants_resolves(self, manifest: CompiledManifest):
        raw = RawToolCall(function_name="create_calendar_event", raw_args={
            "title": "Meeting", "start_time": "10:00", "end_time": "11:00",
            "participants": ["alice@corp.com"]
        }, call_id="c2")
        intent = normalize_tool_call_to_intent(raw, manifest)
        assert intent.action_name == "create_calendar_event_with_participants"

    def test_unknown_tool_resolution_fails(self, manifest: CompiledManifest):
        raw = RawToolCall(function_name="unknown_xyz", raw_args={}, call_id="c3")
        with pytest.raises(ResolutionError) as exc_info:
            normalize_tool_call_to_intent(raw, manifest)
        assert exc_info.value.reason_code == "UNKNOWN_TOOL"
        assert exc_info.value.invariant == "INV-001"

    def test_deterministic_resolution(self, manifest: CompiledManifest):
        """INV-009: same input => same resolution."""
        raw1 = RawToolCall(function_name="send_email", raw_args={
            "recipients": ["x@y.com"], "subject": "s", "body": "b"
        }, call_id="c1")
        raw2 = RawToolCall(function_name="send_email", raw_args={
            "recipients": ["x@y.com"], "subject": "s", "body": "b"
        }, call_id="c2")
        i1 = normalize_tool_call_to_intent(raw1, manifest)
        i2 = normalize_tool_call_to_intent(raw2, manifest)
        assert i1.action_name == i2.action_name


# ═══════════════════════════════════════════════════════════════════════════════
# INV-004: Schema mismatch => deny
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaMismatch:
    def test_send_email_missing_recipients_denied(self, manifest: CompiledManifest):
        intent = make_intent("send_email", "send_email",
                             args={"subject": "Hi", "body": "Body"})
        result = validate_intent(intent, manifest=manifest, taint_state=None, trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == DENY
        assert result.reason_code == "SCHEMA_MISSING_REQUIRED_PARAM"
        assert result.violated_invariant == "INV-004"

    def test_send_email_wrong_type_denied(self, manifest: CompiledManifest):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": "not_a_list", "subject": "Hi", "body": "B"})
        result = validate_intent(intent, manifest=manifest, taint_state=None, trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == DENY
        assert result.reason_code == "SCHEMA_TYPE_MISMATCH"
        assert result.violated_invariant == "INV-004"

    def test_check_schema_missing_required(self, manifest: CompiledManifest):
        action_def = manifest.actions["send_email"]
        step, early = check_schema("send_email", {"body": "hi"}, action_def)
        assert step.verdict == DENY
        assert early is not None

    def test_schema_mismatch_before_execution(self, trusted_episode: EpisodeContext):
        """INV-004: schema check happens before any execution."""
        tc = make_fc("send_email", args={"body": "only_body"})
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == DENY
        assert result.reason_code == "SCHEMA_MISSING_REQUIRED_PARAM"
        # Ensure the trace confirms schema was checked and denied before escalation
        steps = {s.step_name: s for s in result.trace.steps}
        assert "check_schema" in steps
        assert steps["check_schema"].verdict == DENY


# ═══════════════════════════════════════════════════════════════════════════════
# INV-005: Capability missing => deny
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapabilityMismatch:
    def test_untrusted_cannot_send_email(self, manifest: CompiledManifest):
        """Untrusted context lacks external_boundary capability."""
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=None,
                                 trust_level="untrusted",
                                 capabilities=manifest.capability_matrix.get("untrusted", frozenset()))
        assert result.verdict == DENY
        assert result.reason_code == "CAPABILITY_MISSING"
        assert result.violated_invariant == "INV-005"

    def test_untrusted_cannot_delete_file(self, untrusted_episode: EpisodeContext):
        tc = make_fc("delete_file", args={"file_id": "f123"})
        result = evaluate_tool_call(tc, untrusted_episode)
        assert result.verdict == DENY
        assert result.reason_code == "CAPABILITY_MISSING"

    def test_trusted_has_external_boundary_capability(self, manifest: CompiledManifest):
        caps = manifest.capability_matrix.get("trusted", frozenset())
        assert "external_boundary" in caps

    def test_untrusted_has_only_read_only(self, manifest: CompiledManifest):
        caps = manifest.capability_matrix.get("untrusted", frozenset())
        assert "read_only" in caps
        assert "external_boundary" not in caps
        assert "approve_irreversible" not in caps

    def test_capability_check_step_in_trace(self, untrusted_episode: EpisodeContext):
        tc = make_fc("send_email", args={"recipients": ["a@b.com"], "subject": "s", "body": "b"})
        result = evaluate_tool_call(tc, untrusted_episode)
        steps = {s.step_name: s for s in result.trace.steps}
        assert "check_capability" in steps
        assert steps["check_capability"].verdict == DENY


# ═══════════════════════════════════════════════════════════════════════════════
# INV-006: Tainted external action => deny
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaintContainment:
    def test_tainted_send_email_denied(self, manifest: CompiledManifest, tainted_prov_taint: ProvTaintState):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=tainted_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == DENY
        assert result.reason_code == "TAINT_CONTAINMENT_VIOLATION"
        assert result.violated_invariant == "INV-006"

    def test_tainted_share_file_denied(self, manifest: CompiledManifest, tainted_prov_taint: ProvTaintState):
        intent = make_intent("share_file", "share_file",
                             args={"file_id": "f1", "recipients": ["x@y.com"]})
        result = validate_intent(intent, manifest=manifest, taint_state=tainted_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == DENY
        assert result.reason_code == "TAINT_CONTAINMENT_VIOLATION"

    def test_tainted_read_only_allowed(self, manifest: CompiledManifest, tainted_prov_taint: ProvTaintState):
        intent = make_intent("search_emails", "search_emails")
        result = validate_intent(intent, manifest=manifest, taint_state=tainted_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        # read_only: not external_boundary => not blocked by taint
        assert result.verdict == ALLOW

    def test_clean_external_passes_taint_check(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        # Passes taint check; hits escalation (requires_approval=True)
        assert result.verdict == REQUIRE_APPROVAL

    def test_inter_agent_input_untrusted(self, manifest: CompiledManifest):
        """INV-006: inter-agent input defaults to untrusted."""
        assert manifest.inter_agent_trust == "untrusted"

    def test_taint_containment_step_in_trace(self, manifest: CompiledManifest, tainted_prov_taint: ProvTaintState):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=tainted_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        steps = {s.step_name: s for s in result.trace.steps}
        assert "check_taint_containment" in steps
        assert steps["check_taint_containment"].verdict == DENY


# ═══════════════════════════════════════════════════════════════════════════════
# INV-007 / INV-015: High-risk action => requireapproval
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscalation:
    def test_send_email_requires_approval_clean_context(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL
        assert result.reason_code == "APPROVAL_REQUIRED"
        assert result.violated_invariant == "INV-007"

    def test_delete_file_requires_approval(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        """INV-014: Irreversible internal action requires approval."""
        intent = make_intent("delete_file", "delete_file", args={"file_id": "f123"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL
        assert result.violated_invariant == "INV-007"

    def test_delete_email_requires_approval(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("delete_email", "delete_email", args={"email_id": "e001"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL

    def test_create_calendar_with_participants_requires_approval(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        intent = make_intent(
            "create_calendar_event", "create_calendar_event_with_participants",
            args={"title": "M", "start_time": "10:00", "end_time": "11:00",
                  "participants": ["alice@corp.com"]}
        )
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL

    def test_add_calendar_event_participants_requires_approval(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        intent = make_intent("add_calendar_event_participants", "add_calendar_event_participants",
                             args={"event_id": "ev1", "participants": ["b@corp.com"]})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL

    def test_share_file_requires_approval(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        intent = make_intent("share_file", "share_file",
                             args={"file_id": "f1", "recipients": ["c@corp.com"]})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict == REQUIRE_APPROVAL

    def test_matched_rule_id_present_for_escalation(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        """INV-015: approval path must be auditable (rule_id present)."""
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.matched_rule_id is not None
        assert len(result.matched_rule_id) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# INV-007: requireapproval is never silently allow
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoSilentAllow:
    def test_requireapproval_is_not_allow(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("delete_file", "delete_file", args={"file_id": "f1"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.verdict != ALLOW
        assert result.verdict == REQUIRE_APPROVAL

    def test_requireapproval_human_reason_not_empty(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        intent = make_intent("delete_email", "delete_email", args={"email_id": "e1"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.human_reason
        assert len(result.human_reason) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Allowed actions
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowedActions:
    def test_read_only_action_allowed(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("search_emails", "search_emails")
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        assert result.verdict == ALLOW

    def test_read_only_allowed_with_taint(self, manifest: CompiledManifest, tainted_prov_taint: ProvTaintState):
        """Read-only actions are not blocked by taint (only external boundary is)."""
        intent = make_intent("get_file_by_id", "get_file_by_id")
        result = validate_intent(intent, manifest=manifest, taint_state=tainted_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        assert result.verdict == ALLOW

    def test_reversible_internal_allowed(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("create_file", "create_file", args={"filename": "notes.txt"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        assert result.verdict == ALLOW

    def test_create_calendar_event_personal_allowed(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        """Personal calendar event (no participants) is allowed without approval."""
        intent = make_intent(
            "create_calendar_event", "create_calendar_event_personal",
            args={"title": "Lunch", "start_time": "12:00", "end_time": "13:00"}
        )
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        assert result.verdict == ALLOW


# ═══════════════════════════════════════════════════════════════════════════════
# INV-008: Episode state is scoped; taint reset between episodes
# ═══════════════════════════════════════════════════════════════════════════════

class TestEpisodeScoping:
    def test_taint_reset_between_episodes(self):
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email_content", node_id="n1")
        assert t.is_tainted

        # New episode: reset
        t.reset_episode_state()
        assert not t.is_tainted
        assert len(t._nodes) == 0

    def test_start_episode_returns_fresh_context(self, manifest: CompiledManifest):
        ep1 = start_episode(manifest, "trusted")
        ep2 = start_episode(manifest, "trusted")
        assert ep1.episode_id != ep2.episode_id
        assert len(ep1.decisions) == 0
        assert len(ep2.decisions) == 0

    def test_decisions_scoped_to_episode(self, trusted_episode: EpisodeContext):
        tc = make_fc("search_emails")
        evaluate_tool_call(tc, trusted_episode)
        assert len(trusted_episode.decisions) == 1

    def test_taint_does_not_leak_across_episodes(self, manifest: CompiledManifest):
        ep1 = start_episode(manifest, "trusted")
        pt1 = ProvTaintState()
        pt1.seed_from_semantic_event("email", "untrusted", "email", node_id="n1")

        ep2 = start_episode(manifest, "trusted")
        pt2 = ProvTaintState()  # fresh — no taint

        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        # ep1 with taint => deny
        r1 = validate_intent(intent, manifest=manifest, taint_state=pt1,
                             trust_level="trusted",
                             capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        # ep2 clean => requireapproval (not deny due to taint)
        r2 = validate_intent(intent, manifest=manifest, taint_state=pt2,
                             trust_level="trusted",
                             capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert r1.verdict == DENY
        assert r2.verdict == REQUIRE_APPROVAL


# ═══════════════════════════════════════════════════════════════════════════════
# INV-009: Same manifest + same input => same decision
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_same_input_same_decision(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("search_emails", "search_emails")
        caps = manifest.capability_matrix.get("trusted", frozenset())
        r1 = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                             trust_level="trusted", capabilities=caps)
        r2 = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                             trust_level="trusted", capabilities=caps)
        assert r1.verdict == r2.verdict
        assert r1.reason_code == r2.reason_code
        assert r1.violated_invariant == r2.violated_invariant

    def test_same_manifest_same_resolution(self, manifest: CompiledManifest):
        raw1 = RawToolCall("create_calendar_event",
                           {"title": "M", "start_time": "10:00", "end_time": "11:00"}, "c1")
        raw2 = RawToolCall("create_calendar_event",
                           {"title": "M", "start_time": "10:00", "end_time": "11:00"}, "c2")
        i1 = normalize_tool_call_to_intent(raw1, manifest)
        i2 = normalize_tool_call_to_intent(raw2, manifest)
        assert i1.action_name == i2.action_name


# ═══════════════════════════════════════════════════════════════════════════════
# INV-010: Every decision produces explainable trace
# ═══════════════════════════════════════════════════════════════════════════════

class TestExplainability:
    def test_trace_has_steps(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("search_emails", "search_emails")
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        assert len(result.trace.steps) > 0

    def test_trace_serialisable(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("search_emails", "search_emails")
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        d = result.trace.to_dict()
        assert isinstance(d, dict)
        assert "steps" in d
        assert "final_verdict" in d

    def test_deny_result_serialisable(self, manifest: CompiledManifest):
        intent = make_intent("hack", "hack")
        result = validate_intent(intent, manifest=manifest, taint_state=None,
                                 trust_level="trusted",
                                 capabilities=frozenset())
        d = result.to_dict()
        assert d["verdict"] == DENY
        assert d["violated_invariant"] is not None

    def test_all_result_fields_populated(self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState):
        intent = make_intent("send_email", "send_email",
                             args={"recipients": ["x@y.com"], "subject": "s", "body": "b"})
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=frozenset(["read_only", "internal_write", "external_boundary", "approve_irreversible"]))
        assert result.raw_tool_name
        assert result.action_name
        assert result.verdict
        assert result.reason_code
        assert result.human_reason
        assert result.trace is not None

    def test_trace_step_names_in_expected_order(
        self, manifest: CompiledManifest, clean_prov_taint: ProvTaintState
    ):
        intent = make_intent("search_emails", "search_emails")
        result = validate_intent(intent, manifest=manifest, taint_state=clean_prov_taint,
                                 trust_level="trusted",
                                 capabilities=manifest.capability_matrix.get("trusted", frozenset()))
        step_names = [s.step_name for s in result.trace.steps]
        # First step must always be manifest check
        assert step_names[0] == "check_manifest_loaded"


# ═══════════════════════════════════════════════════════════════════════════════
# INV-011: Provenance propagates through transformations
# ═══════════════════════════════════════════════════════════════════════════════

class TestProvenancePropagation:
    def test_provenance_propagates_through_summarize(self, manifest: CompiledManifest):
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email_content", node_id="n1")
        assert t.is_tainted

        # summarize operation: taint must be preserved per manifest rules
        t.apply_transformation_rule("summarize", manifest)
        assert t.is_tainted

    def test_provenance_propagates_through_quote(self, manifest: CompiledManifest):
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email_content", node_id="n1")
        t.apply_transformation_rule("quote", manifest)
        assert t.is_tainted

    def test_provenance_propagates_through_extract(self, manifest: CompiledManifest):
        t = ProvTaintState()
        t.seed_from_semantic_event("web", "untrusted", "web_content", node_id="n1")
        t.apply_transformation_rule("extract", manifest)
        assert t.is_tainted

    def test_aggregate_does_not_clear_taint_without_explicit_rule(self, manifest: CompiledManifest):
        """aggregate/count clears taint ONLY if manifest explicitly allows — which workspace_v2 does NOT."""
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email_content", node_id="n1")
        t.apply_transformation_rule("aggregate", manifest)
        assert t.is_tainted

    def test_unknown_transformation_preserves_taint(self, manifest: CompiledManifest):
        """INV-011: unknown operation => fail-closed => preserve taint."""
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email", node_id="n1")
        t.apply_transformation_rule("xyzzy_unknown_op", manifest)
        assert t.is_tainted

    def test_unknown_transformation_no_manifest_preserves_taint(self):
        """Without manifest, unknown transformation must preserve taint (fail-closed)."""
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email", node_id="n1")
        t.apply_transformation_rule("summarize", None)
        assert t.is_tainted

    def test_provenance_summary_reflects_channels(self):
        t = ProvTaintState()
        t.seed_from_semantic_event("email", "untrusted", "email", node_id="n1")
        t.seed_from_semantic_event("web", "untrusted", "web", node_id="n2")
        summary = t.summarize_provenance()
        assert "email" in summary.source_channels
        assert "web" in summary.source_channels
        assert summary.has_untrusted

    def test_agent_input_marked_in_provenance(self):
        t = ProvTaintState()
        t.seed_from_semantic_event("agent", "untrusted", "agent_msg", node_id="n1")
        summary = t.summarize_provenance()
        assert summary.has_agent_input
        assert t.is_tainted


# ═══════════════════════════════════════════════════════════════════════════════
# INV-014: Irreversible internal actions ≠ harmless writes
# ═══════════════════════════════════════════════════════════════════════════════

class TestIrreversible:
    def test_delete_file_is_irreversible_in_manifest(self, manifest: CompiledManifest):
        assert manifest.actions["delete_file"].irreversible is True

    def test_delete_email_is_irreversible_in_manifest(self, manifest: CompiledManifest):
        assert manifest.actions["delete_email"].irreversible is True

    def test_create_file_is_not_irreversible(self, manifest: CompiledManifest):
        assert manifest.actions["create_file"].irreversible is False

    def test_delete_file_requireapproval_in_trusted_context(
        self, trusted_episode: EpisodeContext
    ):
        tc = make_fc("delete_file", args={"file_id": "f123"})
        result = evaluate_tool_call(tc, trusted_episode)
        assert result.verdict == REQUIRE_APPROVAL

    def test_irreversible_internal_not_treated_as_reversible(self, manifest: CompiledManifest):
        df = manifest.actions["delete_file"]
        cf = manifest.actions["create_file"]
        assert df.action_class == "irreversible_internal"
        assert cf.action_class == "reversible_internal"
        assert df.requires_approval is True
        assert cf.requires_approval is False


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy IntentValidator backward compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyIntentValidator:
    def test_for_suite_workspace(self):
        from ah_defense.intent_validator import IntentValidator
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        # send_email should be known as external_side_effect or external_boundary
        tt = v.get_tool_type("send_email")
        assert tt in ("external_side_effect", "unknown")

    def test_unknown_suite_no_longer_permissive(self):
        """Breaking change: unknown suite => deny-all (was: permissive)."""
        from ah_defense.intent_validator import IntentValidator
        v = IntentValidator.for_suite("nonexistent_suite_xyz", MANIFESTS_DIR)
        # Now returns deny-all (empty classifications + no manifest)
        tt = v.get_tool_type("any_tool")
        assert tt == "unknown"

    def test_unknown_tool_denied_in_validate(self):
        """Breaking change: unknown tool is now DENIED (INV-001)."""
        from ah_defense.intent_validator import IntentValidator
        from ah_defense.taint_tracker import TaintState
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        ts = TaintState()
        result = v.validate("mystery_tool_xyz", ts)
        assert result.verdict == "deny"

    def test_tainted_external_denied_in_validate(self):
        from ah_defense.intent_validator import IntentValidator
        from ah_defense.taint_tracker import TaintState
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        result = v.validate("send_email", ts)
        assert result.verdict == "deny"

    def test_read_only_allowed_with_taint(self):
        from ah_defense.intent_validator import IntentValidator
        from ah_defense.taint_tracker import TaintState
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        result = v.validate("search_emails", ts)
        assert result.verdict == "allow"


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy TaintState backward compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyTaintState:
    def test_initial_not_tainted(self):
        ts = TaintState()
        assert not ts.is_tainted

    def test_mark_tainted(self):
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        assert ts.is_tainted
        assert "call_1" in ts.tainted_call_ids

    def test_taint_blocks_external(self):
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        assert ts.check_tool_call("send_email", "external_side_effect") is True

    def test_taint_allows_read_only(self):
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        assert ts.check_tool_call("search_emails", "read_only") is False

    def test_reset_clears_state(self):
        ts = TaintState()
        ts.mark_tainted("call_1", "get_emails")
        ts.reset()
        assert not ts.is_tainted
        assert len(ts.tainted_call_ids) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Manifest compiler
# ═══════════════════════════════════════════════════════════════════════════════

class TestManifestCompiler:
    def test_workspace_v2_loads(self, manifest: CompiledManifest):
        assert manifest.version == "2.0"
        assert manifest.suite == "workspace"

    def test_all_required_actions_present(self, manifest: CompiledManifest):
        required = [
            "send_email", "create_calendar_event_personal",
            "create_calendar_event_with_participants", "add_calendar_event_participants",
            "share_file", "delete_file", "delete_email",
            "search_emails", "get_file_by_id", "list_files",
        ]
        for action in required:
            assert action in manifest.actions, f"Action '{action}' missing from manifest"

    def test_invalid_manifest_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("version: '2.0'\n# missing suite, actions, etc.\n")
        with pytest.raises(ManifestCompileError):
            load_and_compile(bad)

    def test_capability_matrix_all_trust_levels(self, manifest: CompiledManifest):
        for level in ("untrusted", "semi_trusted", "trusted"):
            assert level in manifest.capability_matrix

    def test_predicates_cover_all_raw_tools(self, manifest: CompiledManifest):
        """Every predicate must reference an existing action."""
        for tool_name, preds in manifest.tool_predicates.items():
            for pred in preds:
                assert pred["action"] in manifest.actions, (
                    f"Predicate for '{tool_name}' references undefined action '{pred['action']}'"
                )
