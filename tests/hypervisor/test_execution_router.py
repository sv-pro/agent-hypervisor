import pytest
from unittest.mock import MagicMock
from pathlib import Path
from typing import Any

from agent_hypervisor.hypervisor.gateway.execution_router import (
    ExecutionRouter,
    ToolRequest,
    ArgSpec,
)
from agent_hypervisor.hypervisor.storage.approval_store import ApprovalStore
from agent_hypervisor.hypervisor.gateway.tool_registry import ToolRegistry, ToolDefinition


class MockPolicyEngine:
    def __init__(self, verdict="allow"):
        self._verdict = verdict

    def evaluate(self, call, registry):
        from agent_hypervisor.hypervisor.policy_engine import RuleVerdict
        result = MagicMock()
        mock_verdict = MagicMock()
        mock_verdict.value = self._verdict
        result.verdict = mock_verdict
        result.reason = "mock policy engine"
        result.matched_rule = "mock-rule"
        return result


class MockFirewall:
    def __init__(self, verdict="allow"):
        self._verdict = verdict

    def check(self, call, registry):
        result = MagicMock()
        mock_verdict = MagicMock()
        mock_verdict.value = self._verdict
        result.verdict = mock_verdict
        result.reason = "mock firewall"
        result.violated_rules = []
        return result


def _make_registry(tool_name: str, adapter_fn) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(ToolDefinition(
        name=tool_name,
        description="mock tool",
        side_effect_class="read_only",
        adapter=adapter_fn
    ))
    return registry


@pytest.fixture
def mock_registry():
    def mock_adapter(args: dict[str, Any]) -> str:
        return f"Executed with {args}"
    return _make_registry("mock_tool", mock_adapter)


@pytest.fixture
def store(tmp_path: Path) -> ApprovalStore:
    return ApprovalStore(tmp_path)


def test_execute_allow_workflow(mock_registry):
    pe = MockPolicyEngine(verdict="allow")
    fw = MockFirewall(verdict="allow")
    router = ExecutionRouter(registry=mock_registry, policy_engine=pe, firewall=fw)

    request = ToolRequest(
        tool="mock_tool",
        arguments={"x": ArgSpec(value=42)}
    )
    response = router.execute(request)
    assert response.verdict == "allow"
    assert response.result == "Executed with {'x': 42}"
    assert not response.approval_required


def test_execute_ask_creates_approval(mock_registry, store):
    pe = MockPolicyEngine(verdict="ask")
    fw = MockFirewall(verdict="allow")
    router = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    request = ToolRequest(
        tool="mock_tool",
        arguments={"y": ArgSpec(value=100)}
    )
    response = router.execute(request)

    assert response.verdict == "ask"
    assert response.approval_required is True
    assert response.approval_id is not None
    assert response.result is None

    # Check store has it
    record = store.get(response.approval_id)
    assert record is not None
    assert record["status"] == "pending"


def test_resolve_approval_accept(mock_registry, store):
    pe = MockPolicyEngine(verdict="ask")
    fw = MockFirewall(verdict="allow")
    router = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    req = ToolRequest(tool="mock_tool", arguments={"auth": ArgSpec(value="ok")})
    resp1 = router.execute(req)
    approval_id = resp1.approval_id

    # Resolve accept
    resp2 = router.resolve_approval(approval_id, approved=True, actor="operator")

    assert resp2.verdict == "allow"
    assert resp2.result == "Executed with {'auth': 'ok'}"

    record = store.get(approval_id)
    assert record["status"] == "executed"
    assert record["actor"] == "operator"


def test_resolve_approval_reject(mock_registry, store):
    pe = MockPolicyEngine(verdict="ask")
    fw = MockFirewall(verdict="allow")
    router = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    req = ToolRequest(tool="mock_tool", arguments={})
    resp1 = router.execute(req)
    approval_id = resp1.approval_id

    # Resolve reject
    resp2 = router.resolve_approval(approval_id, approved=False, actor="operator2")

    assert resp2.verdict == "deny"
    assert resp2.result is None

    record = store.get(approval_id)
    assert record["status"] == "rejected"
    assert record["actor"] == "operator2"


def test_recovery_from_store(mock_registry, store):
    # Setup initial router and create a pending approval
    pe = MockPolicyEngine(verdict="ask")
    fw = MockFirewall(verdict="allow")
    router1 = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    req = ToolRequest(tool="mock_tool", arguments={"restart": ArgSpec(value=1)})
    resp = router1.execute(req)
    approval_id = resp.approval_id

    # Simulate Gateway restart: New router instance but same store
    router2 = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    # Resolve should work on the new router instance
    resp_resolve = router2.resolve_approval(approval_id, approved=True, actor="restart_op")
    assert resp_resolve.verdict == "allow"
    assert resp_resolve.result == "Executed with {'restart': 1}"


def test_resolve_approval_already_resolved(mock_registry, store):
    pe = MockPolicyEngine(verdict="ask")
    fw = MockFirewall(verdict="allow")
    router = ExecutionRouter(
        registry=mock_registry, 
        policy_engine=pe, 
        firewall=fw,
        approval_store=store
    )

    req = ToolRequest(tool="mock_tool", arguments={})
    resp1 = router.execute(req)
    approval_id = resp1.approval_id

    # Resolve accept
    router.resolve_approval(approval_id, approved=True, actor="op1")

    # Second resolve should fail
    with pytest.raises(ValueError, match="is already 'executed' and cannot be resolved again"):
        router.resolve_approval(approval_id, approved=False, actor="op2")
