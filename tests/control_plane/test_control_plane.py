"""
test_control_plane.py — Invariant and behavioral tests for the control plane.

Test groups:
  1. Domain: Session, ActionApproval, SessionOverlay, WorldStateView
  2. SessionStore: lifecycle, state transitions, overlay tracking
  3. EventStore: append-only, ordering, filtering
  4. ApprovalService: fingerprint binding, TTL, world isolation
  5. OverlayService: attach/detach, expiry, session isolation
  6. WorldStateResolver: determinism, overlay application, base manifest unchanged
  7. Integration: full approval + overlay scenario

Import path: tests use direct module paths (pythonpath = src/agent_hypervisor).
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agent_hypervisor.control_plane.domain import (
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    APPROVAL_STATUS_EXPIRED,
    APPROVAL_STATUS_PENDING,
    SESSION_MODE_BACKGROUND,
    SESSION_MODE_INTERACTIVE,
    SESSION_STATE_ACTIVE,
    SESSION_STATE_CLOSED,
    SESSION_STATE_WAITING_APPROVAL,
    OverlayChanges,
    compute_action_fingerprint,
)
from agent_hypervisor.control_plane.session_store import SessionStore
from agent_hypervisor.control_plane.event_store import (
    EventStore,
    make_session_created,
    make_tool_call,
    make_approval_requested,
    make_overlay_attached,
)
from agent_hypervisor.control_plane.approval_service import ApprovalService
from agent_hypervisor.control_plane.overlay_service import OverlayService
from agent_hypervisor.control_plane.world_state_resolver import WorldStateResolver, world_state_to_manifest_dict


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_store():
    return SessionStore()


@pytest.fixture
def event_store():
    return EventStore()


@pytest.fixture
def approval_svc():
    return ApprovalService(default_ttl_seconds=60)


@pytest.fixture
def overlay_svc():
    return OverlayService()


@pytest.fixture
def resolver(session_store, overlay_svc):
    return WorldStateResolver(session_store, overlay_svc)


@pytest.fixture
def session(session_store):
    return session_store.create(manifest_id="test-manifest-v1", principal="test-user")


# ---------------------------------------------------------------------------
# Group 1: Domain model
# ---------------------------------------------------------------------------

class TestDomain:
    def test_compute_fingerprint_is_deterministic(self):
        fp1 = compute_action_fingerprint("send_email", {"to": "a@b.com", "body": "hi"})
        fp2 = compute_action_fingerprint("send_email", {"to": "a@b.com", "body": "hi"})
        assert fp1 == fp2

    def test_fingerprint_differs_for_different_args(self):
        fp1 = compute_action_fingerprint("send_email", {"to": "a@b.com"})
        fp2 = compute_action_fingerprint("send_email", {"to": "b@c.com"})
        assert fp1 != fp2

    def test_fingerprint_differs_for_different_tools(self):
        fp1 = compute_action_fingerprint("read_file", {"path": "/tmp/x"})
        fp2 = compute_action_fingerprint("write_file", {"path": "/tmp/x"})
        assert fp1 != fp2

    def test_fingerprint_is_short_hex(self):
        fp = compute_action_fingerprint("tool", {"k": "v"})
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_overlay_changes_defaults_are_empty(self):
        changes = OverlayChanges()
        assert changes.reveal_tools == []
        assert changes.hide_tools == []
        assert changes.widen_scope == {}
        assert changes.narrow_scope == {}

    def test_overlay_changes_roundtrip(self):
        changes = OverlayChanges(
            reveal_tools=["write_file"],
            hide_tools=["send_email"],
            widen_scope={"read_file": {"paths": ["/*"]}},
        )
        d = changes.to_dict()
        restored = OverlayChanges.from_dict(d)
        assert restored.reveal_tools == ["write_file"]
        assert restored.hide_tools == ["send_email"]
        assert restored.widen_scope == {"read_file": {"paths": ["/*"]}}


# ---------------------------------------------------------------------------
# Group 2: SessionStore
# ---------------------------------------------------------------------------

class TestSessionStore:
    def test_create_returns_session(self, session_store):
        s = session_store.create(manifest_id="m1")
        assert s.session_id
        assert s.manifest_id == "m1"
        assert s.mode == SESSION_MODE_BACKGROUND
        assert s.state == SESSION_STATE_ACTIVE
        assert s.overlay_ids == []

    def test_create_with_explicit_id(self, session_store):
        sid = str(uuid.uuid4())
        s = session_store.create(manifest_id="m1", session_id=sid)
        assert s.session_id == sid

    def test_create_duplicate_id_raises(self, session_store):
        sid = str(uuid.uuid4())
        session_store.create(manifest_id="m1", session_id=sid)
        with pytest.raises(ValueError, match="already exists"):
            session_store.create(manifest_id="m1", session_id=sid)

    def test_get_returns_none_for_unknown(self, session_store):
        assert session_store.get("no-such-session") is None

    def test_require_raises_for_unknown(self, session_store):
        with pytest.raises(KeyError):
            session_store.require("no-such-session")

    def test_transition_state(self, session_store, session):
        updated = session_store.transition_state(session.session_id, SESSION_STATE_WAITING_APPROVAL)
        assert updated.state == SESSION_STATE_WAITING_APPROVAL

    def test_close_marks_closed(self, session_store, session):
        closed = session_store.close(session.session_id)
        assert closed.state == SESSION_STATE_CLOSED

    def test_set_mode_interactive(self, session_store, session):
        updated = session_store.set_mode(session.session_id, SESSION_MODE_INTERACTIVE)
        assert updated.mode == SESSION_MODE_INTERACTIVE

    def test_list_filters_by_state(self, session_store):
        s1 = session_store.create(manifest_id="m1")
        s2 = session_store.create(manifest_id="m1")
        session_store.close(s2.session_id)
        active = session_store.list(state=SESSION_STATE_ACTIVE)
        closed = session_store.list(state=SESSION_STATE_CLOSED)
        assert s1.session_id in [s.session_id for s in active]
        assert s2.session_id in [s.session_id for s in closed]
        assert s2.session_id not in [s.session_id for s in active]

    def test_attach_detach_overlay_ids(self, session_store, session):
        oid = "overlay-1"
        session_store.attach_overlay(session.session_id, oid)
        s = session_store.get(session.session_id)
        assert oid in s.overlay_ids

        session_store.detach_overlay(session.session_id, oid)
        s = session_store.get(session.session_id)
        assert oid not in s.overlay_ids

    def test_attach_overlay_idempotent(self, session_store, session):
        oid = "overlay-1"
        session_store.attach_overlay(session.session_id, oid)
        session_store.attach_overlay(session.session_id, oid)  # second call is no-op
        s = session_store.get(session.session_id)
        assert s.overlay_ids.count(oid) == 1


# ---------------------------------------------------------------------------
# Group 3: EventStore
# ---------------------------------------------------------------------------

class TestEventStore:
    def test_append_and_retrieve(self, event_store, session):
        event = make_session_created(
            session.session_id, session.manifest_id, session.mode
        )
        event_store.append(event)
        events = event_store.get_session_events(session.session_id)
        assert len(events) == 1
        assert events[0].event_id == event.event_id

    def test_duplicate_event_id_raises(self, event_store, session):
        e = make_session_created(session.session_id, "m1", "background")
        event_store.append(e)
        with pytest.raises(ValueError, match="Duplicate event_id"):
            event_store.append(e)

    def test_filter_by_type(self, event_store, session):
        sid = session.session_id
        event_store.append(make_session_created(sid, "m1", "background"))
        event_store.append(make_tool_call(sid, "read_file", "allow"))
        event_store.append(make_tool_call(sid, "send_email", "deny"))

        tool_events = event_store.get_session_events(sid, event_type="tool_call")
        assert len(tool_events) == 2
        session_events = event_store.get_session_events(sid, event_type="session_created")
        assert len(session_events) == 1

    def test_events_ordered_by_append_order(self, event_store, session):
        sid = session.session_id
        for tool in ["a", "b", "c"]:
            event_store.append(make_tool_call(sid, tool, "allow"))
        events = event_store.get_session_events(sid)
        tools = [e.payload["tool_name"] for e in events]
        assert tools == ["a", "b", "c"]

    def test_get_by_event_id(self, event_store, session):
        e = make_tool_call(session.session_id, "read_file", "allow")
        event_store.append(e)
        assert event_store.get(e.event_id) is e

    def test_count(self, event_store, session):
        sid = session.session_id
        assert event_store.count(sid) == 0
        event_store.append(make_tool_call(sid, "read_file", "allow"))
        assert event_store.count(sid) == 1
        assert event_store.count() == 1


# ---------------------------------------------------------------------------
# Group 4: ApprovalService — action fingerprint binding, TTL, world isolation
# ---------------------------------------------------------------------------

class TestApprovalService:
    def test_request_creates_pending_approval(self, approval_svc, session):
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "admin@example.com"},
            requested_by="agent",
        )
        assert approval.status == APPROVAL_STATUS_PENDING
        assert approval.tool_name == "send_email"
        assert approval.approval_id

    def test_approval_bound_to_fingerprint(self, approval_svc, session):
        """An approval applies only to the exact action fingerprint."""
        args = {"to": "admin@example.com", "body": "hello"}
        approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments=args,
            requested_by="agent",
        )
        # Same tool, same args → approved
        assert approval_svc.is_action_approved(
            session.session_id, "send_email", args
        )
        # Same tool, different args → NOT approved
        assert not approval_svc.is_action_approved(
            session.session_id, "send_email", {"to": "other@example.com"}
        )
        # Different tool → NOT approved
        assert not approval_svc.is_action_approved(
            session.session_id, "read_file", args
        )

    def test_approval_does_not_change_visible_tools(self, approval_svc, session,
                                                     session_store, overlay_svc, resolver):
        """An action approval must not affect the session's visible tool world."""
        base_tools = ["read_file", "send_email"]

        view_before = resolver.resolve(
            session.session_id, base_tools
        )
        tools_before = list(view_before.visible_tools)

        # Request and allow an approval
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "x@y.com"},
            requested_by="agent",
        )
        approval_svc.resolve(approval.approval_id, APPROVAL_STATUS_ALLOWED, "operator")

        # World must be identical after approval
        view_after = resolver.resolve(session.session_id, base_tools)
        assert view_after.visible_tools == tools_before

    def test_resolve_allowed(self, approval_svc, session):
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="read_file",
            arguments={"path": "/tmp/x"},
            requested_by="agent",
        )
        resolved = approval_svc.resolve(
            approval.approval_id, APPROVAL_STATUS_ALLOWED, "operator"
        )
        assert resolved.status == APPROVAL_STATUS_ALLOWED
        assert resolved.resolved_by == "operator"

    def test_resolve_denied(self, approval_svc, session):
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="read_file",
            arguments={"path": "/tmp/x"},
            requested_by="agent",
        )
        resolved = approval_svc.resolve(
            approval.approval_id, APPROVAL_STATUS_DENIED, "operator"
        )
        assert resolved.status == APPROVAL_STATUS_DENIED

    def test_resolve_already_resolved_raises(self, approval_svc, session):
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="read_file",
            arguments={},
            requested_by="agent",
        )
        approval_svc.resolve(approval.approval_id, APPROVAL_STATUS_ALLOWED, "op")
        with pytest.raises(RuntimeError, match="already resolved"):
            approval_svc.resolve(approval.approval_id, APPROVAL_STATUS_DENIED, "op")

    def test_expired_approval_is_not_valid(self, session):
        """An expired approval must not be treated as authorized."""
        svc = ApprovalService(default_ttl_seconds=0)
        approval = svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "x@y.com"},
            requested_by="agent",
            ttl_seconds=0,  # no TTL / empty expires_at
        )
        # No TTL means no expiry; valid pending
        assert approval.is_valid()
        assert svc.is_action_approved(session.session_id, "send_email", {"to": "x@y.com"})

    def test_expired_approval_resolves_as_denied(self, session):
        """Resolving an expired approval always yields denied status."""
        svc = ApprovalService(default_ttl_seconds=1)
        # Create an approval with a past expiry
        approval = svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "x@y.com"},
            requested_by="agent",
        )
        # Manually backdate the expiry to simulate elapsed time
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        approval.expires_at = past

        # Resolving with ALLOWED should be overridden to DENIED due to expiry
        resolved = svc.resolve(approval.approval_id, APPROVAL_STATUS_ALLOWED, "operator")
        assert resolved.status == APPROVAL_STATUS_DENIED

    def test_check_expired_marks_stale(self, session):
        """check_expired() should mark pending past-expiry approvals as expired."""
        svc = ApprovalService(default_ttl_seconds=300)
        approval = svc.request_approval(
            session_id=session.session_id,
            tool_name="read_file",
            arguments={},
            requested_by="agent",
        )
        # Backdate expiry
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        approval.expires_at = past

        expired = svc.check_expired()
        assert len(expired) == 1
        assert expired[0].status == APPROVAL_STATUS_EXPIRED

    def test_list_pending_by_session(self, approval_svc, session_store):
        s1 = session_store.create(manifest_id="m1")
        s2 = session_store.create(manifest_id="m1")
        approval_svc.request_approval(s1.session_id, "read_file", {}, "agent")
        approval_svc.request_approval(s2.session_id, "read_file", {}, "agent")

        pending_s1 = approval_svc.list_pending(session_id=s1.session_id)
        assert len(pending_s1) == 1
        assert pending_s1[0].session_id == s1.session_id

    def test_event_emitted_on_request(self, approval_svc, event_store, session):
        approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "a@b.com"},
            requested_by="agent",
            event_store=event_store,
        )
        events = event_store.get_session_events(
            session.session_id, event_type="approval_requested"
        )
        assert len(events) == 1
        assert events[0].payload["tool_name"] == "send_email"

    def test_event_emitted_on_resolve(self, approval_svc, event_store, session):
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="read_file",
            arguments={},
            requested_by="agent",
            event_store=event_store,
        )
        approval_svc.resolve(
            approval.approval_id, APPROVAL_STATUS_ALLOWED, "op", event_store=event_store
        )
        events = event_store.get_session_events(
            session.session_id, event_type="approval_resolved"
        )
        assert len(events) == 1
        assert events[0].decision == APPROVAL_STATUS_ALLOWED


