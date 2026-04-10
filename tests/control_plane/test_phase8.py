"""
test_phase8.py — Multi-scope approval system tests (Phase 8).

Covers:
  - Domain: ApprovalScope constants, ScopedVerdict, ParticipantRegistration
  - Domain: ActionApproval.scoped_verdicts field
  - ParticipantRegistry: register, unregister, list, upsert
  - ApprovalService.respond(): one_off allow creates fingerprint entry
  - ApprovalService.respond(): session allow creates overlay via overlay_service
  - ApprovalService.respond(): idempotent (same scope twice → no double effect)
  - ApprovalService.respond(): expired approval → deny even if verdicts arrive
  - Mixed verdicts: one_off allow + session deny → proceeds, no overlay
  - Status transitions: pending → partially_resolved → resolved
  - API: POST /control/participants
  - API: DELETE /control/participants/{session_id}
  - API: GET /control/participants
  - API: PATCH /control/approvals/{id}/respond with scoped verdicts
  - API: full round-trip — ask → broadcast → respond → unblocked
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_hypervisor.control_plane.api import ControlPlaneState, create_control_plane_app
from agent_hypervisor.control_plane.approval_broadcaster import ApprovalBroadcaster
from agent_hypervisor.control_plane.approval_service import ApprovalService
from agent_hypervisor.control_plane.domain import (
    APPROVAL_SCOPE_ONE_OFF,
    APPROVAL_SCOPE_SESSION,
    APPROVAL_SCOPE_WORLD,
    APPROVAL_STATUS_EXPIRED,
    APPROVAL_STATUS_PARTIALLY_RESOLVED,
    APPROVAL_STATUS_PENDING,
    APPROVAL_STATUS_RESOLVED,
    ActionApproval,
    ParticipantRegistration,
    ScopedVerdict,
)
from agent_hypervisor.control_plane.overlay_service import OverlayService
from agent_hypervisor.control_plane.participant_registry import ParticipantRegistry
from agent_hypervisor.control_plane.session_store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_expired_approval(svc: ApprovalService) -> ActionApproval:
    """Create a pending approval that has already expired."""
    approval = svc.request_approval(
        session_id="sess-x",
        tool_name="do_thing",
        arguments={"x": 1},
        requested_by="agent",
        ttl_seconds=1,
    )
    # Backdate the expiry.
    approval.expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat()
    return approval


def _sv(scope: str, verdict: str, pid: str = "p1") -> ScopedVerdict:
    return ScopedVerdict(scope=scope, verdict=verdict, participant_id=pid)


# ---------------------------------------------------------------------------
# 1. Domain: constants and dataclasses
# ---------------------------------------------------------------------------

class TestApprovalScopeConstants:
    def test_scope_values(self):
        assert APPROVAL_SCOPE_ONE_OFF == "one_off"
        assert APPROVAL_SCOPE_SESSION == "session"
        assert APPROVAL_SCOPE_WORLD == "world"

    def test_partial_resolved_constant(self):
        assert APPROVAL_STATUS_PARTIALLY_RESOLVED == "partially_resolved"

    def test_resolved_constant(self):
        assert APPROVAL_STATUS_RESOLVED == "resolved"


class TestScopedVerdict:
    def test_creation(self):
        sv = ScopedVerdict(scope="one_off", verdict="allow", participant_id="p1")
        assert sv.scope == "one_off"
        assert sv.verdict == "allow"
        assert sv.participant_id == "p1"
        assert sv.timestamp  # non-empty

    def test_to_dict(self):
        sv = ScopedVerdict(scope="session", verdict="deny", participant_id="op1")
        d = sv.to_dict()
        assert d["scope"] == "session"
        assert d["verdict"] == "deny"
        assert d["participant_id"] == "op1"
        assert "timestamp" in d

    def test_default_participant_id(self):
        sv = ScopedVerdict(scope="world", verdict="allow")
        assert sv.participant_id == ""


class TestParticipantRegistration:
    def test_creation(self):
        reg = ParticipantRegistration(
            participant_id="sess-1",
            session_id="sess-1",
            roles={"user", "operator"},
        )
        assert reg.participant_id == "sess-1"
        assert reg.session_id == "sess-1"
        assert reg.roles == {"user", "operator"}
        assert reg.registered_at

    def test_to_dict(self):
        reg = ParticipantRegistration(
            participant_id="sess-2",
            session_id="sess-2",
            roles={"admin"},
        )
        d = reg.to_dict()
        assert d["participant_id"] == "sess-2"
        assert d["roles"] == ["admin"]  # sorted list
        assert "registered_at" in d


class TestActionApprovalScopedVerdicts:
    def test_new_approval_has_empty_scoped_verdicts(self):
        svc = ApprovalService()
        approval = svc.request_approval(
            session_id="s1", tool_name="t1", arguments={}, requested_by="agent"
        )
        assert approval.scoped_verdicts == []

    def test_scoped_verdicts_in_to_dict(self):
        svc = ApprovalService()
        approval = svc.request_approval(
            session_id="s1", tool_name="t1", arguments={}, requested_by="agent"
        )
        sv = _sv(APPROVAL_SCOPE_ONE_OFF, "allow")
        svc.respond(approval.approval_id, [sv])
        d = approval.to_dict()
        assert len(d["scoped_verdicts"]) == 1
        assert d["scoped_verdicts"][0]["scope"] == "one_off"
        assert d["scoped_verdicts"][0]["verdict"] == "allow"


# ---------------------------------------------------------------------------
# 2. ParticipantRegistry
# ---------------------------------------------------------------------------

class TestParticipantRegistry:
    def setup_method(self):
        self.reg = ParticipantRegistry()

    def test_register_creates_entry(self):
        result = self.reg.register("sess-1", {"user"})
        assert result.session_id == "sess-1"
        assert result.roles == {"user"}
        assert self.reg.count() == 1

    def test_register_upserts_roles(self):
        self.reg.register("sess-1", {"user"})
        updated = self.reg.register("sess-1", {"user", "operator"})
        assert updated.roles == {"user", "operator"}
        assert self.reg.count() == 1  # still one participant

    def test_unregister_known_session(self):
        self.reg.register("sess-1", {"user"})
        removed = self.reg.unregister("sess-1")
        assert removed is True
        assert self.reg.count() == 0

    def test_unregister_unknown_session(self):
        removed = self.reg.unregister("does-not-exist")
        assert removed is False

    def test_list_all_empty(self):
        assert self.reg.list_all() == []

    def test_list_all_multiple(self):
        self.reg.register("sess-a", {"user"})
        self.reg.register("sess-b", {"operator"})
        participants = self.reg.list_all()
        assert len(participants) == 2
        ids = {p.session_id for p in participants}
        assert ids == {"sess-a", "sess-b"}

    def test_get_existing(self):
        self.reg.register("sess-1", {"user"})
        result = self.reg.get("sess-1")
        assert result is not None
        assert result.session_id == "sess-1"

    def test_get_missing_returns_none(self):
        assert self.reg.get("missing") is None


# ---------------------------------------------------------------------------
# 3. ApprovalService.respond()
# ---------------------------------------------------------------------------

class TestApprovalServiceRespond:

    def _setup(self):
        svc = ApprovalService(default_ttl_seconds=300)
        overlay_svc = OverlayService()
        session_store = SessionStore()
        session_store.create(manifest_id="manifest-1", session_id="sess-1")
        approval = svc.request_approval(
            session_id="sess-1",
            tool_name="send_email",
            arguments={"to": "alice@example.com"},
            requested_by="agent",
        )
        return svc, overlay_svc, session_store, approval

    # --- one_off allow ---

    def test_one_off_allow_marks_fingerprint_approved(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv = _sv(APPROVAL_SCOPE_ONE_OFF, "allow")
        svc.respond(approval.approval_id, [sv], overlay_svc, ss)
        assert svc.has_explicit_allow(
            session_id="sess-1",
            tool_name="send_email",
            arguments={"to": "alice@example.com"},
        )

    def test_one_off_allow_does_not_create_overlay(self):
        svc, overlay_svc, ss, approval = self._setup()
        svc.respond(approval.approval_id, [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")], overlay_svc, ss)
        assert overlay_svc.count() == 0

    # --- session allow ---

    def test_session_allow_creates_overlay(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv = _sv(APPROVAL_SCOPE_SESSION, "allow")
        svc.respond(approval.approval_id, [sv], overlay_svc, ss)
        overlays = overlay_svc.get_active_overlays("sess-1")
        assert len(overlays) == 1
        assert "send_email" in overlays[0].changes.reveal_tools

    def test_session_deny_does_not_create_overlay(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv = _sv(APPROVAL_SCOPE_SESSION, "deny")
        svc.respond(approval.approval_id, [sv], overlay_svc, ss)
        assert overlay_svc.count() == 0

    # --- world allow (stub) ---

    def test_world_allow_is_accepted_no_crash(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv = _sv(APPROVAL_SCOPE_WORLD, "allow")
        updated = svc.respond(approval.approval_id, [sv], overlay_svc, ss)
        assert any(v.scope == APPROVAL_SCOPE_WORLD for v in updated.scoped_verdicts)

    # --- idempotency ---

    def test_idempotent_same_scope_twice_no_double_effect(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv1 = _sv(APPROVAL_SCOPE_SESSION, "allow")
        sv2 = _sv(APPROVAL_SCOPE_SESSION, "allow")
        # First call: session allow → overlay is created.
        svc.respond(approval.approval_id, [sv1], overlay_svc, ss)
        # Second call with same scope: idempotent → no second overlay.
        svc.respond(approval.approval_id, [sv2], overlay_svc, ss)
        assert overlay_svc.count() == 1

    def test_idempotent_same_scope_in_single_call(self):
        svc, overlay_svc, ss, approval = self._setup()
        sv1 = _sv(APPROVAL_SCOPE_SESSION, "allow")
        sv2 = _sv(APPROVAL_SCOPE_SESSION, "deny")
        svc.respond(approval.approval_id, [sv1, sv2], overlay_svc, ss)
        # Only first verdict for session scope counts.
        assert overlay_svc.count() == 1

    # --- expired approval ---

    def test_expired_approval_returns_expired_status(self):
        svc = ApprovalService()
        approval = _make_expired_approval(svc)
        updated = svc.respond(
            approval.approval_id,
            [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")],
        )
        assert updated.status == APPROVAL_STATUS_EXPIRED

    def test_expired_approval_does_not_create_overlay(self):
        svc = ApprovalService()
        overlay_svc = OverlayService()
        ss = SessionStore()
        ss.create(manifest_id="m1", session_id="sess-x")
        approval = _make_expired_approval(svc)
        svc.respond(
            approval.approval_id,
            [_sv(APPROVAL_SCOPE_SESSION, "allow")],
            overlay_svc,
            ss,
        )
        assert overlay_svc.count() == 0

    def test_expired_approval_does_not_mark_fingerprint_approved(self):
        svc = ApprovalService()
        approval = _make_expired_approval(svc)
        svc.respond(
            approval.approval_id,
            [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")],
        )
        assert not svc.has_explicit_allow("sess-x", "do_thing", {"x": 1})

    # --- terminal state rejection ---

    def test_respond_to_terminal_state_raises(self):
        svc, overlay_svc, ss, approval = self._setup()
        # Fully resolve (all scopes).
        svc.respond(
            approval.approval_id,
            [
                _sv(APPROVAL_SCOPE_ONE_OFF, "allow"),
                _sv(APPROVAL_SCOPE_SESSION, "allow"),
                _sv(APPROVAL_SCOPE_WORLD, "allow"),
            ],
            overlay_svc,
            ss,
        )
        assert approval.status == APPROVAL_STATUS_RESOLVED
        with pytest.raises(RuntimeError):
            svc.respond(approval.approval_id, [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")])

    # --- mixed verdicts ---

    def test_mixed_verdicts_one_off_allow_session_deny(self):
        svc, overlay_svc, ss, approval = self._setup()
        svc.respond(
            approval.approval_id,
            [
                _sv(APPROVAL_SCOPE_ONE_OFF, "allow"),
                _sv(APPROVAL_SCOPE_SESSION, "deny"),
            ],
            overlay_svc,
            ss,
        )
        # one_off allow → tool call explicitly allowed.
        assert svc.has_explicit_allow("sess-1", "send_email", {"to": "alice@example.com"})
        # session deny → no overlay.
        assert overlay_svc.count() == 0

    # --- status transitions ---

    def test_status_pending_to_partially_resolved(self):
        svc, overlay_svc, ss, approval = self._setup()
        assert approval.status == APPROVAL_STATUS_PENDING
        svc.respond(approval.approval_id, [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")])
        assert approval.status == APPROVAL_STATUS_PARTIALLY_RESOLVED

    def test_status_partially_resolved_to_resolved(self):
        svc, overlay_svc, ss, approval = self._setup()
        svc.respond(approval.approval_id, [_sv(APPROVAL_SCOPE_ONE_OFF, "allow")])
        assert approval.status == APPROVAL_STATUS_PARTIALLY_RESOLVED
        svc.respond(approval.approval_id, [_sv(APPROVAL_SCOPE_SESSION, "deny")])
        assert approval.status == APPROVAL_STATUS_PARTIALLY_RESOLVED
        svc.respond(
            approval.approval_id,
            [_sv(APPROVAL_SCOPE_WORLD, "deny")],
            overlay_svc,
            ss,
        )
        assert approval.status == APPROVAL_STATUS_RESOLVED

    def test_status_transitions_all_at_once(self):
        svc, overlay_svc, ss, approval = self._setup()
        svc.respond(
            approval.approval_id,
            [
                _sv(APPROVAL_SCOPE_ONE_OFF, "allow"),
                _sv(APPROVAL_SCOPE_SESSION, "deny"),
                _sv(APPROVAL_SCOPE_WORLD, "deny"),
            ],
            overlay_svc,
            ss,
        )
        assert approval.status == APPROVAL_STATUS_RESOLVED


# ---------------------------------------------------------------------------
# 4. ApprovalBroadcaster
# ---------------------------------------------------------------------------

class TestApprovalBroadcaster:
    def test_broadcast_without_sse_store_is_noop(self):
        bc = ApprovalBroadcaster()
        reg = ParticipantRegistry()
        reg.register("sess-1", {"user"})
        svc = ApprovalService()
        approval = svc.request_approval("sess-1", "tool", {}, "agent")
        count = bc.broadcast_approval_requested(approval, reg)
        assert count == 0

    def test_broadcast_with_sse_store_pushes_to_queues(self):
        bc = ApprovalBroadcaster()
        reg = ParticipantRegistry()
        reg.register("sess-p", {"user"})

        # Mock SSE store with a real asyncio.Queue.
        loop = asyncio.new_event_loop()
        try:
            queue = asyncio.Queue(loop=loop) if hasattr(asyncio, 'Queue') else asyncio.Queue()
        except TypeError:
            queue = asyncio.Queue()

        mock_store = MagicMock()
        mock_store.get_queue.return_value = queue
        bc.set_sse_store(mock_store)

        svc = ApprovalService()
        approval = svc.request_approval("sess-p", "tool", {}, "agent")
        count = bc.broadcast_approval_requested(approval, reg)
        assert count == 1
        assert not queue.empty()
        payload = json.loads(queue.get_nowait())
        assert payload["type"] == "approval_requested"
        assert payload["approval_id"] == approval.approval_id
        assert payload["tool_name"] == "tool"
        assert "one_off" in payload["scopes_available"]

    def test_notify_originator_without_sse_store(self):
        bc = ApprovalBroadcaster()
        svc = ApprovalService()
        approval = svc.request_approval("sess-o", "tool", {}, "agent")
        result = bc.notify_originator("sess-o", approval, "allow")
        assert result is False

    def test_notify_originator_pushes_resolved_event(self):
        bc = ApprovalBroadcaster()
        queue = asyncio.Queue()
        mock_store = MagicMock()
        mock_store.get_queue.return_value = queue
        bc.set_sse_store(mock_store)

        svc = ApprovalService()
        approval = svc.request_approval("sess-o", "tool", {}, "agent")
        sv = _sv(APPROVAL_SCOPE_ONE_OFF, "allow", "p1")
        approval.scoped_verdicts.append(sv)

        result = bc.notify_originator("sess-o", approval, "allow")
        assert result is True
        payload = json.loads(queue.get_nowait())
        assert payload["type"] == "approval_resolved"
        assert payload["approval_id"] == approval.approval_id
        assert payload["effective_verdict"] == "allow"


# ---------------------------------------------------------------------------
# 5. API endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def cp_state():
    return ControlPlaneState.create()


@pytest.fixture
def api_client():
    """
    Returns (TestClient, ControlPlaneState) sharing the same in-memory services.

    create_control_plane_app() creates its own internal ControlPlaneState and
    wires the router to it via closure. We can't replace it after the fact via
    app.state.control_plane. So we build the router directly with our state.
    """
    from fastapi import FastAPI
    from agent_hypervisor.control_plane.api import create_control_plane_router

    state = ControlPlaneState.create()
    router = create_control_plane_router(state)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), state


class TestParticipantEndpoints:
    def test_post_participants_creates_registration(self, api_client):
        client, state = api_client
        resp = client.post("/control/participants", json={
            "session_id": "sess-1",
            "roles": ["user", "operator"],
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["session_id"] == "sess-1"
        assert set(body["roles"]) == {"user", "operator"}

    def test_post_participants_upserts_roles(self, api_client):
        client, state = api_client
        client.post("/control/participants", json={"session_id": "sess-1", "roles": ["user"]})
        resp = client.post("/control/participants", json={"session_id": "sess-1", "roles": ["user", "operator"]})
        assert resp.status_code == 201
        assert state.participant_registry.count() == 1

    def test_delete_participants_removes_registration(self, api_client):
        client, state = api_client
        client.post("/control/participants", json={"session_id": "sess-1", "roles": ["user"]})
        resp = client.delete("/control/participants/sess-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unregistered"
        assert state.participant_registry.count() == 0

    def test_delete_participants_unknown_returns_not_registered(self, api_client):
        client, state = api_client
        resp = client.delete("/control/participants/ghost")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_registered"

    def test_get_participants_returns_list(self, api_client):
        client, state = api_client
        client.post("/control/participants", json={"session_id": "s1", "roles": ["user"]})
        client.post("/control/participants", json={"session_id": "s2", "roles": ["operator"]})
        resp = client.get("/control/participants")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2

    def test_get_participants_empty(self, api_client):
        client, _ = api_client
        resp = client.get("/control/participants")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestRespondEndpoint:
    def _create_session_and_approval(self, client, state):
        """Create a session and pending approval via the service layer."""
        state.session_store.create(manifest_id="m1", session_id="sess-a")
        approval = state.approval_service.request_approval(
            session_id="sess-a",
            tool_name="read_file",
            arguments={"path": "/tmp/x"},
            requested_by="agent",
        )
        return approval

    def test_patch_respond_one_off_allow(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        resp = client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "allow", "participant_id": "p1"}],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == APPROVAL_STATUS_PARTIALLY_RESOLVED
        assert len(body["scoped_verdicts"]) == 1
        assert body["scoped_verdicts"][0]["scope"] == "one_off"
        assert body["scoped_verdicts"][0]["verdict"] == "allow"

    def test_patch_respond_marks_fingerprint_approved(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "allow"}],
        })
        assert state.approval_service.has_explicit_allow(
            session_id="sess-a",
            tool_name="read_file",
            arguments={"path": "/tmp/x"},
        )

    def test_patch_respond_session_allow_creates_overlay(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "session", "verdict": "allow", "participant_id": "op1"}],
        })
        overlays = state.overlay_service.get_active_overlays("sess-a")
        assert len(overlays) == 1
        assert "read_file" in overlays[0].changes.reveal_tools

    def test_patch_respond_full_all_scopes_resolves(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        resp = client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [
                {"scope": "one_off", "verdict": "allow"},
                {"scope": "session", "verdict": "deny"},
                {"scope": "world", "verdict": "deny"},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == APPROVAL_STATUS_RESOLVED

    def test_patch_respond_unknown_approval_returns_404(self, api_client):
        client, _ = api_client
        resp = client.patch("/control/approvals/does-not-exist/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "allow"}],
        })
        assert resp.status_code == 404

    def test_patch_respond_terminal_state_returns_409(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        # Exhaust all scopes.
        client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [
                {"scope": "one_off", "verdict": "deny"},
                {"scope": "session", "verdict": "deny"},
                {"scope": "world", "verdict": "deny"},
            ],
        })
        # Now try again.
        resp = client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "allow"}],
        })
        assert resp.status_code == 409

    def test_patch_respond_idempotent_duplicate_scope(self, api_client):
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        # First call: one_off allow.
        client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "allow"}],
        })
        # Second call with same scope: should be ignored.
        resp = client.patch(f"/control/approvals/{approval.approval_id}/respond", json={
            "verdicts": [{"scope": "one_off", "verdict": "deny"}],
        })
        assert resp.status_code == 200
        # Still only one scoped verdict.
        body = resp.json()
        assert len(body["scoped_verdicts"]) == 1
        assert body["scoped_verdicts"][0]["verdict"] == "allow"  # first wins

    def test_old_resolve_endpoint_still_works(self, api_client):
        """Backwards compatibility: POST /control/approvals/{id}/resolve still works."""
        client, state = api_client
        approval = self._create_session_and_approval(client, state)
        resp = client.post(f"/control/approvals/{approval.approval_id}/resolve", json={
            "decision": "allowed",
            "resolved_by": "human",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "allowed"


# ---------------------------------------------------------------------------
# 6. Full round-trip test
# ---------------------------------------------------------------------------

class TestFullRoundTrip:
    """
    Simulates the complete Phase 8 approval flow:
      1. Register a participant.
      2. Create an approval (simulating ask verdict from gateway).
      3. Broadcast to participants (simulate – check queue contents).
      4. Participant responds with scoped verdicts.
      5. Verify tool is now approved (is_action_approved = True).
      6. Verify overlay created for session scope.
    """

    def test_full_round_trip(self):
        from fastapi import FastAPI
        from agent_hypervisor.control_plane.api import create_control_plane_router

        state = ControlPlaneState.create()
        app = FastAPI()
        app.include_router(create_control_plane_router(state))

        # Wire a mock SSE store for broadcasting.
        participant_queue = asyncio.Queue()
        originator_queue = asyncio.Queue()

        mock_sse = MagicMock()

        def _get_queue(sid):
            if sid == "participant-sess":
                return participant_queue
            if sid == "agent-sess":
                return originator_queue
            return None

        mock_sse.get_queue.side_effect = _get_queue
        state.broadcaster.set_sse_store(mock_sse)

        # Step 1: Create control plane session for agent.
        state.session_store.create(manifest_id="m1", session_id="agent-sess")

        # Step 2: Register participant.
        state.participant_registry.register("participant-sess", {"user", "operator"})

        # Step 3: Create approval (as gateway would on verdict=ask).
        approval = state.approval_service.request_approval(
            session_id="agent-sess",
            tool_name="write_file",
            arguments={"path": "/tmp/out.txt", "content": "hello"},
            requested_by="agent",
        )

        # Step 4: Broadcast to participants.
        n = state.broadcaster.broadcast_approval_requested(approval, state.participant_registry)
        assert n == 1
        payload = json.loads(participant_queue.get_nowait())
        assert payload["type"] == "approval_requested"
        assert payload["approval_id"] == approval.approval_id
        assert payload["tool_name"] == "write_file"

        # Step 5: Participant responds with one_off allow + session allow.
        verdicts = [
            ScopedVerdict(scope=APPROVAL_SCOPE_ONE_OFF, verdict="allow", participant_id="participant-sess"),
            ScopedVerdict(scope=APPROVAL_SCOPE_SESSION, verdict="allow", participant_id="participant-sess"),
        ]
        state.approval_service.respond(
            approval_id=approval.approval_id,
            verdicts=verdicts,
            overlay_service=state.overlay_service,
            session_store=state.session_store,
        )

        # Step 6: Originator is notified.
        state.broadcaster.notify_originator("agent-sess", approval, "allow")
        notification = json.loads(originator_queue.get_nowait())
        assert notification["type"] == "approval_resolved"
        assert notification["effective_verdict"] == "allow"

        # Step 7: Tool call is now explicitly allowed (one_off path).
        assert state.approval_service.has_explicit_allow(
            session_id="agent-sess",
            tool_name="write_file",
            arguments={"path": "/tmp/out.txt", "content": "hello"},
        )

        # Step 8: Session overlay was created.
        overlays = state.overlay_service.get_active_overlays("agent-sess")
        assert len(overlays) == 1
        assert "write_file" in overlays[0].changes.reveal_tools
