"""Tests for the emitter.py v2 compiler integration (Phase 4).

Coverage:
  - emit() on workspace_v2.yaml produces all expected artifact files
  - policy_table: allowed_tools and irreversible_tools populated from v2 actions
  - capability_matrix: by_trust_level matches manifest capability_matrix
  - taint_state_machine: transition_table built from taint_rules; containment_rules from transition_policies
  - data_class_taint_table: v2-only artifact maps data_class → taint_label/confirmation/retention
  - predicate_table: v2-only artifact maps raw tool → [{action, match}] list
  - manifest_meta: name reads from manifest.manifest.name (not top-level name)
  - escalation_table: escalation_rules compiled into conditions list
  - action_schemas: actions dict has expected fields
  - determinism: two consecutive emit() calls produce identical file contents
  - v1 regression: v1 manifest still emits without error
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_hypervisor.compiler.emitter import emit
from agent_hypervisor.compiler.schema import manifest_to_dict, WorldManifest, CapabilityConstraint


# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.parent
_WORKSPACE_V2 = _REPO_ROOT / "manifests" / "workspace_v2.yaml"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_workspace_v2() -> dict:
    return yaml.safe_load(_WORKSPACE_V2.read_text())


def _emit_workspace_v2(tmp_path: Path) -> dict[str, dict]:
    """Emit workspace_v2 and return a dict of artifact_name → parsed JSON."""
    raw = _load_workspace_v2()
    written = emit(raw, tmp_path)
    return {name: json.loads(path.read_text()) for name, path in written.items()}


# ── Tests: artifact presence ───────────────────────────────────────────────────


class TestEmitV2ArtifactPresence:
    def test_emit_workspace_v2_succeeds(self, tmp_path):
        """emit() on workspace_v2 must not raise."""
        raw = _load_workspace_v2()
        written = emit(raw, tmp_path)
        assert isinstance(written, dict)
        assert len(written) > 0

    def test_emit_produces_standard_artifacts(self, tmp_path):
        """All 8 standard artifacts must be written."""
        expected = {
            "policy_table.json",
            "capability_matrix.json",
            "taint_rules.json",
            "taint_state_machine.json",
            "escalation_table.json",
            "provenance_schema.json",
            "action_schemas.json",
            "manifest_meta.json",
        }
        raw = _load_workspace_v2()
        written = emit(raw, tmp_path)
        assert expected.issubset(written.keys()), (
            f"Missing standard artifacts: {expected - written.keys()}"
        )

    def test_emit_produces_v2_only_artifacts(self, tmp_path):
        """v2-specific artifacts must be written for a v2 manifest."""
        raw = _load_workspace_v2()
        written = emit(raw, tmp_path)
        assert "data_class_taint_table.json" in written, "Missing data_class_taint_table.json"
        assert "predicate_table.json" in written, "Missing predicate_table.json"

    def test_all_artifact_files_exist_on_disk(self, tmp_path):
        """Every returned path must exist and be non-empty."""
        raw = _load_workspace_v2()
        written = emit(raw, tmp_path)
        for name, path in written.items():
            assert path.exists(), f"{name} file not on disk"
            assert path.stat().st_size > 0, f"{name} is empty"


# ── Tests: policy_table ────────────────────────────────────────────────────────


class TestPolicyTableV2:
    def test_allowed_tools_populated(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        allowed = artifacts["policy_table.json"]["allowed_tools"]
        assert isinstance(allowed, list)
        assert len(allowed) > 0
        # A sample of expected actions
        for action in ("send_email", "read_emails_unread", "delete_file", "share_file"):
            assert action in allowed, f"Expected action '{action}' in allowed_tools"

    def test_irreversible_tools_populated(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        irreversible = artifacts["policy_table.json"]["irreversible_tools"]
        assert isinstance(irreversible, list)
        # Actions with reversible: false in workspace_v2
        for action in ("delete_file", "delete_email", "send_email"):
            assert action in irreversible, (
                f"Expected '{action}' in irreversible_tools — it has reversible: false"
            )

    def test_reversible_actions_not_in_irreversible(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        irreversible = set(artifacts["policy_table.json"]["irreversible_tools"])
        # read_emails_unread has reversible: true
        assert "read_emails_unread" not in irreversible


# ── Tests: capability_matrix ───────────────────────────────────────────────────


class TestCapabilityMatrixV2:
    def test_by_trust_level_present(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        matrix = artifacts["capability_matrix.json"]["by_trust_level"]
        assert "TRUSTED" in matrix
        assert "UNTRUSTED" in matrix

    def test_trusted_has_external_boundary(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        trusted = artifacts["capability_matrix.json"]["by_trust_level"]["TRUSTED"]
        assert "external_boundary" in trusted

    def test_untrusted_limited_to_read_only(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        untrusted = artifacts["capability_matrix.json"]["by_trust_level"]["UNTRUSTED"]
        assert untrusted == ["read_only"]


# ── Tests: taint_state_machine ─────────────────────────────────────────────────


class TestTaintStateMachineV2:
    def test_transition_table_populated(self, tmp_path):
        """transition_table must no longer be empty for v2 manifests."""
        artifacts = _emit_workspace_v2(tmp_path)
        tt = artifacts["taint_state_machine.json"]["transition_table"]
        assert isinstance(tt, dict)
        assert len(tt) > 0, "transition_table should be populated from taint_rules"

    def test_tainted_operations_present(self, tmp_path):
        """workspace_v2 has taint_rules for summarize/quote/extract/derive under 'tainted'."""
        artifacts = _emit_workspace_v2(tmp_path)
        tt = artifacts["taint_state_machine.json"]["transition_table"]
        assert "tainted" in tt
        for op in ("summarize", "quote", "extract", "derive"):
            assert op in tt["tainted"], f"Operation '{op}' missing from tainted transition_table"

    def test_preserve_maps_to_block_gate(self, tmp_path):
        """result: preserve in taint_rules → gate_required: BLOCK."""
        artifacts = _emit_workspace_v2(tmp_path)
        tt = artifacts["taint_state_machine.json"]["transition_table"]
        entry = tt["tainted"]["summarize"]
        assert entry["gate_required"] == "BLOCK"
        assert entry["taint_label"] == "tainted"

    def test_containment_rules_trusted_external_write_blocked(self, tmp_path):
        """internal_workspace (TRUSTED) → external_network transition is disallowed.
        So external_write side effect for TRUSTED should be blocked."""
        artifacts = _emit_workspace_v2(tmp_path)
        containment = artifacts["taint_state_machine.json"]["containment_rules"]
        # The transition policy: internal_workspace (TRUSTED) -> external_network: not allowed
        # This should result in TRUSTED.external_write being blocked or require_human
        trusted_rules = containment.get("TRUSTED", {})
        assert "external_write" in trusted_rules
        gate = trusted_rules["external_write"]
        assert gate in ("BLOCK", "require_human"), (
            f"Expected TRUSTED.external_write to require human or block, got: {gate}"
        )


# ── Tests: data_class_taint_table ─────────────────────────────────────────────


class TestDataClassTaintTableV2:
    def test_all_data_classes_present(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        dcs = artifacts["data_class_taint_table.json"]["data_classes"]
        expected = {"public", "internal", "pii", "credentials", "email_content"}
        assert expected == set(dcs.keys()), (
            f"Data class mismatch. Expected: {expected}, got: {set(dcs.keys())}"
        )

    def test_pii_confirmation_is_hard_confirm(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        pii = artifacts["data_class_taint_table.json"]["data_classes"]["pii"]
        assert pii["taint_label"] == "pii"
        assert pii["confirmation"] == "hard_confirm"
        assert pii["retention"] == "365d"

    def test_credentials_confirmation_is_require_human(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        creds = artifacts["data_class_taint_table.json"]["data_classes"]["credentials"]
        assert creds["confirmation"] == "require_human"
        assert creds["retention"] == "never"

    def test_public_taint_label_is_clean(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        public = artifacts["data_class_taint_table.json"]["data_classes"]["public"]
        assert public["taint_label"] == "clean"


# ── Tests: predicate_table ─────────────────────────────────────────────────────


class TestPredicateTableV2:
    def test_predicate_table_has_entries(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        predicates = artifacts["predicate_table.json"]["predicates"]
        assert isinstance(predicates, dict)
        assert len(predicates) > 0

    def test_create_calendar_event_has_two_predicates(self, tmp_path):
        """create_calendar_event dispatches to two actions based on participants arg."""
        artifacts = _emit_workspace_v2(tmp_path)
        predicates = artifacts["predicate_table.json"]["predicates"]
        assert "create_calendar_event" in predicates
        entries = predicates["create_calendar_event"]
        assert len(entries) == 2
        actions = [e["action"] for e in entries]
        assert "create_calendar_event_with_participants" in actions
        assert "create_calendar_event_personal" in actions

    def test_simple_predicate_single_entry(self, tmp_path):
        """send_email maps 1:1 to the send_email action."""
        artifacts = _emit_workspace_v2(tmp_path)
        predicates = artifacts["predicate_table.json"]["predicates"]
        assert "send_email" in predicates
        entries = predicates["send_email"]
        assert len(entries) == 1
        assert entries[0]["action"] == "send_email"


# ── Tests: manifest_meta ───────────────────────────────────────────────────────


class TestManifestMetaV2:
    def test_name_reads_from_manifest_block(self, tmp_path):
        """manifest_meta.name must come from manifest.manifest.name, not top-level."""
        artifacts = _emit_workspace_v2(tmp_path)
        meta = artifacts["manifest_meta.json"]
        assert meta["name"] == "workspace-suite-v2", (
            f"Expected 'workspace-suite-v2', got '{meta['name']}'. "
            "This tests the _build_manifest_meta v2 key fix."
        )

    def test_version_is_2_0(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        meta = artifacts["manifest_meta.json"]
        assert meta["version"] == "2.0"

    def test_content_hash_is_sha256(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        meta = artifacts["manifest_meta.json"]
        assert len(meta["content_hash"]) == 64  # SHA-256 hex digest length


# ── Tests: escalation_table ────────────────────────────────────────────────────


class TestEscalationTableV2:
    def test_escalation_conditions_populated(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        conditions = artifacts["escalation_table.json"]["conditions"]
        assert isinstance(conditions, list)
        assert len(conditions) > 0

    def test_send_email_esc_001_present(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        conditions = artifacts["escalation_table.json"]["conditions"]
        rule_ids = [c["id"] for c in conditions]
        assert "ESC-WS-001" in rule_ids

    def test_send_email_trigger_has_taint_flag(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        conditions = artifacts["escalation_table.json"]["conditions"]
        send_email_rule = next((c for c in conditions if c["id"] == "ESC-WS-001"), None)
        assert send_email_rule is not None
        assert send_email_rule["trigger"].get("taint") is True


# ── Tests: action_schemas ──────────────────────────────────────────────────────


class TestActionSchemasV2:
    def test_send_email_schema_present(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        actions = artifacts["action_schemas.json"]["actions"]
        assert "send_email" in actions

    def test_send_email_has_external_write_side_effect(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        send_email = artifacts["action_schemas.json"]["actions"]["send_email"]
        assert "external_write" in send_email["side_effects"]

    def test_delete_file_is_not_reversible(self, tmp_path):
        artifacts = _emit_workspace_v2(tmp_path)
        delete_file = artifacts["action_schemas.json"]["actions"]["delete_file"]
        assert delete_file["reversible"] is False


# ── Tests: determinism ─────────────────────────────────────────────────────────


class TestEmitDeterminism:
    def test_two_emits_produce_identical_files(self, tmp_path):
        """Same manifest → same artifact content every time (determinism invariant)."""
        raw = _load_workspace_v2()
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        written_a = emit(raw, out_a)
        written_b = emit(raw, out_b)

        assert set(written_a.keys()) == set(written_b.keys())
        for name in written_a:
            content_a = (out_a / name).read_text()
            content_b = (out_b / name).read_text()
            assert content_a == content_b, (
                f"Non-deterministic output for {name}"
            )


# ── Tests: v1 regression ───────────────────────────────────────────────────────


class TestEmitV1Regression:
    def test_v1_manifest_emits_without_error(self, tmp_path):
        """v1 manifests must still emit all 8 standard artifacts without raising."""
        v1 = WorldManifest(
            workflow_id="test-workflow",
            capabilities=[
                CapabilityConstraint(tool="read_file", constraints={}),
                CapabilityConstraint(tool="write_file", constraints={"paths": ["/workspace"]}),
            ],
            metadata={"description": "v1 regression test"},
        )
        from agent_hypervisor.compiler.schema import manifest_to_dict
        raw = manifest_to_dict(v1)
        written = emit(raw, tmp_path)

        standard = {
            "policy_table.json", "capability_matrix.json", "taint_rules.json",
            "taint_state_machine.json", "escalation_table.json", "provenance_schema.json",
            "action_schemas.json", "manifest_meta.json",
        }
        assert standard.issubset(written.keys())
        # v2-only artifacts must NOT be written for v1
        assert "data_class_taint_table.json" not in written
        assert "predicate_table.json" not in written