# ---------------------------------------------------------------------------
# Group 5: OverlayService
# ---------------------------------------------------------------------------

class TestOverlayService:
    def test_attach_creates_overlay(self, overlay_svc, session):
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="operator",
            changes=OverlayChanges(reveal_tools=["write_file"]),
        )
        assert overlay.overlay_id
        assert overlay.is_active()
        assert overlay.changes.reveal_tools == ["write_file"]

    def test_detach_removes_from_active(self, overlay_svc, session):
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="operator",
        )
        assert overlay.is_active()
        result = overlay_svc.detach(overlay.overlay_id)
        assert result is True
        assert not overlay.is_active()
        active = overlay_svc.get_active_overlays(session.session_id)
        assert overlay.overlay_id not in [o.overlay_id for o in active]

    def test_detach_unknown_returns_false(self, overlay_svc):
        assert overlay_svc.detach("no-such-overlay") is False

    def test_detach_already_detached_returns_false(self, overlay_svc, session):
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
        )
        overlay_svc.detach(overlay.overlay_id)
        assert overlay_svc.detach(overlay.overlay_id) is False

    def test_expired_overlay_not_in_active(self, overlay_svc, session):
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            ttl_seconds=60,
        )
        # Backdate expiry
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        overlay.expires_at = past

        active = overlay_svc.get_active_overlays(session.session_id)
        assert overlay.overlay_id not in [o.overlay_id for o in active]

    def test_session_isolation(self, overlay_svc, session_store):
        s1 = session_store.create(manifest_id="m1")
        s2 = session_store.create(manifest_id="m1")
        overlay_svc.attach(
            session_id=s1.session_id,
            parent_manifest_id="m1",
            created_by="op",
        )
        # s2 should have no active overlays
        assert overlay_svc.get_active_overlays(s2.session_id) == []

    def test_multiple_overlays_ordered_by_creation(self, overlay_svc, session):
        o1 = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["tool_a"]),
        )
        o2 = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["tool_b"]),
        )
        active = overlay_svc.get_active_overlays(session.session_id)
        ids = [o.overlay_id for o in active]
        assert ids.index(o1.overlay_id) < ids.index(o2.overlay_id)

    def test_event_emitted_on_attach(self, overlay_svc, event_store, session):
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["write_file"]),
            event_store=event_store,
        )
        events = event_store.get_session_events(
            session.session_id, event_type="overlay_attached"
        )
        assert len(events) == 1

    def test_session_store_updated_on_attach_detach(
        self, overlay_svc, session_store, session
    ):
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            session_store=session_store,
        )
        s = session_store.get(session.session_id)
        assert overlay.overlay_id in s.overlay_ids

        overlay_svc.detach(overlay.overlay_id, session_store=session_store)
        s = session_store.get(session.session_id)
        assert overlay.overlay_id not in s.overlay_ids


