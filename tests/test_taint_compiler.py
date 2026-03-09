"""
tests/test_taint_compiler.py — Unit tests for the taint rule compiler.

Verifies that taint rules compile into a correct, deterministic state machine.
No LLM involved. All assertions are deterministic.

The key properties tested:
  1. Transition table covers every (source_taint, operation) pair from the rules.
  2. Containment rules match the sanitization gates in the manifest.
  3. Sanitization index is keyed by taint label.
  4. Conflicts are recorded (not silently dropped) when two rules clash.
  5. Output is deterministic: same input → same state machine.

Run with:
    pytest tests/test_taint_compiler.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.loader import load
from compiler.taint_compiler import compile_taint_rules, compile_from_manifest, TAINT_ORDER

MANIFESTS_DIR = Path(__file__).parent.parent / "manifests" / "examples"
EMAIL_MANIFEST = MANIFESTS_DIR / "email-safe-assistant.yaml"
MCP_MANIFEST = MANIFESTS_DIR / "mcp-gateway-demo.yaml"
BROWSER_MANIFEST = MANIFESTS_DIR / "browser-agent-demo.yaml"


@pytest.fixture
def email_sm() -> dict:
    return compile_from_manifest(load(EMAIL_MANIFEST))


@pytest.fixture
def mcp_sm() -> dict:
    return compile_from_manifest(load(MCP_MANIFEST))


@pytest.fixture
def browser_sm() -> dict:
    return compile_from_manifest(load(BROWSER_MANIFEST))


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestStateMachineStructure:
    def test_has_required_keys(self, email_sm: dict) -> None:
        for key in ("taint_order", "transition_table", "containment_rules",
                    "sanitization_index", "conflicts"):
            assert key in email_sm, f"Missing key: {key}"

    def test_taint_order_is_canonical(self, email_sm: dict) -> None:
        assert email_sm["taint_order"] == TAINT_ORDER

    def test_conflicts_is_list(self, email_sm: dict) -> None:
        assert isinstance(email_sm["conflicts"], list)


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

class TestTransitionTable:
    def test_email_untrusted_summarize_transition(self, email_sm: dict) -> None:
        """Email body taint rule: summarize spreads UNTRUSTED taint."""
        tt = email_sm["transition_table"]
        assert "UNTRUSTED" in tt
        assert "summarize" in tt["UNTRUSTED"]
        entry = tt["UNTRUSTED"]["summarize"]
        assert entry["taint_label"] == "UNTRUSTED"
        assert entry["spreads_to"] == "output"

    def test_email_untrusted_store_spreads_to_memory(self, email_sm: dict) -> None:
        tt = email_sm["transition_table"]
        entry = tt["UNTRUSTED"]["store"]
        assert entry["spreads_to"] == "memory_entry"
        assert entry["taint_label"] == "UNTRUSTED"

    def test_email_semi_trusted_store(self, email_sm: dict) -> None:
        tt = email_sm["transition_table"]
        assert "SEMI_TRUSTED" in tt
        assert "store" in tt["SEMI_TRUSTED"]

    def test_mcp_web_content_taint_transitions(self, mcp_sm: dict) -> None:
        """MCP manifest: UNTRUSTED (web) taint has code_generation transition."""
        tt = mcp_sm["transition_table"]
        assert "code_generation" in tt.get("UNTRUSTED", {})

    def test_browser_untrusted_extract_transition(self, browser_sm: dict) -> None:
        tt = browser_sm["transition_table"]
        assert "extract" in tt.get("UNTRUSTED", {})

    def test_no_internal_rule_id_in_output(self, email_sm: dict) -> None:
        """Internal _rule_id field must not appear in the serialised output."""
        raw = json.dumps(email_sm)
        assert "_rule_id" not in raw


# ---------------------------------------------------------------------------
# Containment rules
# ---------------------------------------------------------------------------

class TestContainmentRules:
    def test_untrusted_output_requires_gate(self, email_sm: dict) -> None:
        """UNTRUSTED taint on output must require human_approval gate."""
        cr = email_sm["containment_rules"]
        assert "UNTRUSTED" in cr
        gate = cr["UNTRUSTED"].get("output")
        assert gate is not None
        assert gate != "ALLOW"  # must not be freely allowed

    def test_untrusted_memory_entry_blocked_or_gated(self, email_sm: dict) -> None:
        cr = email_sm["containment_rules"]
        gate = cr["UNTRUSTED"].get("memory_entry")
        assert gate is not None

    def test_semi_trusted_gate_present(self, email_sm: dict) -> None:
        cr = email_sm["containment_rules"]
        assert "SEMI_TRUSTED" in cr

    def test_mcp_untrusted_execution_input_blocked(self, mcp_sm: dict) -> None:
        """Default containment: UNTRUSTED data cannot reach execution_input."""
        cr = mcp_sm["containment_rules"]
        gate = cr.get("UNTRUSTED", {}).get("execution_input", "BLOCK")
        assert gate == "BLOCK"


# ---------------------------------------------------------------------------
# Sanitization index
# ---------------------------------------------------------------------------

class TestSanitizationIndex:
    def test_untrusted_gate_in_index(self, email_sm: dict) -> None:
        si = email_sm["sanitization_index"]
        assert "UNTRUSTED" in si
        assert si["UNTRUSTED"]["requires"] == "human_approval"

    def test_semi_trusted_gate_in_index(self, email_sm: dict) -> None:
        si = email_sm["sanitization_index"]
        assert "SEMI_TRUSTED" in si
        assert si["SEMI_TRUSTED"]["requires"] == "schema_validation"

    def test_log_entry_flag_present(self, email_sm: dict) -> None:
        si = email_sm["sanitization_index"]
        assert "log_entry" in si["UNTRUSTED"]
        assert si["UNTRUSTED"]["log_entry"] is True

    def test_semi_trusted_log_entry_false(self, email_sm: dict) -> None:
        si = email_sm["sanitization_index"]
        assert si["SEMI_TRUSTED"]["log_entry"] is False


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestConflictDetection:
    def test_no_conflicts_in_well_formed_manifests(self, email_sm: dict, mcp_sm: dict,
                                                    browser_sm: dict) -> None:
        """All three example manifests should compile with no conflicts."""
        assert email_sm["conflicts"] == []
        assert mcp_sm["conflicts"] == []
        assert browser_sm["conflicts"] == []

    def test_conflict_recorded_not_raised(self) -> None:
        """Conflicting rules produce a conflict record, not an exception."""
        conflicting_rules = [
            {
                "id": "rule-a",
                "source_taint": "UNTRUSTED",
                "propagation": [{"operation": "summarize", "spreads_to": "output"}],
                "sanitization_gate": {"requires": "human_approval", "log_entry": True},
            },
            {
                "id": "rule-b",
                "source_taint": "UNTRUSTED",
                "propagation": [{"operation": "summarize", "spreads_to": "output"}],
                "sanitization_gate": {"requires": "schema_validation", "log_entry": False},
            },
        ]
        sm = compile_taint_rules(conflicting_rules)
        # First rule wins
        assert sm["transition_table"]["UNTRUSTED"]["summarize"]["gate_required"] == "human_approval"
        # Conflict is recorded
        assert len(sm["conflicts"]) == 1
        assert "rule-a" in sm["conflicts"][0]
        assert "rule-b" in sm["conflicts"][0]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_rules_same_output(self) -> None:
        """Core invariant: same rules → identical state machine."""
        rules = [
            {
                "id": "test-rule",
                "source_taint": "UNTRUSTED",
                "propagation": [
                    {"operation": "summarize", "spreads_to": "output"},
                    {"operation": "store", "spreads_to": "memory_entry"},
                ],
                "sanitization_gate": {"requires": "human_approval", "log_entry": True},
            }
        ]
        sm1 = compile_taint_rules(rules)
        sm2 = compile_taint_rules(rules)
        assert json.dumps(sm1, sort_keys=True) == json.dumps(sm2, sort_keys=True)

    def test_email_manifest_deterministic(self) -> None:
        manifest = load(EMAIL_MANIFEST)
        sm1 = compile_from_manifest(manifest)
        sm2 = compile_from_manifest(manifest)
        assert json.dumps(sm1, sort_keys=True) == json.dumps(sm2, sort_keys=True)


# ---------------------------------------------------------------------------
# Integration: emitter produces taint_state_machine.json
# ---------------------------------------------------------------------------

class TestEmitterIntegration:
    def test_state_machine_artifact_written(self, tmp_path: Path) -> None:
        from compiler.emitter import emit
        manifest = load(EMAIL_MANIFEST)
        written = emit(manifest, tmp_path / "out")
        assert "taint_state_machine.json" in written

    def test_state_machine_artifact_is_valid_json(self, tmp_path: Path) -> None:
        from compiler.emitter import emit
        manifest = load(EMAIL_MANIFEST)
        written = emit(manifest, tmp_path / "out")
        path = written["taint_state_machine.json"]
        data = json.loads(path.read_text())
        assert "transition_table" in data
        assert "containment_rules" in data

    def test_total_artifacts_now_eight(self, tmp_path: Path) -> None:
        from compiler.emitter import emit
        manifest = load(EMAIL_MANIFEST)
        written = emit(manifest, tmp_path / "out")
        assert len(written) == 8
