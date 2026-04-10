"""
test_gateway_wiring.py — Integration tests for the control plane ↔ MCP gateway wiring.

Tests verify that:
  1. tools/call with "ask" verdict routes to ApprovalService (creates pending approval)
  2. tools/call with "ask" and no control plane fails closed (deny)
  3. tools/list reflects active session overlays when control plane is wired
  4. tools/list without overlays is unchanged
  5. The EnforcementDecision "asked" property works correctly
  6. ASK verdict without a session_id fails closed
  7. Existing allow/deny behavior is unchanged after wiring

All tests run against a real FastAPI TestClient (no server process needed).
The policy engine is a minimal stub that returns "ask" for a specific tool.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import MagicMock

from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import create_mcp_app
from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
    EnforcementDecision,
    InvocationProvenance,
    ToolCallEnforcer,
)
from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
from agent_hypervisor.control_plane.api import ControlPlaneState
from agent_hypervisor.control_plane.domain import (
    APPROVAL_STATUS_ALLOWED,
    APPROVAL_STATUS_PENDING,
    OverlayChanges,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MANIFEST_PATH = Path(__file__).parent.parent.parent / "manifests" / "example_world.yaml"


def _make_manifest(tools: list[str]) -> WorldManifest:
    return WorldManifest(
        workflow_id="test-world",
        capabilities=[CapabilityConstraint(tool=t) for t in tools],
    )


def _make_registry(tools: list[str]):
    from agent_hypervisor.hypervisor.gateway.tool_registry import build_default_registry
    return build_default_registry(tools)


def _jsonrpc_call(method: str, params: dict, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def _tools_list(client, session_id: str = "") -> list[str]:
    meta = {"_meta": {"session_id": session_id}} if session_id else {}
    resp = client.post("/mcp", json=_jsonrpc_call("tools/list", meta))
    data = resp.json()
    return [t["name"] for t in data.get("result", {}).get("tools", [])]


def _tools_call(client, tool: str, args: dict, session_id: str = "") -> dict:
    params: dict = {"name": tool, "arguments": args}
    if session_id:
        params["_meta"] = {"session_id": session_id}
    resp = client.post("/mcp", json=_jsonrpc_call("tools/call", params))
    return resp.json()


# ---------------------------------------------------------------------------
# Minimal "ask" policy engine stub
# ---------------------------------------------------------------------------

class _AskPolicyEngine:
    """
    Stub policy engine that returns 'ask' for a specific tool, 'allow' otherwise.
    Mimics the PolicyEngine interface expected by ToolCallEnforcer.
    """

    def __init__(self, ask_tool: str) -> None:
        self._ask_tool = ask_tool

    def evaluate(self, call, registry) -> MagicMock:
        result = MagicMock()
        if call.tool == self._ask_tool:
            result.verdict = MagicMock()
            result.verdict.value = "ask"
            result.reason = f"tool '{call.tool}' requires approval"
            result.matched_rule = "ask-policy"
        else:
            result.verdict = MagicMock()
            result.verdict.value = "allow"
            result.reason = "allowed"
            result.matched_rule = "allow-all"
        return result


# ---------------------------------------------------------------------------
# Group 1: EnforcementDecision "asked" property
# ---------------------------------------------------------------------------

class TestEnforcementDecisionAsked:
    def test_asked_true_when_verdict_is_ask(self):
        decision = EnforcementDecision(
            verdict="ask",
            reason="requires approval",
            matched_rule="policy:ask-policy",
        )
        assert decision.asked is True
        assert decision.allowed is False
        assert decision.denied is False

    def test_asked_false_when_verdict_is_allow(self):
        decision = EnforcementDecision(
            verdict="allow", reason="ok", matched_rule="manifest:allowed"
        )
        assert decision.asked is False

    def test_asked_false_when_verdict_is_deny(self):
        decision = EnforcementDecision(
            verdict="deny", reason="denied", matched_rule="manifest:tool_not_declared"
        )
        assert decision.asked is False

    def test_enforcer_returns_ask_from_policy_engine(self):
        """ToolCallEnforcer propagates 'ask' from the policy engine."""
        manifest = _make_manifest(["send_email"])
        registry = _make_registry(["send_email"])
        policy = _AskPolicyEngine(ask_tool="send_email")
        enforcer = ToolCallEnforcer(manifest, registry, policy_engine=policy)

        decision = enforcer.enforce("send_email", {"to": "x@y.com"})
        assert decision.asked
        assert "ask" in decision.matched_rule or "ask-policy" in decision.matched_rule

    def test_enforcer_returns_deny_for_deny_policy(self):
        """Deny from policy engine is still deny, not ask."""
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])

        deny_policy = MagicMock()
        deny_result = MagicMock()
        deny_result.verdict = MagicMock()
        deny_result.verdict.value = "deny"
        deny_result.reason = "not allowed"
        deny_result.matched_rule = "deny-rule"
        deny_policy.evaluate.return_value = deny_result

        enforcer = ToolCallEnforcer(manifest, registry, policy_engine=deny_policy)
        decision = enforcer.enforce("read_file", {})
        assert decision.denied
        assert not decision.asked


# ---------------------------------------------------------------------------
# Group 2: tools/call ask → approval routing (with control plane)
# ---------------------------------------------------------------------------

class TestToolsCallAskWithControlPlane:
    @pytest.fixture
    def app_with_cp(self):
        """Gateway with a control plane and a policy engine that asks for send_email."""
        cp = ControlPlaneState.create()
        policy = _AskPolicyEngine(ask_tool="send_email")
        return create_mcp_app(
            manifest_path=MANIFEST_PATH,
            policy_engine=policy,
            control_plane=cp,
        )

    def test_ask_creates_pending_approval(self, app_with_cp):
        """When policy says ask and control plane is present, a pending approval is created."""
        with TestClient(app_with_cp) as client:
            # Create a session first
            sid = "test-session-ask-01"
            app_with_cp.state.control_plane.session_store.create(
                manifest_id="test", session_id=sid
            )

            result = _tools_call(client, "send_email", {"to": "a@b.com"}, session_id=sid)
            assert "result" in result, f"Expected result, got: {result}"
            assert result["result"]["status"] == "pending_approval"
            assert "approval_id" in result["result"]

    def test_pending_approval_is_in_service(self, app_with_cp):
        """The created approval is retrievable from ApprovalService."""
        with TestClient(app_with_cp) as client:
            sid = "test-session-ask-02"
            app_with_cp.state.control_plane.session_store.create(
                manifest_id="test", session_id=sid
            )

            result = _tools_call(client, "send_email", {"to": "a@b.com"}, session_id=sid)
            approval_id = result["result"]["approval_id"]

            cp = app_with_cp.state.control_plane
            approval = cp.approval_service.get(approval_id)
            assert approval is not None
            assert approval.status == APPROVAL_STATUS_PENDING
            assert approval.tool_name == "send_email"

    def test_approval_resolves_via_control_plane_api(self, app_with_cp):
        """Approval created by ask verdict can be resolved via /control/approvals/{id}/resolve."""
        with TestClient(app_with_cp) as client:
            sid = "test-session-ask-03"
            app_with_cp.state.control_plane.session_store.create(
                manifest_id="test", session_id=sid
            )

            result = _tools_call(client, "send_email", {"to": "a@b.com"}, session_id=sid)
            approval_id = result["result"]["approval_id"]

            resp = client.post(
                f"/control/approvals/{approval_id}/resolve",
                json={"decision": "allowed", "resolved_by": "operator"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == APPROVAL_STATUS_ALLOWED

    def test_approval_event_emitted(self, app_with_cp):
        """approval_requested event is emitted to the event store."""
        with TestClient(app_with_cp) as client:
            sid = "test-session-ask-04"
            app_with_cp.state.control_plane.session_store.create(
                manifest_id="test", session_id=sid
            )

            _tools_call(client, "send_email", {"to": "x@y.com"}, session_id=sid)

            events = app_with_cp.state.control_plane.event_store.get_session_events(
                sid, event_type="approval_requested"
            )
            assert len(events) == 1
            assert events[0].payload["tool_name"] == "send_email"

    def test_non_ask_tool_still_executes(self, app_with_cp):
        """Tools not matched by the ask policy still execute normally."""
        with TestClient(app_with_cp) as client:
            # read_file is not in the ask policy — should execute (or deny for another reason)
            result = _tools_call(client, "read_file", {"path": "/tmp/test.txt"})
            # The result should not be a pending_approval — it should be allow or deny
            if "result" in result:
                assert result["result"].get("status") != "pending_approval"


# ---------------------------------------------------------------------------
# Group 3: tools/call ask → fail closed (no control plane)
# ---------------------------------------------------------------------------

class TestToolsCallAskWithoutControlPlane:
    @pytest.fixture
    def app_no_cp(self):
        """Gateway with an ask policy but NO control plane."""
        policy = _AskPolicyEngine(ask_tool="send_email")
        return create_mcp_app(
            manifest_path=MANIFEST_PATH,
            policy_engine=policy,
        )

    def test_ask_without_control_plane_fails_closed(self, app_no_cp):
        """Without a control plane, ask verdicts are denied (fail-closed)."""
        with TestClient(app_no_cp) as client:
            result = _tools_call(
                client, "send_email",
                {"to": "a@b.com"},
                session_id="session-no-cp",
            )
            assert "error" in result, f"Expected error, got: {result}"
            assert "denied" in result["error"]["message"].lower() or \
                   "approval" in result["error"]["message"].lower()

    def test_ask_without_session_id_fails_closed(self):
        """Ask verdict with no session_id also fails closed (no session to bind approval to)."""
        cp = ControlPlaneState.create()
        policy = _AskPolicyEngine(ask_tool="send_email")
        app = create_mcp_app(
            manifest_path=MANIFEST_PATH,
            policy_engine=policy,
            control_plane=cp,
        )
        with TestClient(app) as client:
            # Call without session_id — provenance.session_id will be ""
            result = _tools_call(client, "send_email", {"to": "a@b.com"}, session_id="")
            assert "error" in result, f"Expected error for no-session ask, got: {result}"


# ---------------------------------------------------------------------------
# Group 4: tools/list reflects overlays when control plane is wired
# ---------------------------------------------------------------------------

class TestToolsListWithOverlays:
    @pytest.fixture
    def app_with_cp(self):
        cp = ControlPlaneState.create()
        return create_mcp_app(manifest_path=MANIFEST_PATH, control_plane=cp)

    def test_tools_list_without_overlays_is_unchanged(self, app_with_cp):
        """Without overlays, tools/list returns the base manifest tools."""
        with TestClient(app_with_cp) as client:
            tools = _tools_list(client)
            # Should include the manifest's declared tools (that have adapters)
            assert len(tools) > 0

    def test_tools_list_reflects_reveal_overlay(self, app_with_cp):
        """An overlay that reveals a tool makes it appear in tools/list."""
        cp = app_with_cp.state.control_plane
        sid = "overlay-list-session-01"
        cp.session_store.create(manifest_id="test", session_id=sid)

        # Get baseline (no overlays)
        with TestClient(app_with_cp) as client:
            baseline = _tools_list(client, session_id=sid)

            # Attach overlay revealing an extra tool (one that has an adapter)
            # We need a tool that IS in the registry but NOT in the base manifest.
            # The example_world.yaml has read_file and send_email.
            # Let's reveal "http_post" which has an adapter in build_default_registry.
            cp.overlay_service.attach(
                session_id=sid,
                parent_manifest_id="test",
                created_by="op",
                changes=OverlayChanges(reveal_tools=["http_post"]),
                session_store=cp.session_store,
            )

            overlay_tools = _tools_list(client, session_id=sid)
            assert "http_post" in overlay_tools
            # baseline tools are still present
            for t in baseline:
                assert t in overlay_tools

    def test_tools_list_reflects_hide_overlay(self, app_with_cp):
        """An overlay that hides a tool removes it from tools/list."""
        cp = app_with_cp.state.control_plane
        sid = "overlay-list-session-02"
        cp.session_store.create(manifest_id="test", session_id=sid)

        with TestClient(app_with_cp) as client:
            baseline = _tools_list(client, session_id=sid)
            # Need at least one tool to hide
            if not baseline:
                pytest.skip("No tools in base manifest to hide")

            target = baseline[0]
            cp.overlay_service.attach(
                session_id=sid,
                parent_manifest_id="test",
                created_by="op",
                changes=OverlayChanges(hide_tools=[target]),
                session_store=cp.session_store,
            )

            hidden_tools = _tools_list(client, session_id=sid)
            assert target not in hidden_tools

    def test_tools_list_restores_after_overlay_detach(self, app_with_cp):
        """After detaching an overlay, tools/list reverts to the base manifest."""
        cp = app_with_cp.state.control_plane
        sid = "overlay-list-session-03"
        cp.session_store.create(manifest_id="test", session_id=sid)

        with TestClient(app_with_cp) as client:
            baseline = _tools_list(client, session_id=sid)

            overlay = cp.overlay_service.attach(
                session_id=sid,
                parent_manifest_id="test",
                created_by="op",
                changes=OverlayChanges(reveal_tools=["http_post"]),
                session_store=cp.session_store,
            )
            assert "http_post" in _tools_list(client, session_id=sid)

            # Detach and confirm revert
            cp.overlay_service.detach(overlay.overlay_id, session_store=cp.session_store)
            restored = _tools_list(client, session_id=sid)
            assert "http_post" not in restored
            assert set(restored) == set(baseline)


# ---------------------------------------------------------------------------
# Group 5: SSE session auto-registration
# ---------------------------------------------------------------------------

class TestSSESessionAutoRegistration:
    def test_sse_registers_session_with_control_plane(self):
        """Opening an SSE connection auto-registers the session in SessionStore.

        The session registration happens synchronously inside sse_endpoint(),
        before the StreamingResponse body is consumed. We patch sse_stream to a
        minimal generator that yields one event and returns immediately so that
        the TestClient does not block on the 25-second heartbeat loop.
        """
        from unittest.mock import patch

        async def _fast_sse_stream(session_id, queue, endpoint_url, store):
            """Replacement generator: yield the endpoint event then exit cleanly."""
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            store.remove_session(session_id)

        cp = ControlPlaneState.create()
        app = create_mcp_app(manifest_path=MANIFEST_PATH, control_plane=cp)

        target = "agent_hypervisor.hypervisor.mcp_gateway.mcp_server.sse_stream"
        with patch(target, side_effect=_fast_sse_stream):
            with TestClient(app) as client:
                resp = client.get("/mcp/sse")

        # At least one session must have been registered with the control plane.
        sessions = cp.session_store.list()
        assert len(sessions) == 1, (
            f"Expected 1 session registered, got {len(sessions)}"
        )

    def test_sse_registered_session_has_correct_manifest(self):
        """Session registered by SSE has the manifest_id from the resolved manifest."""
        from unittest.mock import patch

        async def _fast_sse_stream(session_id, queue, endpoint_url, store):
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            store.remove_session(session_id)

        cp = ControlPlaneState.create()
        app = create_mcp_app(manifest_path=MANIFEST_PATH, control_plane=cp)

        target = "agent_hypervisor.hypervisor.mcp_gateway.mcp_server.sse_stream"
        with patch(target, side_effect=_fast_sse_stream):
            with TestClient(app) as client:
                client.get("/mcp/sse")

        sessions = cp.session_store.list()
        assert len(sessions) == 1
        session = sessions[0]
        # manifest_id must be a non-empty string (from WorldManifest.workflow_id)
        assert session.manifest_id, "Session manifest_id should not be empty"


# ---------------------------------------------------------------------------
# Group 6: Existing gateway behavior unchanged
# ---------------------------------------------------------------------------

class TestExistingBehaviorUnchanged:
    """Verify that wiring the control plane does not regress existing behavior."""

    @pytest.fixture
    def app_with_cp(self):
        cp = ControlPlaneState.create()
        return create_mcp_app(manifest_path=MANIFEST_PATH, control_plane=cp)

    def test_initialize_still_works(self, app_with_cp):
        with TestClient(app_with_cp) as client:
            resp = client.post("/mcp", json=_jsonrpc_call("initialize", {}))
            data = resp.json()
            assert "result" in data
            assert data["result"]["protocolVersion"] == "2024-11-05"

    def test_undeclared_tool_still_denied(self, app_with_cp):
        with TestClient(app_with_cp) as client:
            result = _tools_call(client, "not_a_real_tool", {})
            assert "error" in result

    def test_health_endpoint_still_works(self, app_with_cp):
        with TestClient(app_with_cp) as client:
            resp = client.get("/mcp/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "running"

    def test_control_plane_endpoints_mounted(self, app_with_cp):
        """When wired, /control/* endpoints are available."""
        with TestClient(app_with_cp) as client:
            resp = client.get("/control/sessions")
            assert resp.status_code == 200

    def test_sessions_endpoint_lists_sessions(self, app_with_cp):
        with TestClient(app_with_cp) as client:
            client.post("/control/sessions", json={"manifest_id": "m1"})
            resp = client.get("/control/sessions")
            assert resp.json()["count"] >= 1
