"""Tests for the IntentValidator — manifest loading and validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ah_defense.intent_validator import IntentValidator
from ah_defense.taint_tracker import TaintState


MANIFESTS_DIR = Path(__file__).parent.parent / "ah_defense" / "manifests"


class TestManifestLoading:
    """Test that World Manifests load correctly."""

    def test_workspace_manifest_loads(self):
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        # Known external tool
        assert v.get_tool_type("send_email") == "external_side_effect"

    def test_workspace_read_only_tools(self):
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        assert v.get_tool_type("get_unread_emails") == "read_only"
        assert v.get_tool_type("search_emails") == "read_only"
        assert v.get_tool_type("get_day_calendar_events") == "read_only"
        assert v.get_tool_type("list_files") == "read_only"

    def test_workspace_internal_write_tools(self):
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        assert v.get_tool_type("delete_email") == "internal_write"
        assert v.get_tool_type("delete_file") == "internal_write"
        assert v.get_tool_type("create_file") == "internal_write"

    def test_workspace_external_tools(self):
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        assert v.get_tool_type("send_email") == "external_side_effect"
        assert v.get_tool_type("create_calendar_event") == "external_side_effect"
        assert v.get_tool_type("share_file") == "external_side_effect"

    def test_travel_manifest_loads(self):
        v = IntentValidator.for_suite("travel", MANIFESTS_DIR)
        assert v.get_tool_type("reserve_hotel") == "external_side_effect"
        assert v.get_tool_type("get_all_hotels_in_city") == "read_only"

    def test_banking_manifest_loads(self):
        v = IntentValidator.for_suite("banking", MANIFESTS_DIR)
        assert v.get_tool_type("send_money") == "external_side_effect"
        assert v.get_tool_type("get_balance") == "read_only"

    def test_slack_manifest_loads(self):
        v = IntentValidator.for_suite("slack", MANIFESTS_DIR)
        assert v.get_tool_type("send_channel_message") == "external_side_effect"
        assert v.get_tool_type("read_channel_messages") == "read_only"

    def test_unknown_suite_returns_permissive(self):
        v = IntentValidator.for_suite("nonexistent_suite", MANIFESTS_DIR)
        # Should return unknown for all tools
        assert v.get_tool_type("any_tool") == "unknown"

    def test_unknown_tool_returns_unknown(self):
        v = IntentValidator.for_suite("workspace", MANIFESTS_DIR)
        assert v.get_tool_type("mystery_tool_xyz") == "unknown"


class TestValidation:
    """Test the validation logic."""

    def setup_method(self):
        self.validator = IntentValidator.for_suite("workspace", MANIFESTS_DIR)

    def test_allow_read_only_without_taint(self):
        taint = TaintState()
        result = self.validator.validate("search_emails", taint)
        assert result.verdict == "allow"

    def test_allow_read_only_with_taint(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "some_tool")
        result = self.validator.validate("search_emails", taint)
        assert result.verdict == "allow"

    def test_allow_external_without_taint(self):
        taint = TaintState()
        result = self.validator.validate("send_email", taint)
        assert result.verdict == "allow"

    def test_deny_external_with_taint(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("send_email", taint)
        assert result.verdict == "deny"
        assert "TaintContainmentLaw" in result.reason

    def test_deny_includes_tool_name(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("send_email", taint)
        assert "send_email" in result.reason

    def test_allow_internal_write_with_taint(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("delete_email", taint)
        assert result.verdict == "allow"

    def test_unknown_tool_treated_as_external(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("mystery_tool", taint)
        # Unknown tools with taint should be denied (conservative)
        assert result.verdict == "deny"
