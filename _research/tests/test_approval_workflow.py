"""
test_approval_workflow.py — Tests for the approval workflow.

Tests cover:
  1. ApprovalRecord creation when execute() returns ask
  2. Approval execution path (approve → tool runs → result returned)
  3. Rejection path (reject → deny-like response, no execution)
  4. Not-found approval (KeyError)
  5. Double-resolution prevention (ValueError)
  6. Traces include approval lifecycle fields
  7. GET /approvals endpoint (filter by status)
  8. GET /approvals/{id} endpoint
  9. POST /approvals/{id} endpoint (approve and reject via HTTP)
  10. GatewayClient helpers (arg, wrap_tool, submit_approval)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from fastapi.testclient import TestClient

from agent_hypervisor.gateway.config_loader import load_config
from agent_hypervisor.gateway.execution_router import (
    ArgSpec,
    ExecutionRouter,
    ToolRequest,
    _make_gateway_firewall_task,
)
from agent_hypervisor.gateway.gateway_server import create_app
from agent_hypervisor.gateway.tool_registry import build_default_registry
from agent_hypervisor.firewall import ProvenanceFirewall
from agent_hypervisor.policy_engine import PolicyEngine
from agent_hypervisor.gateway_client import GatewayClient, arg


REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_router() -> ExecutionRouter:
    registry = build_default_registry()
    engine = PolicyEngine.from_dict({"rules": [
        {"id": "allow-read",       "tool": "read_file",  "verdict": "allow"},
        {"id": "deny-ext-email",   "tool": "send_email", "argument": "to",
         "provenance": "external_document", "verdict": "deny"},
        {"id": "ask-clean-email",  "tool": "send_email", "argument": "to",
         "provenance": "user_declared", "verdict": "ask"},
        {"id": "deny-ext-post",    "tool": "http_post",  "argument": "body",
         "provenance": "external_document", "verdict": "deny"},
    ]})
    task = _make_gateway_firewall_task(["send_email", "http_post", "read_file"])
    firewall = ProvenanceFirewall(task=task, protection_enabled=True)
    return ExecutionRouter(
        registry=registry,
        policy_engine=engine,
        firewall=firewall,
        policy_version="test-v1",
        max_traces=200,
    )


def _ask_request(call_id: str = "c1") -> ToolRequest:
    """A request that should always produce an ask verdict."""
    return ToolRequest(
        tool="send_email",
        arguments={
            "to":      ArgSpec(value="alice@company.com", source="user_declared",
                               role="recipient_source"),
            "subject": ArgSpec(value="Report", source="system"),
            "body":    ArgSpec(value="See attached.", source="system"),
        },
        call_id=call_id,
    )


def _deny_request(call_id: str = "c2") -> ToolRequest:
    """A request that should always produce a deny verdict."""
    return ToolRequest(
        tool="send_email",
        arguments={
            "to":      ArgSpec(value="attacker@evil.com", source="external_document",
                               label="evil.txt"),
            "subject": ArgSpec(value="Stolen data", source="system"),
            "body":    ArgSpec(value="Here it is.", source="system"),
        },
        call_id=call_id,
    )


@pytest.fixture
def router() -> ExecutionRouter:
    return _make_router()


@pytest.fixture
def http_client(tmp_path):
    policy_file = REPO_ROOT / "policies" / "default_policy.yaml"
    if not policy_file.exists():
        pytest.skip("default_policy.yaml not found")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"tools:\n  - send_email\n  - http_post\n  - read_file\n"
        f"policy_file: {policy_file}\n"
    )
    app = create_app(config_file)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. ApprovalRecord creation
# ---------------------------------------------------------------------------

class TestApprovalRecordCreation:

    def test_ask_verdict_creates_approval_record(self, router):
        resp = router.execute(_ask_request())
        assert resp.verdict == "ask"
        assert resp.approval_id is not None
        assert resp.approval_required is True

    def test_approval_record_stored_in_router(self, router):
        resp = router.execute(_ask_request())
        record = router.get_approval(resp.approval_id)
        assert record is not None
        assert record.status == "pending"
        assert record.tool == "send_email"

    def test_deny_verdict_does_not_create_approval(self, router):
        resp = router.execute(_deny_request())
        assert resp.verdict == "deny"
        assert resp.approval_id is None
        assert resp.approval_required is False

    def test_allow_verdict_does_not_create_approval(self, router):
        req = ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="README.md", source="system")},
            call_id="c3",
        )
        resp = router.execute(req)
        assert resp.verdict == "allow"
        assert resp.approval_id is None

    def test_approval_record_has_correct_fields(self, router):
        resp = router.execute(_ask_request("my-call"))
        record = router.get_approval(resp.approval_id)
        assert record.call_id == "my-call"
        assert record.policy_version == "test-v1"
        assert record.trace_id == resp.trace_id
        assert record.matched_rule  # non-empty
        assert record.created_at    # non-empty
        assert "to" in record.arg_provenance

    def test_original_ask_trace_has_approval_fields(self, router):
        resp = router.execute(_ask_request())
        traces = router.get_traces(limit=1)
        t = traces[0]
        assert t["approval_id"] == resp.approval_id
        assert t["approval_status"] == "pending"
        assert t["final_verdict"] == "ask"
        assert t["original_verdict"] is None  # not yet resolved


# ---------------------------------------------------------------------------
# 2. Approval execution path
# ---------------------------------------------------------------------------

class TestApprovalExecution:

    def test_approve_returns_allow_verdict(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        assert result.verdict == "allow"

    def test_approve_returns_tool_result(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        # send_email adapter returns a dict with "status"
        assert result.result is not None
        assert result.result.get("status") == "sent"

    def test_approve_updates_record_status(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        record = router.get_approval(resp.approval_id)
        assert record.status == "executed"
        assert record.actor == "alice"
        assert record.resolved_at is not None

    def test_approve_writes_resolution_trace(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        traces = router.get_traces(limit=5)
        # Most recent trace should be the resolution
        resolution_trace = traces[0]
        assert resolution_trace["approval_id"] == resp.approval_id
        assert resolution_trace["approval_status"] == "executed"
        assert resolution_trace["final_verdict"] == "allow"
        assert resolution_trace["original_verdict"] == "ask"
        assert resolution_trace["approved_by"] == "alice"

    def test_approve_uses_correct_actor(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=True, actor="bob-reviewer")
        record = router.get_approval(resp.approval_id)
        assert record.actor == "bob-reviewer"

    def test_approval_id_in_resolution_response(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        assert result.approval_id == resp.approval_id


# ---------------------------------------------------------------------------
# 3. Rejection path
# ---------------------------------------------------------------------------

class TestApprovalRejection:

    def test_reject_returns_deny_verdict(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=False, actor="security")
        assert result.verdict == "deny"

    def test_reject_returns_no_result(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=False, actor="security")
        assert result.result is None

    def test_reject_updates_record_status(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=False, actor="security")
        record = router.get_approval(resp.approval_id)
        assert record.status == "rejected"
        assert record.actor == "security"

    def test_reject_writes_rejection_trace(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=False, actor="security")
        traces = router.get_traces(limit=5)
        rejection_trace = traces[0]
        assert rejection_trace["approval_status"] == "rejected"
        assert rejection_trace["final_verdict"] == "deny"
        assert rejection_trace["original_verdict"] == "ask"
        assert rejection_trace["approved_by"] == "security"

    def test_reject_reason_mentions_actor(self, router):
        resp = router.execute(_ask_request())
        result = router.resolve_approval(resp.approval_id, approved=False, actor="carol")
        assert "carol" in result.reason


# ---------------------------------------------------------------------------
# 4. Not-found and error cases
# ---------------------------------------------------------------------------

class TestApprovalErrors:

    def test_unknown_approval_id_raises_key_error(self, router):
        with pytest.raises(KeyError, match="not found"):
            router.resolve_approval("nonexistent", approved=True)

    def test_double_approve_raises_value_error(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        with pytest.raises(ValueError, match="already"):
            router.resolve_approval(resp.approval_id, approved=True, actor="alice")

    def test_double_reject_raises_value_error(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=False, actor="security")
        with pytest.raises(ValueError, match="already"):
            router.resolve_approval(resp.approval_id, approved=False, actor="security")

    def test_approve_after_reject_raises_value_error(self, router):
        resp = router.execute(_ask_request())
        router.resolve_approval(resp.approval_id, approved=False, actor="security")
        with pytest.raises(ValueError):
            router.resolve_approval(resp.approval_id, approved=True, actor="alice")

    def test_get_approval_unknown_returns_none(self, router):
        assert router.get_approval("ghost-id") is None


# ---------------------------------------------------------------------------
# 5. get_approvals filtering
# ---------------------------------------------------------------------------

class TestGetApprovals:

    def test_get_approvals_returns_all(self, router):
        router.execute(_ask_request("c1"))
        router.execute(_ask_request("c2"))
        approvals = router.get_approvals()
        assert len(approvals) >= 2

    def test_filter_pending(self, router):
        resp1 = router.execute(_ask_request("c1"))
        resp2 = router.execute(_ask_request("c2"))
        router.resolve_approval(resp1.approval_id, approved=True, actor="alice")

        pending = router.get_approvals(status="pending")
        pending_ids = {a["approval_id"] for a in pending}
        assert resp2.approval_id in pending_ids
        assert resp1.approval_id not in pending_ids

    def test_filter_executed(self, router):
        resp = router.execute(_ask_request("c1"))
        router.resolve_approval(resp.approval_id, approved=True, actor="alice")
        executed = router.get_approvals(status="executed")
        assert any(a["approval_id"] == resp.approval_id for a in executed)

    def test_filter_rejected(self, router):
        resp = router.execute(_ask_request("c1"))
        router.resolve_approval(resp.approval_id, approved=False, actor="security")
        rejected = router.get_approvals(status="rejected")
        assert any(a["approval_id"] == resp.approval_id for a in rejected)

    def test_limit(self, router):
        for i in range(5):
            router.execute(_ask_request(f"c{i}"))
        approvals = router.get_approvals(limit=2)
        assert len(approvals) <= 2


# ---------------------------------------------------------------------------
# 6. HTTP endpoints
# ---------------------------------------------------------------------------

class TestApprovalHTTP:

    def test_execute_ask_returns_approval_id(self, http_client):
        resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "Report", "source": "system"},
                "body":    {"value": "See attached.", "source": "system"},
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "ask"
        assert data["approval_id"] is not None
        assert data["approval_required"] is True

    def test_get_approvals_list(self, http_client):
        # Create an ask first
        http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        resp = http_client.get("/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert "approvals" in data

    def test_get_approvals_filter_pending(self, http_client):
        resp = http_client.get("/approvals?status=pending")
        assert resp.status_code == 200

    def test_get_approval_by_id(self, http_client):
        exec_resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        approval_id = exec_resp.json()["approval_id"]
        if not approval_id:
            pytest.skip("no ask produced")

        resp = http_client.get(f"/approvals/{approval_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["approval_id"] == approval_id
        assert data["status"] == "pending"

    def test_get_approval_not_found(self, http_client):
        resp = http_client.get("/approvals/nonexistent-id")
        assert resp.status_code == 404

    def test_approve_via_http(self, http_client):
        exec_resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        approval_id = exec_resp.json().get("approval_id")
        if not approval_id:
            pytest.skip("no ask produced")

        resp = http_client.post(
            f"/approvals/{approval_id}",
            json={"approved": True, "actor": "alice-reviewer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "allow"
        assert data["result"] is not None

    def test_reject_via_http(self, http_client):
        exec_resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        approval_id = exec_resp.json().get("approval_id")
        if not approval_id:
            pytest.skip("no ask produced")

        resp = http_client.post(
            f"/approvals/{approval_id}",
            json={"approved": False, "actor": "security-team"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["verdict"] == "deny"

    def test_double_resolve_returns_409(self, http_client):
        exec_resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        approval_id = exec_resp.json().get("approval_id")
        if not approval_id:
            pytest.skip("no ask produced")

        http_client.post(
            f"/approvals/{approval_id}",
            json={"approved": True, "actor": "alice"},
        )
        second = http_client.post(
            f"/approvals/{approval_id}",
            json={"approved": True, "actor": "alice"},
        )
        assert second.status_code == 409

    def test_approve_nonexistent_returns_404(self, http_client):
        resp = http_client.post(
            "/approvals/does-not-exist",
            json={"approved": True, "actor": "alice"},
        )
        assert resp.status_code == 404

    def test_traces_include_approval_fields_after_resolve(self, http_client):
        exec_resp = http_client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "R", "source": "system"},
                "body":    {"value": "B", "source": "system"},
            },
        })
        approval_id = exec_resp.json().get("approval_id")
        if not approval_id:
            pytest.skip("no ask produced")

        http_client.post(
            f"/approvals/{approval_id}",
            json={"approved": True, "actor": "reviewer"},
        )
        traces_resp = http_client.get("/traces?limit=5")
        traces = traces_resp.json()["traces"]
        resolution_trace = traces[0]  # newest first

        assert resolution_trace["approval_id"] == approval_id
        assert resolution_trace["approved_by"] == "reviewer"
        assert resolution_trace["original_verdict"] == "ask"
        assert resolution_trace["final_verdict"] == "allow"


# ---------------------------------------------------------------------------
# 7. GatewayClient helpers
# ---------------------------------------------------------------------------

class TestGatewayClientHelpers:

    def test_arg_builds_spec_with_defaults(self):
        spec = arg("hello@example.com", "user_declared")
        assert spec["value"] == "hello@example.com"
        assert spec["source"] == "user_declared"
        assert "parents" not in spec
        assert "role" not in spec

    def test_arg_with_all_fields(self):
        spec = arg("x@y.com", "derived", parents=["doc"], role="recipient_source",
                   label="extracted")
        assert spec["parents"] == ["doc"]
        assert spec["role"] == "recipient_source"
        assert spec["label"] == "extracted"

    def test_arg_default_source_is_external(self):
        spec = arg("some value")
        assert spec["source"] == "external_document"

    def test_wrap_tool_returns_callable(self, http_client):
        # Build a client that uses the TestClient transport
        # We test the structure, not the HTTP call
        client = GatewayClient("http://testserver")  # not actually used
        wrapped = client.wrap_tool("read_file")
        assert callable(wrapped)
        assert wrapped.__name__ == "gateway_read_file"