# ---------------------------------------------------------------------------
# Group 6: WorldStateResolver — determinism, overlay application, base unchanged
# ---------------------------------------------------------------------------

class TestWorldStateResolver:
    BASE_TOOLS = ["read_file", "send_email"]
    BASE_CONSTRAINTS = {
        "read_file": {"paths": ["/safe/*"]},
    }

    def test_resolver_with_no_overlays(self, resolver, session):
        view = resolver.resolve(session.session_id, self.BASE_TOOLS, self.BASE_CONSTRAINTS)
        assert set(view.visible_tools) == set(self.BASE_TOOLS)
        assert view.active_overlay_ids == []
        assert view.manifest_id == session.manifest_id
        assert view.mode == SESSION_MODE_BACKGROUND

    def test_resolver_is_deterministic(self, resolver, session):
        view1 = resolver.resolve(session.session_id, self.BASE_TOOLS)
        view2 = resolver.resolve(session.session_id, self.BASE_TOOLS)
        assert view1.visible_tools == view2.visible_tools
        assert view1.active_overlay_ids == view2.active_overlay_ids

    def test_overlay_can_reveal_hidden_tool(
        self, resolver, session, overlay_svc, session_store
    ):
        """An overlay can add a tool not in the base manifest."""
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["write_file"]),
            session_store=session_store,
        )
        view = resolver.resolve(session.session_id, self.BASE_TOOLS)
        assert "write_file" in view.visible_tools
        assert len(view.active_overlay_ids) == 1

    def test_overlay_can_hide_existing_tool(
        self, resolver, session, overlay_svc, session_store
    ):
        """An overlay can remove a tool that is in the base manifest."""
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(hide_tools=["send_email"]),
            session_store=session_store,
        )
        view = resolver.resolve(session.session_id, self.BASE_TOOLS)
        assert "send_email" not in view.visible_tools
        assert "read_file" in view.visible_tools

    def test_overlay_detachment_restores_world(
        self, resolver, session, overlay_svc, session_store
    ):
        """After detaching an overlay, the world reverts to base manifest state."""
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["write_file"]),
            session_store=session_store,
        )
        view_with = resolver.resolve(session.session_id, self.BASE_TOOLS)
        assert "write_file" in view_with.visible_tools

        overlay_svc.detach(overlay.overlay_id, session_store=session_store)

        view_without = resolver.resolve(session.session_id, self.BASE_TOOLS)
        assert "write_file" not in view_without.visible_tools
        assert set(view_without.visible_tools) == set(self.BASE_TOOLS)

    def test_base_manifest_tools_unchanged_after_overlay(
        self, resolver, session, overlay_svc, session_store
    ):
        """The base_tools list is never mutated by the resolver."""
        base_tools_original = list(self.BASE_TOOLS)
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(
                reveal_tools=["write_file"],
                hide_tools=["send_email"],
            ),
            session_store=session_store,
        )
        base_copy = list(self.BASE_TOOLS)
        resolver.resolve(session.session_id, base_copy)
        # base_copy must be unchanged (resolver must not mutate it)
        assert base_copy == base_tools_original

    def test_narrow_scope_wins_over_widen_scope(
        self, resolver, session, overlay_svc, session_store
    ):
        """When two overlays conflict, narrow_scope always takes precedence."""
        # First overlay widens read_file to all paths
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(widen_scope={"read_file": {"paths": ["/*"]}}),
            session_store=session_store,
        )
        # Second overlay narrows back to specific path
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(narrow_scope={"read_file": {"paths": ["/safe/*"]}}),
            session_store=session_store,
        )
        view = resolver.resolve(
            session.session_id, self.BASE_TOOLS, self.BASE_CONSTRAINTS
        )
        # narrow_scope should win: paths are ["/safe/*"]
        assert view.active_constraints["read_file"]["paths"] == ["/safe/*"]

    def test_resolver_unknown_session_raises(self, resolver):
        with pytest.raises(KeyError):
            resolver.resolve("no-such-session", [])

    def test_world_state_to_manifest_dict(self, resolver, session):
        view = resolver.resolve(session.session_id, self.BASE_TOOLS, self.BASE_CONSTRAINTS)
        manifest_dict = world_state_to_manifest_dict(view)
        assert "workflow_id" in manifest_dict
        assert "capabilities" in manifest_dict
        tool_names = [c["tool"] for c in manifest_dict["capabilities"]]
        assert set(tool_names) == set(self.BASE_TOOLS)

    def test_mode_reflected_in_view(self, session_store, overlay_svc):
        resolver = WorldStateResolver(session_store, overlay_svc)
        s = session_store.create(manifest_id="m1")
        session_store.set_mode(s.session_id, SESSION_MODE_INTERACTIVE)
        view = resolver.resolve(s.session_id, ["read_file"])
        assert view.mode == SESSION_MODE_INTERACTIVE


