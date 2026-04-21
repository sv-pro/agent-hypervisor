"""
test_taint_trigger.py — Phase 4 tests: Runtime Trigger-Based Profile Switching.

Coverage:
  1. SessionTaintTracker unit tests (signal tracking, monotonic escalation, clear).
  2. LinkingPolicyEngine comparison operators (_gte, _lte, _gt, _lt).
  3. evaluate_with_note() — returns (profile_id, note) tuple.
  4. Taint-triggered profile downgrade via resolve_manifest_for_call().
  5. Operator restore path (clear_taint + profile revert).
  6. Audit log: profile_switched events written to EventStore.
  7. REST API: GET/POST /ui/api/sessions/{id}/taint, /restore-profile, /taint (list).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
from agent_hypervisor.hypervisor.mcp_gateway.session_taint_tracker import (
    TAINT_LEVELS,
    SessionSignals,
    SessionTaintTracker,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_catalog_and_resolver(tmp_path: Path, profiles: list[dict]):
    """
    Build a ProfilesCatalog + SessionWorldResolver from scratch in tmp_path.
    Returns (catalog, resolver, manifest_paths).
    """
    import yaml
    from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
        ProfileEntry,
        ProfilesCatalog,
    )
    from agent_hypervisor.hypervisor.mcp_gateway.session_world_resolver import (
        SessionWorldResolver,
    )

    # Write minimal manifests
    manifest_paths = {}
    for p in profiles:
        m_path = tmp_path / f"{p['id']}.yaml"
        m_path.write_text(
            yaml.dump({
                "workflow_id": p["id"],
                "version": "1.0",
                "capabilities": p.get("capabilities", []),
            }),
            encoding="utf-8",
        )
        manifest_paths[p["id"]] = m_path

    # Build catalog index
    index = {
        "profiles": [
            {
                "id": p["id"],
                "description": p.get("description", ""),
                "path": str(manifest_paths[p["id"]]),
                "tags": p.get("tags", []),
            }
            for p in profiles
        ]
    }
    index_path = tmp_path / "profiles-index.yaml"
    index_path.write_text(yaml.dump(index), encoding="utf-8")

    catalog = ProfilesCatalog(index_path)

    # Default manifest = first profile
    default_path = manifest_paths[profiles[0]["id"]]
    resolver = SessionWorldResolver(default_path)

    return catalog, resolver, manifest_paths


# ============================================================
# 1. SessionTaintTracker unit tests
# ============================================================

class TestSessionTaintTracker:

    def test_get_context_auto_inits_session(self):
        tracker = SessionTaintTracker()
        ctx = tracker.get_context("s1")
        assert ctx["taint_level"] == "clean"
        assert ctx["tool_call_count"] == 0
        assert ctx["last_verdict"] == "allow"
        assert "session_age_s" in ctx

    def test_record_tool_call_increments_count(self):
        tracker = SessionTaintTracker()
        tracker.record_tool_call("s1", verdict="allow")
        tracker.record_tool_call("s1", verdict="deny")
        ctx = tracker.get_context("s1")
        assert ctx["tool_call_count"] == 2
        assert ctx["last_verdict"] == "deny"

    def test_escalate_taint_monotonic(self):
        tracker = SessionTaintTracker()
        # clean → elevated
        changed = tracker.escalate_taint("s1", "elevated")
        assert changed
        assert tracker.get_context("s1")["taint_level"] == "elevated"
        # elevated → high
        changed = tracker.escalate_taint("s1", "high")
        assert changed
        assert tracker.get_context("s1")["taint_level"] == "high"
        # high → elevated  (downgrade rejected)
        changed = tracker.escalate_taint("s1", "elevated")
        assert not changed
        assert tracker.get_context("s1")["taint_level"] == "high"
        # high → clean (downgrade rejected)
        changed = tracker.escalate_taint("s1", "clean")
        assert not changed

    def test_clear_taint_resets_to_clean(self):
        tracker = SessionTaintTracker()
        tracker.escalate_taint("s1", "high")
        assert tracker.get_context("s1")["taint_level"] == "high"
        cleared = tracker.clear_taint("s1")
        assert cleared
        assert tracker.get_context("s1")["taint_level"] == "clean"

    def test_clear_taint_returns_false_for_unknown_session(self):
        tracker = SessionTaintTracker()
        assert not tracker.clear_taint("nonexistent")

    def test_init_session_records_original_profile(self):
        tracker = SessionTaintTracker()
        tracker.init_session("s1", original_profile_id="email-assistant-v1")
        sig = tracker.get_signals("s1")
        assert sig is not None
        assert sig.original_profile_id == "email-assistant-v1"
        assert sig.current_profile_id == "email-assistant-v1"

    def test_note_profile_switch_updates_current(self):
        tracker = SessionTaintTracker()
        tracker.init_session("s1", original_profile_id="full-access")
        tracker.note_profile_switch("s1", "read-only")
        sig = tracker.get_signals("s1")
        assert sig.current_profile_id == "read-only"
        assert sig.original_profile_id == "full-access"

    def test_clear_taint_restores_original_profile_id(self):
        tracker = SessionTaintTracker()
        tracker.init_session("s1", original_profile_id="full-access")
        tracker.note_profile_switch("s1", "read-only")
        tracker.clear_taint("s1")
        sig = tracker.get_signals("s1")
        assert sig.current_profile_id == "full-access"

    def test_list_sessions(self):
        tracker = SessionTaintTracker()
        tracker.record_tool_call("s1")
        tracker.record_tool_call("s2")
        sessions = tracker.list_sessions()
        ids = {s["session_id"] for s in sessions}
        assert "s1" in ids
        assert "s2" in ids

    def test_remove_session(self):
        tracker = SessionTaintTracker()
        tracker.record_tool_call("s1")
        tracker.remove_session("s1")
        assert tracker.get_signals("s1") is None

    def test_session_age_increases(self):
        tracker = SessionTaintTracker()
        tracker.record_tool_call("s1")
        time.sleep(0.05)
        ctx = tracker.get_context("s1")
        assert ctx["session_age_s"] >= 0.0


# ============================================================
# 2. LinkingPolicyEngine — comparison operators
# ============================================================

class TestLinkingPolicyEngineComparisons:

    def test_gte_matches(self):
        engine = LinkingPolicyEngine([
            {"if": {"tool_call_count_gte": 5}, "then": {"profile_id": "restricted"}},
        ])
        assert engine.evaluate({"tool_call_count": 5}) == "restricted"
        assert engine.evaluate({"tool_call_count": 10}) == "restricted"
        assert engine.evaluate({"tool_call_count": 4}) is None

    def test_lte_matches(self):
        engine = LinkingPolicyEngine([
            {"if": {"session_age_s_lte": 60}, "then": {"profile_id": "new-session"}},
        ])
        assert engine.evaluate({"session_age_s": 30}) == "new-session"
        assert engine.evaluate({"session_age_s": 60}) == "new-session"
        assert engine.evaluate({"session_age_s": 61}) is None

    def test_gt_matches(self):
        engine = LinkingPolicyEngine([
            {"if": {"tool_call_count_gt": 10}, "then": {"profile_id": "heavy-user"}},
        ])
        assert engine.evaluate({"tool_call_count": 11}) == "heavy-user"
        assert engine.evaluate({"tool_call_count": 10}) is None

    def test_lt_matches(self):
        engine = LinkingPolicyEngine([
            {"if": {"session_age_s_lt": 10}, "then": {"profile_id": "fresh"}},
        ])
        assert engine.evaluate({"session_age_s": 9}) == "fresh"
        assert engine.evaluate({"session_age_s": 10}) is None

    def test_plain_equality_still_works(self):
        engine = LinkingPolicyEngine([
            {"if": {"taint_level": "high"}, "then": {"profile_id": "read-only"}},
        ])
        assert engine.evaluate({"taint_level": "high"}) == "read-only"
        assert engine.evaluate({"taint_level": "clean"}) is None

    def test_mixed_conditions(self):
        """All conditions must hold — mix of equality and comparison."""
        engine = LinkingPolicyEngine([
            {
                "if": {"taint_level": "high", "tool_call_count_gte": 3},
                "then": {"profile_id": "locked-down"},
            },
        ])
        # Both hold
        assert engine.evaluate({"taint_level": "high", "tool_call_count": 5}) == "locked-down"
        # taint_level holds but count is too low
        assert engine.evaluate({"taint_level": "high", "tool_call_count": 2}) is None
        # count holds but taint_level doesn't
        assert engine.evaluate({"taint_level": "clean", "tool_call_count": 5}) is None

    def test_comparison_with_non_numeric_context_does_not_match(self):
        engine = LinkingPolicyEngine([
            {"if": {"tool_call_count_gte": 5}, "then": {"profile_id": "r"}},
        ])
        # context value is a string (non-numeric) → no match
        assert engine.evaluate({"tool_call_count": "many"}) is None

    def test_missing_context_key_does_not_match(self):
        engine = LinkingPolicyEngine([
            {"if": {"tool_call_count_gte": 5}, "then": {"profile_id": "r"}},
        ])
        assert engine.evaluate({}) is None

    def test_default_rule_still_matches(self):
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "fallback"}},
        ])
        assert engine.evaluate({}) == "fallback"
        assert engine.evaluate({"taint_level": "high"}) == "fallback"


# ============================================================
# 3. evaluate_with_note()
# ============================================================

class TestEvaluateWithNote:

    def test_returns_none_when_no_match(self):
        engine = LinkingPolicyEngine([
            {"if": {"taint_level": "high"}, "then": {"profile_id": "r"}},
        ])
        result = engine.evaluate_with_note({"taint_level": "clean"})
        assert result is None

    def test_returns_profile_and_note(self):
        engine = LinkingPolicyEngine([
            {
                "if": {"taint_level": "high"},
                "then": {
                    "profile_id": "read-only",
                    "note": "Taint escalation — downgraded.",
                },
            },
        ])
        result = engine.evaluate_with_note({"taint_level": "high"})
        assert result is not None
        profile_id, note = result
        assert profile_id == "read-only"
        assert note == "Taint escalation — downgraded."

    def test_note_is_none_when_absent(self):
        engine = LinkingPolicyEngine([
            {"if": {"taint_level": "high"}, "then": {"profile_id": "read-only"}},
        ])
        result = engine.evaluate_with_note({"taint_level": "high"})
        assert result is not None
        _, note = result
        assert note is None

    def test_default_rule_with_note(self):
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "fallback", "note": "default profile"}},
        ])
        result = engine.evaluate_with_note({})
        assert result == ("fallback", "default profile")


# ============================================================
# 4 & 5. Taint-triggered downgrade + operator restore
# ============================================================

class TestResolveManifestForCall:
    """
    Tests for MCPGatewayState.resolve_manifest_for_call().

    We build a minimal gateway state with a linking-policy engine wired in
    and verify that a taint escalation causes the resolver to switch profiles.
    """

    def _make_state(self, tmp_path: Path):
        """
        Return (state, profiles_catalog) with two profiles:
          'full-access'  — default
          'read-only'    — activated when taint_level == "high"
        """
        from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import MCPGatewayState
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
            ProfileEntry,
            ProfilesCatalog,
        )
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import (
            LinkingPolicyEngine,
        )

        catalog, resolver, _ = _make_catalog_and_resolver(
            tmp_path,
            profiles=[
                {"id": "full-access"},
                {"id": "read-only"},
            ],
        )

        engine = LinkingPolicyEngine([
            {
                "if": {"taint_level": "high"},
                "then": {
                    "profile_id": "read-only",
                    "note": "Taint escalation — downgraded.",
                },
            },
        ])
        resolver.set_linking_policy(engine, catalog)

        full_access_path = tmp_path / "full-access.yaml"
        state = MCPGatewayState(manifest_path=full_access_path)
        # Wire the pre-built resolver into state (bypass the default one)
        state.resolver = resolver

        return state, catalog

    def test_clean_session_gets_default_manifest(self, tmp_path):
        state, catalog = self._make_state(tmp_path)
        manifest = state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        # No rule matched (taint_level is clean) → default manifest
        assert manifest.workflow_id == "full-access"

    def test_high_taint_triggers_profile_switch(self, tmp_path):
        state, catalog = self._make_state(tmp_path)
        # Escalate taint
        state.taint_tracker.escalate_taint("s1", "high")
        manifest = state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        assert manifest.workflow_id == "read-only"

    def test_profile_switch_recorded_in_tracker(self, tmp_path):
        state, catalog = self._make_state(tmp_path)
        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)

        sig = state.taint_tracker.get_signals("s1")
        assert sig is not None
        assert sig.current_profile_id == "read-only"

    def test_operator_restore_reverts_to_original(self, tmp_path):
        state, catalog = self._make_state(tmp_path)
        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)

        # Operator clears taint
        cleared = state.taint_tracker.clear_taint("s1")
        assert cleared

        sig = state.taint_tracker.get_signals("s1")
        assert sig.taint_level == "clean"
        assert sig.current_profile_id == "full-access"

        # Next call should now use the full-access manifest
        manifest = state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        assert manifest.workflow_id == "full-access"

    def test_tool_call_count_increments_on_each_call(self, tmp_path):
        state, catalog = self._make_state(tmp_path)
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        ctx = state.taint_tracker.get_context("s1")
        assert ctx["tool_call_count"] == 2


# ============================================================
# 6. Audit log: profile_switched events
# ============================================================

class TestAuditLogProfileSwitched:

    def test_profile_switched_event_written_to_event_store(self, tmp_path):
        """
        When a taint-triggered switch occurs and a control plane is wired,
        a profile_switched event must appear in the event store.
        """
        from agent_hypervisor.control_plane.event_store import EventStore
        from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import MCPGatewayState
        from agent_hypervisor.control_plane.domain import EVENT_TYPE_PROFILE_SWITCHED

        catalog, resolver, _ = _make_catalog_and_resolver(
            tmp_path,
            profiles=[
                {"id": "full-access"},
                {"id": "read-only"},
            ],
        )

        engine = LinkingPolicyEngine([
            {
                "if": {"taint_level": "high"},
                "then": {"profile_id": "read-only", "note": "Taint escalation."},
            },
        ])
        resolver.set_linking_policy(engine, catalog)

        # Create a minimal fake control plane with an event store
        event_store = EventStore()
        cp = MagicMock()
        cp.event_store = event_store

        full_access_path = tmp_path / "full-access.yaml"
        state = MCPGatewayState(manifest_path=full_access_path, control_plane=cp)
        state.resolver = resolver

        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)

        events = event_store.get_session_events("s1")
        profile_events = [e for e in events if e.type == EVENT_TYPE_PROFILE_SWITCHED]
        assert len(profile_events) == 1

        ev = profile_events[0]
        assert ev.payload["to_profile_id"] == "read-only"
        assert ev.payload["from_profile_id"] == "full-access"
        assert ev.payload["note"] == "Taint escalation."

    def test_no_duplicate_event_on_same_profile(self, tmp_path):
        """
        If the engine resolves the same profile on subsequent calls,
        no additional profile_switched event should be emitted.
        """
        from agent_hypervisor.control_plane.event_store import EventStore
        from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import MCPGatewayState
        from agent_hypervisor.control_plane.domain import EVENT_TYPE_PROFILE_SWITCHED

        catalog, resolver, _ = _make_catalog_and_resolver(
            tmp_path,
            profiles=[{"id": "full-access"}, {"id": "read-only"}],
        )
        engine = LinkingPolicyEngine([
            {"if": {"taint_level": "high"}, "then": {"profile_id": "read-only"}},
        ])
        resolver.set_linking_policy(engine, catalog)

        event_store = EventStore()
        cp = MagicMock()
        cp.event_store = event_store

        full_access_path = tmp_path / "full-access.yaml"
        state = MCPGatewayState(manifest_path=full_access_path, control_plane=cp)
        state.resolver = resolver

        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")

        # First call: switch fires
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)
        # Second call: profile already "read-only" — no second event
        state.resolve_manifest_for_call("s1", profiles_catalog=catalog)

        events = event_store.get_session_events("s1")
        profile_events = [e for e in events if e.type == EVENT_TYPE_PROFILE_SWITCHED]
        assert len(profile_events) == 1

    def test_restore_profile_writes_operator_restore_event(self, tmp_path):
        from agent_hypervisor.control_plane.event_store import EventStore
        from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import MCPGatewayState
        from agent_hypervisor.control_plane.domain import EVENT_TYPE_PROFILE_SWITCHED

        catalog, resolver, _ = _make_catalog_and_resolver(
            tmp_path,
            profiles=[{"id": "full-access"}, {"id": "read-only"}],
        )
        event_store = EventStore()
        cp = MagicMock()
        cp.event_store = event_store

        full_access_path = tmp_path / "full-access.yaml"
        state = MCPGatewayState(manifest_path=full_access_path, control_plane=cp)
        state.resolver = resolver

        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.note_profile_switch("s1", "read-only")

        # Simulate operator restore via event store directly
        from agent_hypervisor.control_plane.event_store import make_profile_switched
        sig = state.taint_tracker.get_signals("s1")
        state.taint_tracker.clear_taint("s1")
        event = make_profile_switched(
            session_id="s1",
            from_profile_id="read-only",
            to_profile_id="full-access",
            trigger="operator_restore",
            note="Operator cleared taint and restored original profile.",
            signals={},
        )
        event_store.append(event)

        events = event_store.get_session_events("s1")
        restore_events = [
            e for e in events
            if e.type == EVENT_TYPE_PROFILE_SWITCHED
            and e.payload.get("trigger") == "operator_restore"
        ]
        assert len(restore_events) == 1
        assert restore_events[0].payload["to_profile_id"] == "full-access"


# ============================================================
# 7. REST API tests
# ============================================================

def _build_test_client(tmp_path: Path):
    """
    Build a FastAPI TestClient with a gateway that has two profiles and
    a linking policy wired in, plus a mock control plane.
    """
    from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import MCPGatewayState
    from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
    from agent_hypervisor.control_plane.event_store import EventStore
    from agent_hypervisor.ui.router import create_ui_router
    from fastapi import FastAPI

    catalog, resolver, _ = _make_catalog_and_resolver(
        tmp_path,
        profiles=[{"id": "full-access"}, {"id": "read-only"}],
    )

    engine = LinkingPolicyEngine([
        {"if": {"taint_level": "high"}, "then": {"profile_id": "read-only"}},
    ])
    resolver.set_linking_policy(engine, catalog)

    event_store = EventStore()
    cp = MagicMock()
    cp.event_store = event_store

    full_access_path = tmp_path / "full-access.yaml"
    state = MCPGatewayState(manifest_path=full_access_path, control_plane=cp)
    state.resolver = resolver

    app = FastAPI()
    app.include_router(
        create_ui_router(
            gw_state=state,
            cp_state=cp,
            profiles_catalog=catalog,
        )
    )
    return TestClient(app), state, event_store


class TestTaintRestAPI:

    def test_get_taint_unknown_session_returns_404(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        resp = client.get("/ui/api/sessions/unknown-session/taint")
        assert resp.status_code == 404

    def test_get_taint_after_first_call_returns_signals(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        # Prime the tracker by getting context
        state.taint_tracker.record_tool_call("s1")
        resp = client.get("/ui/api/sessions/s1/taint")
        assert resp.status_code == 200
        data = resp.json()
        assert data["taint_level"] == "clean"
        assert data["tool_call_count"] == 1

    def test_post_taint_escalates_level(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        state.taint_tracker.record_tool_call("s1")
        resp = client.post("/ui/api/sessions/s1/taint", json={"level": "elevated"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "escalated"
        assert data["taint_level"] == "elevated"

    def test_post_taint_invalid_level_returns_400(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        resp = client.post("/ui/api/sessions/s1/taint", json={"level": "extreme"})
        assert resp.status_code == 400

    def test_post_taint_cannot_downgrade(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        state.taint_tracker.escalate_taint("s1", "high")
        resp = client.post("/ui/api/sessions/s1/taint", json={"level": "clean"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unchanged"
        assert data["taint_level"] == "high"

    def test_get_sessions_taint_list(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        state.taint_tracker.record_tool_call("s1")
        state.taint_tracker.record_tool_call("s2")
        resp = client.get("/ui/api/sessions/taint")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        ids = {s["session_id"] for s in data["sessions"]}
        assert "s1" in ids
        assert "s2" in ids

    def test_restore_profile_unknown_session_returns_404(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        resp = client.post("/ui/api/sessions/ghost/restore-profile")
        assert resp.status_code == 404

    def test_restore_profile_clears_taint_and_returns_200(self, tmp_path):
        client, state, _ = _build_test_client(tmp_path)
        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")
        state.taint_tracker.note_profile_switch("s1", "read-only")

        resp = client.post("/ui/api/sessions/s1/restore-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"
        assert data["taint_level"] == "clean"
        assert data["original_profile_id"] == "full-access"

    def test_restore_profile_writes_audit_event(self, tmp_path):
        from agent_hypervisor.control_plane.domain import EVENT_TYPE_PROFILE_SWITCHED

        client, state, event_store = _build_test_client(tmp_path)
        state.taint_tracker.init_session("s1", original_profile_id="full-access")
        state.taint_tracker.escalate_taint("s1", "high")
        state.taint_tracker.note_profile_switch("s1", "read-only")

        client.post("/ui/api/sessions/s1/restore-profile")

        events = event_store.get_session_events("s1")
        restore_events = [
            e for e in events
            if e.type == EVENT_TYPE_PROFILE_SWITCHED
        ]
        assert len(restore_events) == 1
        assert restore_events[0].payload["trigger"] == "operator_restore"
