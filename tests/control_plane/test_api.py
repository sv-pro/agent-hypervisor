"""
test_api.py — HTTP endpoint tests for the control plane FastAPI router.

Uses FastAPI's TestClient (synchronous, no server needed).

Test groups:
  1. Health endpoint
  2. Session endpoints (create, get, list, mode, close)
  3. World state endpoint
  4. Approval endpoints (list, get, resolve)
  5. Overlay endpoints (attach, list, detach)
  6. Integration: full scenario through the API
"""

import pytest
from fastapi.testclient import TestClient

from agent_hypervisor.control_plane.api import create_control_plane_app, ControlPlaneState
from agent_hypervisor.control_plane.domain import (
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_DENIED,
    SESSION_MODE_BACKGROUND,
    SESSION_MODE_INTERACTIVE,
    SESSION_STATE_CLOSED,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_control_plane_app(default_ttl_seconds=300)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def cp_state(app):
    return app.state.control_plane


def _create_session(client, manifest_id="test-manifest-v1", mode="background", principal=None):
    """Helper: create a session via API and return the response JSON."""
    body = {"manifest_id": manifest_id, "mode": mode}
    if principal:
        body["principal"] = principal
    resp = client.post("/control/sessions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Group 1: Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_running(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "sessions" in data
        assert "approvals" in data
        assert "overlays" in data


# ---------------------------------------------------------------------------
# Group 2: Session endpoints
# ---------------------------------------------------------------------------

class TestSessionEndpoints:
    def test_create_session_returns_201(self, client):
        resp = client.post("/control/sessions", json={
            "manifest_id": "email-assistant-v1",
            "mode": "background",
            "principal": "agent",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["manifest_id"] == "email-assistant-v1"
        assert data["mode"] == SESSION_MODE_BACKGROUND
        assert data["session_id"]

    def test_create_session_with_explicit_id(self, client):
        resp = client.post("/control/sessions", json={
            "manifest_id": "m1",
            "session_id": "my-fixed-id-001",
        })
        assert resp.status_code == 201
        assert resp.json()["session_id"] == "my-fixed-id-001"

    def test_create_duplicate_session_returns_400(self, client):
        client.post("/control/sessions", json={
            "manifest_id": "m1", "session_id": "dup-id",
        })
        resp = client.post("/control/sessions", json={
            "manifest_id": "m1", "session_id": "dup-id",
        })
        assert resp.status_code == 400

    def test_get_session(self, client):
        session = _create_session(client, manifest_id="m1")
        resp = client.get(f"/control/sessions/{session['session_id']}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session["session_id"]

    def test_get_unknown_session_returns_404(self, client):
        resp = client.get("/control/sessions/no-such-session")
        assert resp.status_code == 404

    def test_list_sessions(self, client):
        _create_session(client, manifest_id="m1")
        _create_session(client, manifest_id="m2")
        resp = client.get("/control/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2

    def test_list_sessions_filter_by_state(self, client):
        s = _create_session(client, manifest_id="m1")
        client.delete(f"/control/sessions/{s['session_id']}")

        resp = client.get("/control/sessions?state_filter=closed")
        data = resp.json()
        assert any(x["session_id"] == s["session_id"] for x in data["sessions"])

        resp = client.get("/control/sessions?state_filter=active")
        data = resp.json()
        assert not any(x["session_id"] == s["session_id"] for x in data["sessions"])

    def test_set_mode_to_interactive(self, client):
        session = _create_session(client)
        resp = client.patch(
            f"/control/sessions/{session['session_id']}/mode",
            json={"mode": "interactive"},
        )
        assert resp.status_code == 200
        assert resp.json()["mode"] == SESSION_MODE_INTERACTIVE

    def test_set_mode_invalid_returns_400(self, client):
        session = _create_session(client)
        resp = client.patch(
            f"/control/sessions/{session['session_id']}/mode",
            json={"mode": "invalid-mode"},
        )
        assert resp.status_code == 400

    def test_set_mode_unknown_session_returns_404(self, client):
        resp = client.patch("/control/sessions/no-such/mode", json={"mode": "interactive"})
        assert resp.status_code == 404

    def test_close_session(self, client):
        session = _create_session(client)
        resp = client.delete(f"/control/sessions/{session['session_id']}")
        assert resp.status_code == 200
        assert resp.json()["state"] == SESSION_STATE_CLOSED

    def test_close_unknown_session_returns_404(self, client):
        resp = client.delete("/control/sessions/no-such")
        assert resp.status_code == 404

    def test_session_created_event_emitted(self, client, cp_state):
        session = _create_session(client, manifest_id="m1")
        events = cp_state.event_store.get_session_events(
            session["session_id"], event_type="session_created"
        )
        assert len(events) == 1

    def test_mode_changed_event_emitted(self, client, cp_state):
        session = _create_session(client)
        client.patch(
            f"/control/sessions/{session['session_id']}/mode",
            json={"mode": "interactive"},
        )
        events = cp_state.event_store.get_session_events(
            session["session_id"], event_type="mode_changed"
        )
        assert len(events) == 1
        assert events[0].payload["new_mode"] == "interactive"


# ---------------------------------------------------------------------------
# Group 3: World state endpoint
# ---------------------------------------------------------------------------

class TestWorldStateEndpoint:
    def test_world_state_no_manifest_resolver(self, client):
        """Without a manifest resolver, base_tools is empty; overlays still visible."""
        session = _create_session(client)
        resp = client.get(f"/control/sessions/{session['session_id']}/world")
        assert resp.status_code == 200
        data = resp.json()
        assert "visible_tools" in data
        assert "_note" in data  # note explaining no resolver configured
        assert data["active_overlay_ids"] == []

    def test_world_state_with_manifest_resolver(self):
        """With a manifest resolver, visible_tools reflect base tools."""
        def resolver(session_id):
            return ["read_file", "send_email"], {}

        app = create_control_plane_app(get_base_manifest=resolver)
        with TestClient(app) as client:
            session = _create_session(client)
            resp = client.get(f"/control/sessions/{session['session_id']}/world")
            assert resp.status_code == 200
            data = resp.json()
            assert set(data["visible_tools"]) == {"read_file", "send_email"}
            assert "_note" not in data

    def test_world_state_includes_overlay_tools(self):
        """Active overlays are reflected in the world state view."""
        def resolver(session_id):
            return ["read_file"], {}

        app = create_control_plane_app(get_base_manifest=resolver)
        with TestClient(app) as client:
            session = _create_session(client)
            sid = session["session_id"]

            # Attach overlay that reveals write_file
            client.post(f"/control/sessions/{sid}/overlays", json={
                "created_by": "op",
                "reveal_tools": ["write_file"],
            })

            resp = client.get(f"/control/sessions/{sid}/world")
            data = resp.json()
            assert "write_file" in data["visible_tools"]
            assert "read_file" in data["visible_tools"]
            assert len(data["active_overlay_ids"]) == 1

    def test_world_state_unknown_session_returns_404(self, client):
        resp = client.get("/control/sessions/no-such/world")
        assert resp.status_code == 404

    def test_world_state_mode_reflects_session(self, client):
        session = _create_session(client, mode="interactive")
        resp = client.get(f"/control/sessions/{session['session_id']}/world")
        assert resp.json()["mode"] == SESSION_MODE_INTERACTIVE


# ---------------------------------------------------------------------------
# Group 4: Approval endpoints
# ---------------------------------------------------------------------------

class TestApprovalEndpoints:
    def _request_approval(self, cp_state, session_id, tool="send_email", args=None):
        """Helper: create an approval directly via service (not API)."""
        return cp_state.approval_service.request_approval(
            session_id=session_id,
            tool_name=tool,
            arguments=args or {"to": "x@y.com"},
            requested_by="agent",
            event_store=cp_state.event_store,
        )

    def test_list_pending_approvals(self, client, cp_state):
        session = _create_session(client)
        self._request_approval(cp_state, session["session_id"])

        resp = client.get("/control/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_list_pending_filter_by_session(self, client, cp_state):
        s1 = _create_session(client)
        s2 = _create_session(client)
        self._request_approval(cp_state, s1["session_id"])
        self._request_approval(cp_state, s2["session_id"])

        resp = client.get(f"/control/approvals?session_id={s1['session_id']}")
        data = resp.json()
        assert data["count"] == 1
        assert data["approvals"][0]["session_id"] == s1["session_id"]

    def test_get_approval(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])
        resp = client.get(f"/control/approvals/{approval.approval_id}")
        assert resp.status_code == 200
        assert resp.json()["approval_id"] == approval.approval_id

    def test_get_unknown_approval_returns_404(self, client):
        resp = client.get("/control/approvals/no-such-approval")
        assert resp.status_code == 404

    def test_resolve_approval_allowed(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])

        resp = client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "allowed", "resolved_by": "operator"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == APPROVAL_STATUS_ALLOWED
        assert data["resolved_by"] == "operator"

    def test_resolve_approval_denied(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])

        resp = client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "denied", "resolved_by": "operator"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == APPROVAL_STATUS_DENIED

    def test_resolve_invalid_decision_returns_400(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])

        resp = client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "maybe", "resolved_by": "op"},
        )
        assert resp.status_code == 400

    def test_resolve_already_resolved_returns_409(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])

        client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "allowed", "resolved_by": "op"},
        )
        resp = client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "denied", "resolved_by": "op"},
        )
        assert resp.status_code == 409

    def test_resolve_unknown_approval_returns_404(self, client):
        resp = client.post(
            "/control/approvals/no-such/resolve",
            json={"decision": "allowed", "resolved_by": "op"},
        )
        assert resp.status_code == 404

    def test_resolve_emits_event(self, client, cp_state):
        session = _create_session(client)
        approval = self._request_approval(cp_state, session["session_id"])

        client.post(
            f"/control/approvals/{approval.approval_id}/resolve",
            json={"decision": "allowed", "resolved_by": "op"},
        )
        events = cp_state.event_store.get_session_events(
            session["session_id"], event_type="approval_resolved"
        )
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Group 5: Overlay endpoints
# ---------------------------------------------------------------------------

