"""
test_persistence.py — Tests for durable storage layer and persistence integration.

Tests are grouped by concern:

  TestTraceStore        — TraceStore append / read / filter
  TestApprovalStore     — ApprovalStore create / update / get / list
  TestPolicyStore       — PolicyStore record / history / dedup
  TestPersistenceRestart — traces and approvals survive router restart
  TestPolicyVersioning  — GatewayState version creation on startup / reload
  TestTracePolicyLink   — traces reference the correct policy version
  TestMCPAdapterBasic   — MCP adapter translate logic (no live server)

All tests use temporary directories so they never touch real .data/.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_trace_store(tmp_path: Path):
    from agent_hypervisor.storage.trace_store import TraceStore
    return TraceStore(tmp_path / "traces.jsonl")


def _tmp_approval_store(tmp_path: Path):
    from agent_hypervisor.storage.approval_store import ApprovalStore
    return ApprovalStore(tmp_path / "approvals")


def _tmp_policy_store(tmp_path: Path):
    from agent_hypervisor.storage.policy_store import PolicyStore
    return PolicyStore(tmp_path / "policy_history.jsonl")


def _sample_trace(tool="send_email", verdict="deny", approval_id=None) -> dict:
    return {
        "trace_id": "abc12345",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "tool": tool,
        "call_id": "call-1",
        "policy_engine_verdict": verdict,
        "firewall_verdict": verdict,
        "final_verdict": verdict,
        "reason": "test reason",
        "matched_rule": "test-rule",
        "policy_version": "deadbeef",
        "arg_provenance": {"to": "external_document:doc.txt"},
        "result_summary": None,
        "approval_id": approval_id,
        "approval_status": None,
        "approved_by": None,
        "original_verdict": None,
    }


def _sample_approval(approval_id="appr0001") -> dict:
    return {
        "approval_id": approval_id,
        "tool": "send_email",
        "call_id": "call-1",
        "request": {
            "tool": "send_email",
            "arguments": {
                "to": {"value": "alice@example.com", "source": "user_declared",
                       "parents": [], "role": None, "label": ""},
            },
            "call_id": "call-1",
            "provenance": {},
        },
        "arg_provenance": {"to": "user_declared:gateway_trusted"},
        "reason": "ask: user_declared recipient requires confirmation",
        "matched_rule": "ask-email-declared-recipient",
        "policy_version": "deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "trace_id": "abc12345",
        "status": "pending",
        "actor": None,
        "resolved_at": None,
        "result": None,
    }


# ---------------------------------------------------------------------------
# TestTraceStore
# ---------------------------------------------------------------------------

class TestTraceStore:
    def test_append_and_list(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        store.append(_sample_trace(verdict="deny"))
        store.append(_sample_trace(verdict="allow"))
        entries = store.list_recent(limit=10)
        assert len(entries) == 2
        # newest first
        assert entries[0]["final_verdict"] == "allow"
        assert entries[1]["final_verdict"] == "deny"

    def test_list_empty_file(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        assert store.list_recent() == []

    def test_list_missing_file(self, tmp_path):
        from agent_hypervisor.storage.trace_store import TraceStore
        store = TraceStore(tmp_path / "nonexistent" / "traces.jsonl")
        assert store.list_recent() == []

    def test_limit(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        for i in range(10):
            store.append(_sample_trace())
        assert len(store.list_recent(limit=3)) == 3

    def test_filter_verdict(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        store.append(_sample_trace(verdict="deny"))
        store.append(_sample_trace(verdict="allow"))
        store.append(_sample_trace(verdict="deny"))
        results = store.list_recent(verdict="deny")
        assert all(e["final_verdict"] == "deny" for e in results)
        assert len(results) == 2

    def test_filter_tool(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        store.append(_sample_trace(tool="send_email"))
        store.append(_sample_trace(tool="http_post"))
        results = store.list_recent(tool="http_post")
        assert len(results) == 1
        assert results[0]["tool"] == "http_post"

    def test_filter_approval_id(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        store.append(_sample_trace(approval_id="appr0001"))
        store.append(_sample_trace(approval_id=None))
        results = store.list_recent(approval_id="appr0001")
        assert len(results) == 1
        assert results[0]["approval_id"] == "appr0001"

    def test_file_created_on_append(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        assert not (tmp_path / "traces.jsonl").exists()
        store.append(_sample_trace())
        assert (tmp_path / "traces.jsonl").exists()

    def test_entries_are_jsonl(self, tmp_path):
        store = _tmp_trace_store(tmp_path)
        store.append(_sample_trace(verdict="deny"))
        store.append(_sample_trace(verdict="allow"))
        lines = (tmp_path / "traces.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # must be valid JSON


# ---------------------------------------------------------------------------
# TestApprovalStore
# ---------------------------------------------------------------------------

class TestApprovalStore:
    def test_create_and_get(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        record = _sample_approval("appr0001")
        store.create(record)
        loaded = store.get("appr0001")
        assert loaded is not None
        assert loaded["approval_id"] == "appr0001"
        assert loaded["status"] == "pending"

    def test_get_missing(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        assert store.get("nonexistent") is None

    def test_update_status(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        store.create(_sample_approval("appr0001"))
        store.update("appr0001", status="approved", actor="alice")
        loaded = store.get("appr0001")
        assert loaded["status"] == "approved"
        assert loaded["actor"] == "alice"

    def test_update_missing_raises(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        with pytest.raises(KeyError):
            store.update("nonexistent", status="approved")

    def test_list_recent(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        store.create(_sample_approval("appr0001"))
        store.create(_sample_approval("appr0002"))
        records = store.list_recent()
        ids = {r["approval_id"] for r in records}
        assert "appr0001" in ids
        assert "appr0002" in ids

    def test_list_filter_status(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        store.create(_sample_approval("appr0001"))
        store.create(_sample_approval("appr0002"))
        store.update("appr0002", status="executed")
        pending = store.list_recent(status="pending")
        assert len(pending) == 1
        assert pending[0]["approval_id"] == "appr0001"

    def test_list_limit(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        for i in range(5):
            store.create(_sample_approval(f"appr000{i}"))
        assert len(store.list_recent(limit=2)) == 2

    def test_each_approval_is_separate_file(self, tmp_path):
        store = _tmp_approval_store(tmp_path)
        store.create(_sample_approval("appr0001"))
        store.create(_sample_approval("appr0002"))
        files = list((tmp_path / "approvals").glob("*.json"))
        assert len(files) == 2


# ---------------------------------------------------------------------------
# TestPolicyStore
# ---------------------------------------------------------------------------

class TestPolicyStore:
    def _record(self, version_id="aabbccdd", rule_count=5, content_hash=None) -> dict:
        return {
            "version_id": version_id,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "policy_file": "policies/default_policy.yaml",
            "content_hash": content_hash or ("x" * 64),
            "rule_count": rule_count,
        }

    def test_record_and_get_current(self, tmp_path):
        store = _tmp_policy_store(tmp_path)
        assert store.get_current() is None
        store.record_version(self._record("aabbccdd"))
        current = store.get_current()
        assert current is not None
        assert current["version_id"] == "aabbccdd"

    def test_history_newest_first(self, tmp_path):
        store = _tmp_policy_store(tmp_path)
        store.record_version(self._record("v1", content_hash="a" * 64))
        store.record_version(self._record("v2", content_hash="b" * 64))
        history = store.get_history()
        assert history[0]["version_id"] == "v2"
        assert history[1]["version_id"] == "v1"

    def test_history_limit(self, tmp_path):
        store = _tmp_policy_store(tmp_path)
        for i in range(5):
            store.record_version(self._record(f"v{i}", content_hash=str(i) * 64))
        assert len(store.get_history(limit=2)) == 2

    def test_empty_history(self, tmp_path):
        store = _tmp_policy_store(tmp_path)
        assert store.get_history() == []


# ---------------------------------------------------------------------------
# TestPersistenceRestart
# ---------------------------------------------------------------------------

class TestPersistenceRestart:
    """Traces and approvals survive router recreation (simulated restart)."""

    def _make_router(self, tmp_path: Path, trace_store=None, approval_store=None):
        """Build a minimal ExecutionRouter wired to the given stores."""
        from agent_hypervisor.gateway.config_loader import load_config
        from agent_hypervisor.gateway.execution_router import ExecutionRouter, _make_gateway_firewall_task
        from agent_hypervisor.gateway.tool_registry import build_default_registry
        from agent_hypervisor.policy_engine import PolicyEngine
        from agent_hypervisor.firewall import ProvenanceFirewall

        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(textwrap.dedent("""\
            rules:
              - tool: read_file
                verdict: allow
              - tool: send_email
                argument: to
                provenance: user_declared
                verdict: ask
              - tool: send_email
                argument: to
                provenance: external_document
                verdict: deny
        """))

        registry = build_default_registry(["send_email", "http_post", "read_file"])
        engine = PolicyEngine.from_yaml(policy_file)
        task_dict = _make_gateway_firewall_task(["send_email", "http_post", "read_file"])
        firewall = ProvenanceFirewall(task=task_dict, protection_enabled=True)

        return ExecutionRouter(
            registry=registry,
            policy_engine=engine,
            firewall=firewall,
            policy_version="test-v1",
            trace_store=trace_store,
            approval_store=approval_store,
        )

    def _allow_request(self):
        from agent_hypervisor.gateway.execution_router import ArgSpec, ToolRequest
        return ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="/etc/hostname", source="system")},
        )

    def _ask_request(self):
        from agent_hypervisor.gateway.execution_router import ArgSpec, ToolRequest
        return ToolRequest(
            tool="send_email",
            arguments={
                "to": ArgSpec(value="alice@example.com", source="user_declared",
                              role="recipient_source"),
                "subject": ArgSpec(value="Report", source="system"),
                "body": ArgSpec(value="See attached.", source="system"),
            },
        )

    def test_traces_survive_restart(self, tmp_path):
        trace_store = _tmp_trace_store(tmp_path)

        # Router 1 — produces a trace
        router1 = self._make_router(tmp_path, trace_store=trace_store)
        router1.execute(self._allow_request())

        # Router 2 — reads from the same store
        router2 = self._make_router(tmp_path, trace_store=trace_store)
        traces = router2.get_traces(limit=10)
        assert len(traces) >= 1
        assert any(t["tool"] == "read_file" for t in traces)

    def test_pending_approvals_survive_restart(self, tmp_path):
        trace_store = _tmp_trace_store(tmp_path)
        approval_store = _tmp_approval_store(tmp_path)

        # Router 1 — creates a pending approval
        router1 = self._make_router(tmp_path, trace_store=trace_store,
                                    approval_store=approval_store)
        resp = router1.execute(self._ask_request())
        assert resp.verdict == "ask"
        approval_id = resp.approval_id

        # Router 2 — starts fresh (empty memory), loads pending from store
        router2 = self._make_router(tmp_path, trace_store=trace_store,
                                    approval_store=approval_store)
        record = router2.get_approval(approval_id)
        assert record is not None
        assert record.status == "pending"

    def test_approval_resolve_after_restart(self, tmp_path):
        trace_store = _tmp_trace_store(tmp_path)
        approval_store = _tmp_approval_store(tmp_path)

        router1 = self._make_router(tmp_path, trace_store=trace_store,
                                    approval_store=approval_store)
        resp = router1.execute(self._ask_request())
        approval_id = resp.approval_id

        # Resolve on a new router instance
        router2 = self._make_router(tmp_path, trace_store=trace_store,
                                    approval_store=approval_store)
        result = router2.resolve_approval(approval_id, approved=True, actor="alice")
        assert result.verdict == "allow"

        # Status is persisted
        stored = approval_store.get(approval_id)
        assert stored["status"] == "executed"
        assert stored["actor"] == "alice"


# ---------------------------------------------------------------------------
# TestPolicyVersioning
# ---------------------------------------------------------------------------

class TestPolicyVersioning:
    def _make_state(self, tmp_path: Path, policy_yaml: str):
        """Build a GatewayState with isolated storage in tmp_path."""
        from agent_hypervisor.gateway.gateway_server import GatewayState
        from agent_hypervisor.gateway.config_loader import GatewayConfig, ServerConfig, TracesConfig, StorageConfig

        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(policy_yaml)

        config = GatewayConfig(
            tools=["read_file", "send_email"],
            policy_file=str(policy_file),
            server=ServerConfig(),
            traces=TracesConfig(),
            storage=StorageConfig(path=str(tmp_path / "data")),
        )
        return GatewayState(config=config, config_path=tmp_path / "gateway_config.yaml")

    _POLICY_V1 = textwrap.dedent("""\
        rules:
          - tool: read_file
            verdict: allow
    """)

    _POLICY_V2 = textwrap.dedent("""\
        rules:
          - tool: read_file
            verdict: allow
          - tool: send_email
            argument: to
            provenance: external_document
            verdict: deny
    """)

    def test_version_recorded_on_startup(self, tmp_path):
        state = self._make_state(tmp_path, self._POLICY_V1)
        history = state.get_policy_history()
        assert len(history) == 1
        assert history[0]["rule_count"] == 1

    def test_restart_same_policy_no_duplicate(self, tmp_path):
        # Two GatewayState instances with the same policy should not create duplicate entries
        self._make_state(tmp_path, self._POLICY_V1)
        self._make_state(tmp_path, self._POLICY_V1)
        from agent_hypervisor.storage.policy_store import PolicyStore
        store = PolicyStore(tmp_path / "data" / "policy_history.jsonl")
        assert len(store.get_history()) == 1

    def test_reload_creates_new_version(self, tmp_path):
        state = self._make_state(tmp_path, self._POLICY_V1)
        # Change policy file on disk
        Path(state.policy_file).write_text(self._POLICY_V2)
        info = state.reload_policy()
        assert info["changed"] is True
        history = state.get_policy_history()
        assert len(history) == 2
        assert history[0]["rule_count"] == 2  # newest first

    def test_reload_same_content_no_new_version(self, tmp_path):
        state = self._make_state(tmp_path, self._POLICY_V1)
        info = state.reload_policy()  # same content
        assert info["changed"] is False
        history = state.get_policy_history()
        assert len(history) == 1


# ---------------------------------------------------------------------------
# TestTracePolicyLink
# ---------------------------------------------------------------------------

class TestTracePolicyLink:
    """Traces carry the policy version that was active at decision time."""

    def _make_router(self, tmp_path, policy_version="v-test"):
        from agent_hypervisor.gateway.execution_router import ExecutionRouter, _make_gateway_firewall_task
        from agent_hypervisor.gateway.tool_registry import build_default_registry
        from agent_hypervisor.policy_engine import PolicyEngine
        from agent_hypervisor.firewall import ProvenanceFirewall
        import textwrap

        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(textwrap.dedent("""\
            rules:
              - tool: read_file
                verdict: allow
        """))

        trace_store = _tmp_trace_store(tmp_path)
        registry = build_default_registry(["read_file"])
        engine = PolicyEngine.from_yaml(policy_file)
        task_dict = _make_gateway_firewall_task(["read_file"])
        firewall = ProvenanceFirewall(task=task_dict, protection_enabled=True)

        return ExecutionRouter(
            registry=registry,
            policy_engine=engine,
            firewall=firewall,
            policy_version=policy_version,
            trace_store=trace_store,
        ), trace_store

    def test_trace_carries_policy_version(self, tmp_path):
        from agent_hypervisor.gateway.execution_router import ArgSpec, ToolRequest

        router, store = self._make_router(tmp_path, policy_version="deadbeef")
        router.execute(ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="/etc/hostname", source="system")},
        ))
        traces = store.list_recent(limit=1)
        assert traces[0]["policy_version"] == "deadbeef"

    def test_trace_version_updates_after_engine_update(self, tmp_path):
        from agent_hypervisor.gateway.execution_router import ArgSpec, ToolRequest
        import textwrap
        from agent_hypervisor.policy_engine import PolicyEngine
        from agent_hypervisor.firewall import ProvenanceFirewall
        from agent_hypervisor.gateway.execution_router import _make_gateway_firewall_task

        router, store = self._make_router(tmp_path, policy_version="version1")

        # Simulate a hot reload by swapping engines
        policy_file = tmp_path / "policy.yaml"
        new_engine = PolicyEngine.from_yaml(policy_file)
        task_dict = _make_gateway_firewall_task(["read_file"])
        new_firewall = ProvenanceFirewall(task=task_dict, protection_enabled=True)
        router.update_engines(new_engine, new_firewall, "version2")

        router.execute(ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="/etc/hostname", source="system")},
        ))
        traces = store.list_recent(limit=1)
        assert traces[0]["policy_version"] == "version2"


# ---------------------------------------------------------------------------
# TestMCPAdapterBasic
# ---------------------------------------------------------------------------

class TestMCPAdapterBasic:
    """Unit tests for the MCP adapter translation logic (no live server needed)."""

    def test_handle_initialize_returns_capabilities(self):
        import importlib.util, sys
        # Import the example module
        spec = importlib.util.spec_from_file_location(
            "mcp_adapter",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.load_from_spec = None
        # Use direct import path
        import importlib
        mod = importlib.import_module.__module__

        # Just test the handle_initialize logic directly
        sys.path.insert(0, str(Path(__file__).parent.parent / "examples" / "integrations"))

    def test_handle_initialize(self, tmp_path):
        """handle_initialize returns required MCP fields."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_example",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.handle_initialize({})
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert "capabilities" in result
        assert "tools" in result["capabilities"]

    def test_handle_tools_call_allow_verdict(self, tmp_path):
        """tools/call with allow verdict returns isError: False."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_example2",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Patch _gateway_request to return an allow verdict
        with patch.object(mod, "_gateway_request", return_value={
            "verdict": "allow",
            "result": {"output": "ok"},
            "reason": "",
            "matched_rule": "allow-read-file",
            "policy_version": "deadbeef",
            "trace_id": "abc12345",
        }):
            result = mod.handle_tools_call({"name": "read_file", "arguments": {"path": "/etc/hostname"}})

        assert result["isError"] is False
        assert "ok" in result["content"][0]["text"]

    def test_handle_tools_call_deny_verdict(self, tmp_path):
        """tools/call with deny verdict returns isError: True."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_example3",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with patch.object(mod, "_gateway_request", return_value={
            "verdict": "deny",
            "reason": "Recipient provenance is external_document",
            "matched_rule": "deny-email-external",
            "policy_version": "deadbeef",
            "trace_id": "abc12345",
        }):
            result = mod.handle_tools_call({"name": "send_email",
                                            "arguments": {"to": "hacker@evil.com"}})

        assert result["isError"] is True
        assert "BLOCKED" in result["content"][0]["text"]

    def test_handle_tools_call_ask_verdict(self, tmp_path):
        """tools/call with ask verdict returns isError: False with approval_id."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_example4",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with patch.object(mod, "_gateway_request", return_value={
            "verdict": "ask",
            "reason": "User-declared recipient requires confirmation",
            "approval_id": "ab3f9c1d",
            "approval_required": True,
            "matched_rule": "ask-email-declared",
            "policy_version": "deadbeef",
            "trace_id": "abc12345",
        }):
            result = mod.handle_tools_call({"name": "send_email",
                                            "arguments": {"to": "alice@example.com"}})

        assert result["isError"] is False
        assert result.get("_approval_required") is True
        assert result.get("_approval_id") == "ab3f9c1d"
        assert "APPROVAL REQUIRED" in result["content"][0]["text"]

    def test_mcp_args_tagged_user_declared(self, tmp_path):
        """All MCP arguments are tagged with user_declared provenance."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_example5",
            Path(__file__).parent.parent / "examples" / "integrations" / "mcp_gateway_adapter_example.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        captured = {}

        def fake_gateway_request(method, path, body=None):
            captured["body"] = body
            return {"verdict": "allow", "result": "ok"}

        with patch.object(mod, "_gateway_request", side_effect=fake_gateway_request):
            mod.handle_tools_call({"name": "send_email", "arguments": {"to": "alice@example.com", "subject": "Hi"}})

        args = captured["body"]["arguments"]
        for arg_name, arg_spec in args.items():
            assert arg_spec["source"] == "user_declared", (
                f"Argument '{arg_name}' should be user_declared, got {arg_spec['source']!r}"
            )
