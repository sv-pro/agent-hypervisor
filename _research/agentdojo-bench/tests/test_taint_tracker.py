"""Tests for the TaintState — taint propagation and containment law."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ah_defense.taint_tracker import TaintState


class TestTaintState:
    """Test taint state initialization and marking."""

    def test_initial_state_not_tainted(self):
        state = TaintState()
        assert not state.is_tainted
        assert len(state.tainted_call_ids) == 0

    def test_mark_tainted_sets_flag(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        assert state.is_tainted

    def test_mark_tainted_records_call_id(self):
        state = TaintState()
        state.mark_tainted("call_abc", "search_files")
        assert "call_abc" in state.tainted_call_ids

    def test_multiple_marks_accumulate(self):
        state = TaintState()
        state.mark_tainted("call_1", "get_emails")
        state.mark_tainted("call_2", "search_files")
        assert "call_1" in state.tainted_call_ids
        assert "call_2" in state.tainted_call_ids

    def test_reset_clears_state(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        state.reset()
        assert not state.is_tainted
        assert len(state.tainted_call_ids) == 0


class TestTaintContainmentLaw:
    """Test the core TaintContainmentLaw: tainted context + external tool = blocked."""

    def test_no_taint_allows_external(self):
        state = TaintState()
        # Without taint, external tools are allowed
        assert not state.check_tool_call("send_email", "external_side_effect")

    def test_taint_blocks_external(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        # With taint, external tools are BLOCKED
        assert state.check_tool_call("send_email", "external_side_effect")

    def test_taint_allows_read_only(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        # Read-only tools remain allowed even with taint
        assert not state.check_tool_call("search_emails", "read_only")

    def test_taint_allows_internal_write(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        # Internal writes are allowed even with taint
        assert not state.check_tool_call("delete_email", "internal_write")

    def test_taint_blocks_unknown_tool_type(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        # Unknown tools are treated as external (conservative)
        # (This is handled in IntentValidator, not TaintState directly)
        assert state.check_tool_call("mystery_tool", "external_side_effect")

    def test_audit_log_records_blocks(self):
        state = TaintState()
        state.mark_tainted("call_001", "get_emails")
        state.check_tool_call("send_email", "external_side_effect")
        log = state.get_audit_log()
        block_events = [e for e in log if e["event"] == "taint_block"]
        assert len(block_events) == 1
        assert block_events[0]["tool_name"] == "send_email"