class TestOverlayEndpoints:
    def test_attach_overlay_returns_201(self, client):
        session = _create_session(client)
        resp = client.post(
            f"/control/sessions/{session['session_id']}/overlays",
            json={
                "created_by": "operator",
                "reveal_tools": ["write_file"],
                "ttl_seconds": 3600,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["overlay_id"]
        assert data["changes"]["reveal_tools"] == ["write_file"]

    def test_attach_overlay_to_unknown_session_returns_404(self, client):
        resp = client.post(
            "/control/sessions/no-such/overlays",
            json={"created_by": "op"},
        )
        assert resp.status_code == 404

    def test_list_overlays_active_only(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={"created_by": "op"})
        overlay_id = resp.json()["overlay_id"]

        resp = client.get(f"/control/sessions/{sid}/overlays")
        data = resp.json()
        assert data["count"] == 1
        assert data["overlays"][0]["overlay_id"] == overlay_id

    def test_list_overlays_all_after_detach(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={"created_by": "op"})
        overlay_id = resp.json()["overlay_id"]
        client.delete(f"/control/sessions/{sid}/overlays/{overlay_id}")

        # active_only=true (default) → 0
        resp = client.get(f"/control/sessions/{sid}/overlays")
        assert resp.json()["count"] == 0

        # active_only=false → 1
        resp = client.get(f"/control/sessions/{sid}/overlays?active_only=false")
        assert resp.json()["count"] == 1

    def test_detach_overlay(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={"created_by": "op"})
        oid = resp.json()["overlay_id"]

        resp = client.delete(f"/control/sessions/{sid}/overlays/{oid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "detached"

    def test_detach_unknown_overlay_returns_404(self, client):
        session = _create_session(client)
        resp = client.delete(
            f"/control/sessions/{session['session_id']}/overlays/no-such-overlay"
        )
        assert resp.status_code == 404

    def test_detach_already_detached_returns_404(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={"created_by": "op"})
        oid = resp.json()["overlay_id"]

        client.delete(f"/control/sessions/{sid}/overlays/{oid}")
        resp = client.delete(f"/control/sessions/{sid}/overlays/{oid}")
        assert resp.status_code == 404

    def test_overlay_updates_session_overlay_ids(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={"created_by": "op"})
        oid = resp.json()["overlay_id"]

        session_detail = client.get(f"/control/sessions/{sid}").json()
        assert oid in session_detail["overlay_ids"]

    def test_overlay_emits_event(self, client, cp_state):
        session = _create_session(client)
        sid = session["session_id"]

        client.post(f"/control/sessions/{sid}/overlays", json={
            "created_by": "op", "reveal_tools": ["write_file"],
        })
        events = cp_state.event_store.get_session_events(sid, event_type="overlay_attached")
        assert len(events) == 1

    def test_overlay_with_all_change_types(self, client):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.post(f"/control/sessions/{sid}/overlays", json={
            "created_by": "op",
            "reveal_tools": ["write_file"],
            "hide_tools": ["send_email"],
            "widen_scope": {"read_file": {"paths": ["/*"]}},
            "narrow_scope": {"write_file": {"paths": ["/tmp/*"]}},
            "additional_constraints": {"rate_limit": 10},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["changes"]["reveal_tools"] == ["write_file"]
        assert data["changes"]["hide_tools"] == ["send_email"]
        assert data["changes"]["widen_scope"] == {"read_file": {"paths": ["/*"]}}
        assert data["changes"]["narrow_scope"] == {"write_file": {"paths": ["/tmp/*"]}}


# ---------------------------------------------------------------------------
# Group 6: Session event log endpoint
# ---------------------------------------------------------------------------

class TestEventLogEndpoint:
    def test_get_events(self, client, cp_state):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.get(f"/control/sessions/{sid}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        # session_created event was emitted by create_session endpoint
        assert data["count"] >= 1

    def test_get_events_filter_by_type(self, client, cp_state):
        session = _create_session(client)
        sid = session["session_id"]
        client.patch(f"/control/sessions/{sid}/mode", json={"mode": "interactive"})

        resp = client.get(f"/control/sessions/{sid}/events?event_type=mode_changed")
        data = resp.json()
        assert data["count"] == 1
        assert data["events"][0]["type"] == "mode_changed"

    def test_get_events_unknown_session_returns_404(self, client):
        resp = client.get("/control/sessions/no-such/events")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Group 7: Integration — full scenario via API
# ---------------------------------------------------------------------------

class TestIntegrationAPI:
    def test_session_start_approval_overlay_scenario(self):
        """
        Full scenario via HTTP API:
        1. Session created (background)
        2. Approval requested (via service, simulating agent trigger)
        3. Operator resolves approval via API
        4. Operator switches session to interactive
        5. Operator attaches overlay via API
        6. World state reflects overlay
        7. Overlay detached; world reverts
        """
        def resolver(session_id):
            return ["read_file", "send_email"], {}

        app = create_control_plane_app(get_base_manifest=resolver)
        cp_state = app.state.control_plane

        with TestClient(app) as client:
            # Step 1: create session
            session = _create_session(client, manifest_id="email-v1")
            sid = session["session_id"]
            assert session["mode"] == SESSION_MODE_BACKGROUND

            # Step 2: approval requested (by agent/system directly via service)
            approval = cp_state.approval_service.request_approval(
                session_id=sid,
                tool_name="send_email",
                arguments={"to": "board@corp.com"},
                requested_by="agent",
                event_store=cp_state.event_store,
            )

            # Verify pending via API
            resp = client.get(f"/control/approvals?session_id={sid}")
            assert resp.json()["count"] == 1

            # Step 3: operator approves via API
            resp = client.post(
                f"/control/approvals/{approval.approval_id}/resolve",
                json={"decision": "allowed", "resolved_by": "alice"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "allowed"

            # Approval did NOT change the world
            world_before = client.get(f"/control/sessions/{sid}/world").json()
            assert "write_file" not in world_before["visible_tools"]

            # Step 4: operator switches to interactive
            client.patch(f"/control/sessions/{sid}/mode", json={"mode": "interactive"})
            assert client.get(f"/control/sessions/{sid}").json()["mode"] == "interactive"

            # Step 5: operator attaches overlay
            resp = client.post(f"/control/sessions/{sid}/overlays", json={
                "created_by": "alice",
                "reveal_tools": ["write_file"],
            })
            assert resp.status_code == 201
            oid = resp.json()["overlay_id"]

            # Step 6: world state reflects overlay
            world = client.get(f"/control/sessions/{sid}/world").json()
            assert "write_file" in world["visible_tools"]
            assert oid in world["active_overlay_ids"]

            # Step 7: detach overlay, world reverts
            client.delete(f"/control/sessions/{sid}/overlays/{oid}")
            world_after = client.get(f"/control/sessions/{sid}/world").json()
            assert "write_file" not in world_after["visible_tools"]
            assert set(world_after["visible_tools"]) == {"read_file", "send_email"}

            # Audit log has all expected events
            events_resp = client.get(f"/control/sessions/{sid}/events")
            event_types = [e["type"] for e in events_resp.json()["events"]]
            assert "session_created" in event_types
            assert "approval_requested" in event_types
            assert "approval_resolved" in event_types
            assert "mode_changed" in event_types
            assert "overlay_attached" in event_types
            assert "overlay_detached" in event_types
