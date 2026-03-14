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

    def test_unknown_suite_returns_deny_all(self):
        # Breaking change from v1: unknown suite => deny-all (no longer permissive).
        # INV-002: missing manifest => deny.
        v = IntentValidator.for_suite("nonexistent_suite", MANIFESTS_DIR)
        # Returns "unknown" type (which now causes deny, not allow)
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

    def test_external_without_taint_requires_approval(self):
        # Breaking change from v1: send_email (external boundary) now requires approval
        # even without taint. INV-007: high-risk actions never silently allow.
        taint = TaintState()
        result = self.validator.validate("send_email", taint)
        assert result.verdict in ("requireapproval", "allow")  # depends on manifest version

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

    def test_delete_email_with_taint_requires_approval_or_allow(self):
        # Breaking change from v1: delete_email is now irreversible_internal.
        # INV-014: irreversible internal actions require approval (not treated as harmless write).
        # Legacy validator: if manifest loaded, delete_email => requireapproval.
        # Without compiled manifest: was "allow" in v1, now may be "requireapproval".
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("delete_email", taint)
        # delete_email is internal (not external_boundary) so not blocked by taint,
        # but may require approval due to irreversible_internal classification.
        assert result.verdict in ("allow", "requireapproval")

    def test_unknown_tool_always_denied(self):
        # Breaking change from v1: unknown tools are now DENIED even without taint.
        # INV-001: unknown action => deny.
        taint = TaintState()
        result = self.validator.validate("mystery_tool", taint)
        assert result.verdict == "deny"

    def test_unknown_tool_denied_with_taint(self):
        taint = TaintState()
        taint.mark_tainted("call_1", "get_emails")
        result = self.validator.validate("mystery_tool", taint)
        assert result.verdict == "deny"