# ---------------------------------------------------------------------------
# Group 7: Integration — approval + overlay scenario
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_approval_then_overlay_scenario(
        self,
        session_store,
        event_store,
        approval_svc,
        overlay_svc,
    ):
        """
        Scenario:
        1. Session starts in background mode.
        2. Agent requests send_email approval.
        3. Operator approves (once).
        4. Operator attaches overlay to interactive session.
        5. World state reflects overlay.
        6. Base manifest is unchanged throughout.
        """
        resolver = WorldStateResolver(session_store, overlay_svc)
        base_tools = ["read_file", "send_email"]

        # Step 1: session starts
        session = session_store.create(manifest_id="email-assistant-v1", principal="agent")
        event_store.append(
            make_session_created(session.session_id, session.manifest_id, session.mode)
        )
        assert session.mode == SESSION_MODE_BACKGROUND

        # Step 2: agent requests approval for send_email
        approval = approval_svc.request_approval(
            session_id=session.session_id,
            tool_name="send_email",
            arguments={"to": "ceo@corp.com", "subject": "Q1 Results"},
            requested_by="agent",
            rationale="Agent wants to send board update",
            event_store=event_store,
        )
        session_store.transition_state(session.session_id, SESSION_STATE_WAITING_APPROVAL)
        assert approval.status == APPROVAL_STATUS_PENDING

        # Step 3: operator approves
        approval_svc.resolve(
            approval.approval_id, APPROVAL_STATUS_ALLOWED, "alice@corp.com",
            event_store=event_store
        )
        session_store.transition_state(session.session_id, SESSION_STATE_ACTIVE)

        # Approval did NOT widen the world
        view_after_approval = resolver.resolve(session.session_id, base_tools)
        assert "send_email" in view_after_approval.visible_tools  # was already there
        assert "write_file" not in view_after_approval.visible_tools  # still absent

        # Step 4: operator attaches overlay (switch to interactive)
        session_store.set_mode(session.session_id, SESSION_MODE_INTERACTIVE)
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="alice@corp.com",
            changes=OverlayChanges(reveal_tools=["write_file"]),
            session_store=session_store,
            event_store=event_store,
        )

        # Step 5: world state now includes write_file
        view_with_overlay = resolver.resolve(session.session_id, base_tools)
        assert "write_file" in view_with_overlay.visible_tools
        assert overlay.overlay_id in view_with_overlay.active_overlay_ids
        assert view_with_overlay.mode == SESSION_MODE_INTERACTIVE

        # Step 6: base manifest tools list is still just the original two
        assert set(base_tools) == {"read_file", "send_email"}  # not mutated

        # Audit log reflects all events
        all_events = event_store.get_session_events(session.session_id)
        event_types = [e.type for e in all_events]
        assert "session_created" in event_types
        assert "approval_requested" in event_types
        assert "approval_resolved" in event_types
        assert "overlay_attached" in event_types

    def test_overlay_detach_restores_world_in_integration(
        self, session_store, overlay_svc
    ):
        resolver = WorldStateResolver(session_store, overlay_svc)
        base_tools = ["read_file"]
        session = session_store.create(manifest_id="read-only-v1")

        # Attach then detach
        overlay = overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id=session.manifest_id,
            created_by="op",
            changes=OverlayChanges(reveal_tools=["write_file"]),
            session_store=session_store,
        )
        assert "write_file" in resolver.resolve(session.session_id, base_tools).visible_tools

        overlay_svc.detach(overlay.overlay_id, session_store=session_store)
        assert "write_file" not in resolver.resolve(session.session_id, base_tools).visible_tools

    def test_invalid_overlay_input_fails_closed(self, overlay_svc, session_store):
        """
        An overlay with invalid input should not silently succeed.
        Duplicate overlay_id must raise, not silently ignore.
        """
        session = session_store.create(manifest_id="m1")
        oid = str(uuid.uuid4())
        overlay_svc.attach(
            session_id=session.session_id,
            parent_manifest_id="m1",
            created_by="op",
            overlay_id=oid,
        )
        with pytest.raises(ValueError, match="already exists"):
            overlay_svc.attach(
                session_id=session.session_id,
                parent_manifest_id="m1",
                created_by="op",
                overlay_id=oid,  # duplicate
            )
