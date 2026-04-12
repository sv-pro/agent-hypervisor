"""
test_mcp_gateway.py — Safety invariant and behavior tests for the AH MCP Gateway.

Tests are organized into three groups:

  Group 1: ToolSurfaceRenderer (tools/list virtualization)
    - Only manifest-declared tools appear
    - Undeclared tools do not appear
    - Tools with no adapter do not appear

  Group 2: ToolCallEnforcer (deterministic enforcement)
    - Declared tool is allowed
    - Undeclared tool is denied (manifest:tool_not_declared)
    - Constraint violation is denied
    - Same input → same decision (determinism check)

  Group 3: MCPGateway HTTP endpoint (integration)
    - tools/list returns only manifest tools
    - tools/call to undeclared tool fails closed
    - tools/call to declared tool returns result
    - Manifest load failure does not create a permissive gateway
    - initialize handshake returns correct capabilities

Shared fixtures build a minimal in-memory setup (no filesystem needed for
unit tests; integration tests use real manifest files).
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

MANIFESTS_DIR = Path(__file__).parent.parent.parent / "manifests"


def _make_manifest(tool_names: list[str]):
    """Build a WorldManifest from a list of tool names (no constraints)."""
    from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
    return WorldManifest(
        workflow_id="test-world",
        version="1.0",
        capabilities=[CapabilityConstraint(tool=name) for name in tool_names],
    )


def _make_registry(tool_names: list[str]):
    """Build a ToolRegistry pre-populated with the built-in adapters, filtered."""
    from agent_hypervisor.hypervisor.gateway.tool_registry import build_default_registry
    return build_default_registry(tool_names)


# ---------------------------------------------------------------------------
# Group 1: ToolSurfaceRenderer
# ---------------------------------------------------------------------------

class TestToolSurfaceRenderer:

    def test_only_manifest_tools_appear(self):
        """tools/list must return only manifest-declared tools."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file", "send_email", "http_post"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        tools = renderer.render()
        names = [t.name for t in tools]

        assert names == ["read_file"], f"Expected only read_file, got {names}"

    def test_undeclared_tool_does_not_appear(self):
        """Undeclared tools must be absent — not just unlisted."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file", "send_email", "http_post"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        tools = renderer.render()
        names = [t.name for t in tools]

        assert "send_email" not in names
        assert "http_post" not in names

    def test_tool_with_no_adapter_does_not_appear(self):
        """Tool declared in manifest but with no adapter must not appear."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["read_file", "nonexistent_tool"])
        registry = _make_registry(["read_file"])  # nonexistent_tool not in registry
        renderer = ToolSurfaceRenderer(manifest, registry)

        tools = renderer.render()
        names = [t.name for t in tools]

        assert "nonexistent_tool" not in names
        assert "read_file" in names

    def test_empty_manifest_renders_no_tools(self):
        """Empty manifest → empty visible surface."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest([])
        registry = _make_registry(["read_file", "send_email"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        assert renderer.render() == []

    def test_is_visible_returns_true_for_declared_tool(self):
        """is_visible must return True for a manifest-declared tool with an adapter."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        assert renderer.is_visible("read_file") is True

    def test_is_visible_returns_false_for_undeclared_tool(self):
        """is_visible must return False for a tool not in the manifest."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file", "send_email"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        assert renderer.is_visible("send_email") is False

    def test_render_order_follows_manifest(self):
        """Tool order in render() must follow manifest declaration order."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer
        manifest = _make_manifest(["send_email", "read_file"])
        registry = _make_registry(["read_file", "send_email"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        names = [t.name for t in renderer.render()]
        assert names == ["send_email", "read_file"]

    def test_input_schema_enforces_path_globs(self):
        """paths constraints should become JSON Schema path assertions."""
        from jsonschema import validate, ValidationError
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer

        manifest = WorldManifest(
            workflow_id="paths-world",
            capabilities=[
                CapabilityConstraint(tool="read_file", constraints={"paths": ["/safe/*"]})
            ],
        )
        registry = _make_registry(["read_file"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        schema = renderer.render()[0].inputSchema
        validate(instance={"path": "/safe/report.txt"}, schema=schema)
        with pytest.raises(ValidationError):
            validate(instance={"path": "/etc/passwd"}, schema=schema)

    def test_input_schema_enforces_domain_enum(self):
        """domains constraints should become JSON Schema enum assertions."""
        from jsonschema import validate, ValidationError
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        from agent_hypervisor.hypervisor.mcp_gateway import ToolSurfaceRenderer

        manifest = WorldManifest(
            workflow_id="domains-world",
            capabilities=[
                CapabilityConstraint(
                    tool="http_post",
                    constraints={"domains": ["internal.local", "api.partner.com"]},
                )
            ],
        )
        registry = _make_registry(["http_post"])
        renderer = ToolSurfaceRenderer(manifest, registry)

        schema = renderer.render()[0].inputSchema
        validate(instance={"domain": "internal.local"}, schema=schema)
        with pytest.raises(ValidationError):
            validate(instance={"domain": "evil.example"}, schema=schema)


# ---------------------------------------------------------------------------
# Group 2: ToolCallEnforcer
# ---------------------------------------------------------------------------

class TestToolCallEnforcer:

    def test_declared_tool_is_allowed(self):
        """tool/call to a manifest-declared tool must be allowed."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"})
        assert decision.allowed, f"Expected allow, got {decision.verdict}: {decision.reason}"

    def test_undeclared_tool_is_denied(self):
        """tool/call to an undeclared tool must fail closed."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file", "send_email"])
        enforcer = ToolCallEnforcer(manifest, registry)

        decision = enforcer.enforce("send_email", {"to": "x@y.com"})
        assert decision.denied
        assert decision.matched_rule == "manifest:tool_not_declared"

    def test_undeclared_tool_reason_mentions_world(self):
        """Denial reason must clarify the tool does not exist in this world."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest([])
        registry = _make_registry(["send_email"])
        enforcer = ToolCallEnforcer(manifest, registry)

        decision = enforcer.enforce("send_email", {})
        assert "world" in decision.reason.lower()

    def test_tool_with_no_adapter_is_denied(self):
        """Declared tool with no adapter must fail closed."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["ghost_tool"])
        registry = _make_registry([])  # empty registry
        enforcer = ToolCallEnforcer(manifest, registry)

        decision = enforcer.enforce("ghost_tool", {})
        assert decision.denied
        assert decision.matched_rule == "registry:no_adapter"

    def test_determinism_same_input_same_decision(self):
        """Same inputs must produce the same decision every time."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        args = {"path": "/tmp/test.txt"}
        decisions = [enforcer.enforce("read_file", args) for _ in range(10)]
        verdicts = {d.verdict for d in decisions}
        rules = {d.matched_rule for d in decisions}

        assert len(verdicts) == 1, f"Non-deterministic verdicts: {verdicts}"
        assert len(rules) == 1, f"Non-deterministic rules: {rules}"

    def test_undeclared_tool_determinism(self):
        """Denial for undeclared tool must be deterministic."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file", "http_post"])
        enforcer = ToolCallEnforcer(manifest, registry)

        decisions = [enforcer.enforce("http_post", {"url": "http://x"}) for _ in range(5)]
        assert all(d.denied for d in decisions)
        assert len({d.matched_rule for d in decisions}) == 1

    def test_enforce_never_raises(self):
        """enforce() must never raise — all error conditions produce deny decisions."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        # These should not raise
        d1 = enforcer.enforce("", {})
        d2 = enforcer.enforce("read_file", None or {})
        d3 = enforcer.enforce("nonexistent", {"x": object()})

        assert d1.denied
        assert d2.allowed or d2.denied  # just must not raise
        assert d3.denied

    def test_constraint_violation_is_denied(self):
        """Manifest constraint violation must fail closed."""
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        # Manifest allows read_file only for /safe/**
        manifest = WorldManifest(
            workflow_id="constrained-world",
            capabilities=[
                CapabilityConstraint(tool="read_file", constraints={"paths": ["/safe/*"]})
            ],
        )
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        decision = enforcer.enforce("read_file", {"path": "/etc/passwd"})
        assert decision.denied
        assert "constraint" in decision.matched_rule


# ---------------------------------------------------------------------------
# Group 3: MCP Gateway HTTP integration
# ---------------------------------------------------------------------------

class TestMCPGatewayHTTP:
    """
    Integration tests using the real FastAPI app and real manifest files.

    These use httpx in ASGI mode so no server is needed.
    """

    @pytest.fixture
    def client(self):
        """Create an httpx test client for the MCP gateway."""
        pytest.importorskip("httpx")
        from httpx import AsyncClient, ASGITransport
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        manifest_path = MANIFESTS_DIR / "example_world.yaml"
        if not manifest_path.exists():
            pytest.skip(f"Manifest not found: {manifest_path}")

        app = create_mcp_app(manifest_path)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Health endpoint must return running status and visible tools."""
        async with client as c:
            resp = await c.get("/mcp/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "visible_tools" in data

    @pytest.mark.asyncio
    async def test_tools_list_only_manifest_tools(self, client):
        """tools/list must return only tools declared in the manifest."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        async with client as c:
            resp = await c.post("/mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        tool_names = [t["name"] for t in data["result"]["tools"]]
        # example_world.yaml declares: read_file, send_email
        assert "read_file" in tool_names
        assert "send_email" in tool_names
        # http_post is registered but NOT in example_world.yaml
        assert "http_post" not in tool_names

    @pytest.mark.asyncio
    async def test_tools_call_undeclared_tool_fails_closed(self, client):
        """tools/call to undeclared tool must return a JSON-RPC error."""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "http_post", "arguments": {"url": "http://evil.example.com"}},
        }
        async with client as c:
            resp = await c.post("/mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data, f"Expected error, got: {data}"
        assert data["error"]["code"] in (-32001, -32002)  # MCP_TOOL_NOT_FOUND or DENIED

    @pytest.mark.asyncio
    async def test_tools_call_declared_tool_succeeds(self, client):
        """tools/call to a declared tool must return a result."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            tmp_path = f.name
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "read_file", "arguments": {"path": tmp_path}},
            }
            async with client as c:
                resp = await c.post("/mcp", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert "result" in data, f"Expected result, got: {data}"
            assert data["result"]["isError"] is False
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self, client):
        """initialize method must return server capabilities."""
        payload = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        async with client as c:
            resp = await c.post("/mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert "capabilities" in data["result"]
        assert "serverInfo" in data["result"]

    @pytest.mark.asyncio
    async def test_unknown_method_returns_method_not_found(self, client):
        """Unknown JSON-RPC method must return -32601 MethodNotFound."""
        payload = {"jsonrpc": "2.0", "id": 99, "method": "nonexistent/method"}
        async with client as c:
            resp = await c.post("/mcp", json=payload)
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Group 4: SessionWorldResolver
# ---------------------------------------------------------------------------

class TestSessionWorldResolver:

    def test_resolver_loads_manifest(self, tmp_path):
        """Resolver must load a valid manifest from disk."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: test\ncapabilities:\n  - tool: read_file\n"
        )
        resolver = SessionWorldResolver(manifest_file)
        manifest = resolver.resolve()
        assert manifest.workflow_id == "test"
        assert manifest.tool_names() == ["read_file"]

    def test_resolver_raises_on_missing_file(self, tmp_path):
        """Resolver must raise if the manifest file does not exist."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        with pytest.raises(Exception):
            SessionWorldResolver(tmp_path / "does_not_exist.yaml")

    def test_resolver_resolve_is_deterministic(self, tmp_path):
        """resolve() must return the same manifest every call."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text("workflow_id: test\ncapabilities:\n  - tool: read_file\n")
        resolver = SessionWorldResolver(manifest_file)

        m1 = resolver.resolve(session_id="s1")
        m2 = resolver.resolve(session_id="s2")
        assert m1 is m2  # same object (no reloading between calls)

    def test_reload_picks_up_changes(self, tmp_path):
        """reload() must pick up manifest file changes."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text("workflow_id: v1\ncapabilities:\n  - tool: read_file\n")
        resolver = SessionWorldResolver(manifest_file)
        assert resolver.resolve().workflow_id == "v1"

        # Update the file
        manifest_file.write_text("workflow_id: v2\ncapabilities:\n  - tool: send_email\n")
        ok = resolver.reload()
        assert ok
        assert resolver.resolve().workflow_id == "v2"

    def test_manifest_load_failure_does_not_fail_open(self, tmp_path):
        """If manifest fails to load, gateway startup must fail (not open)."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("this is not valid yaml: [\n")
        with pytest.raises(Exception):
            SessionWorldResolver(bad_file)


# ---------------------------------------------------------------------------
# Group 5: PolicyEngine integration
# ---------------------------------------------------------------------------

class TestPolicyEngineIntegration:
    """
    Verify that the optional PolicyEngine wires correctly into ToolCallEnforcer
    and that create_mcp_app(use_default_policy=True) loads the bundled policy.
    """

    def _make_allow_engine(self):
        """PolicyEngine that allows every tool."""
        from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
        return PolicyEngine.from_dict({"rules": [{"tool": "*", "verdict": "allow"}]})

    def _make_deny_engine(self, tool_name: str):
        """PolicyEngine that denies a specific tool."""
        from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
        return PolicyEngine.from_dict(
            {"rules": [{"tool": tool_name, "verdict": "deny"}]}
        )

    def test_policy_engine_deny_overrides_manifest_allow(self):
        """A policy-engine deny on a manifest-declared tool must fail closed."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        engine = self._make_deny_engine("read_file")
        enforcer = ToolCallEnforcer(manifest, registry, policy_engine=engine)

        decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"})
        assert decision.denied
        assert decision.matched_rule.startswith("policy:")

    def test_policy_engine_allow_passes_to_constraint_check(self):
        """A policy-engine allow on a manifest-declared tool proceeds to constraint check."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        engine = self._make_allow_engine()
        enforcer = ToolCallEnforcer(manifest, registry, policy_engine=engine)

        decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"})
        assert decision.allowed

    def test_policy_engine_error_fails_closed(self):
        """If the policy engine raises, the enforcer must fail closed."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from unittest.mock import MagicMock
        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        bad_engine = MagicMock()
        bad_engine.evaluate.side_effect = RuntimeError("policy engine boom")
        enforcer = ToolCallEnforcer(manifest, registry, policy_engine=bad_engine)

        decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"})
        assert decision.denied
        assert decision.matched_rule == "policy:evaluation_error"

    def test_use_default_policy_loads_bundled_policy(self, tmp_path):
        """create_mcp_app(use_default_policy=True) must load the bundled policy."""
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: policy-test\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file, use_default_policy=True)
        gw = app.state.gw
        assert gw.policy_engine is not None

    def test_use_default_policy_false_leaves_engine_none(self, tmp_path):
        """create_mcp_app() without use_default_policy must leave policy_engine as None."""
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: no-policy\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file)
        gw = app.state.gw
        assert gw.policy_engine is None

    def test_explicit_policy_engine_is_not_overridden(self, tmp_path):
        """Passing an explicit policy_engine must not be replaced even if use_default_policy=True."""
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: explicit\ncapabilities:\n  - tool: read_file\n"
        )
        custom_engine = self._make_allow_engine()
        app = create_mcp_app(manifest_file, policy_engine=custom_engine, use_default_policy=True)
        gw = app.state.gw
        assert gw.policy_engine is custom_engine


# ---------------------------------------------------------------------------
# Group 6: Per-session manifest bindings
# ---------------------------------------------------------------------------

class TestPerSessionManifests:
    """
    Tests for per-session WorldManifest bindings.

    Core invariant: different sessions can operate in different worlds
    simultaneously. Sessions without an explicit binding fall back to the
    gateway-level default.
    """

    def _write_manifest(self, path, workflow_id: str, tools: list[str]) -> None:
        caps = "\n".join(f"  - tool: {t}" for t in tools)
        path.write_text(f"workflow_id: {workflow_id}\ncapabilities:\n{caps}\n")

    # --- SessionWorldResolver unit tests ---

    def test_unregistered_session_gets_default(self, tmp_path):
        """Sessions without a binding must use the default manifest."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        resolver = SessionWorldResolver(default_file)

        manifest = resolver.resolve(session_id="unknown-session")
        assert manifest.workflow_id == "default-world"

    def test_registered_session_gets_own_manifest(self, tmp_path):
        """A session with a registered manifest must receive that manifest."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        session_file = tmp_path / "session.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        self._write_manifest(session_file, "session-world", ["send_email"])
        resolver = SessionWorldResolver(default_file)

        resolver.register_session("s1", session_file)
        manifest = resolver.resolve(session_id="s1")
        assert manifest.workflow_id == "session-world"

    def test_registered_session_does_not_affect_other_sessions(self, tmp_path):
        """Per-session binding must not affect sessions without a binding."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        session_file = tmp_path / "session.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        self._write_manifest(session_file, "session-world", ["send_email"])
        resolver = SessionWorldResolver(default_file)

        resolver.register_session("s1", session_file)
        assert resolver.resolve(session_id="s2").workflow_id == "default-world"
        assert resolver.resolve(session_id=None).workflow_id == "default-world"

    def test_unregister_session_reverts_to_default(self, tmp_path):
        """Unregistering a session must revert it to the default manifest."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        session_file = tmp_path / "session.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        self._write_manifest(session_file, "session-world", ["send_email"])
        resolver = SessionWorldResolver(default_file)

        resolver.register_session("s1", session_file)
        assert resolver.resolve(session_id="s1").workflow_id == "session-world"

        removed = resolver.unregister_session("s1")
        assert removed is True
        assert resolver.resolve(session_id="s1").workflow_id == "default-world"

    def test_unregister_nonexistent_session_is_idempotent(self, tmp_path):
        """Unregistering a session that was never bound must return False safely."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        resolver = SessionWorldResolver(default_file)

        removed = resolver.unregister_session("does-not-exist")
        assert removed is False

    def test_register_session_fails_closed_on_bad_manifest(self, tmp_path):
        """register_session must raise and NOT register if the manifest is invalid."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        bad_file = tmp_path / "bad.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        bad_file.write_text("this: [is: invalid yaml:\n")
        resolver = SessionWorldResolver(default_file)

        with pytest.raises(Exception):
            resolver.register_session("s1", bad_file)

        # Session must NOT have been registered
        assert resolver.resolve(session_id="s1").workflow_id == "default-world"

    def test_session_registry_returns_snapshot(self, tmp_path):
        """session_registry() must return a snapshot of current bindings."""
        from agent_hypervisor.hypervisor.mcp_gateway import SessionWorldResolver
        default_file = tmp_path / "default.yaml"
        s1_file = tmp_path / "s1.yaml"
        s2_file = tmp_path / "s2.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        self._write_manifest(s1_file, "world-s1", ["send_email"])
        self._write_manifest(s2_file, "world-s2", ["read_file"])
        resolver = SessionWorldResolver(default_file)

        resolver.register_session("alice", s1_file)
        resolver.register_session("bob", s2_file)
        registry = resolver.session_registry()

        assert registry == {"alice": "world-s1", "bob": "world-s2"}

    # --- HTTP endpoint tests ---

    @pytest.fixture
    def two_world_client(self, tmp_path):
        """
        Client with a gateway that has two manifests on disk:
          - default_world.yaml: read_file only
          - email_world.yaml: send_email only
        """
        pytest.importorskip("httpx")
        from httpx import AsyncClient, ASGITransport
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        default_file = tmp_path / "default_world.yaml"
        email_file = tmp_path / "email_world.yaml"
        self._write_manifest(default_file, "default-world", ["read_file"])
        self._write_manifest(email_file, "email-world", ["send_email"])

        app = create_mcp_app(default_file)
        # Attach paths for use in tests
        app.state.email_manifest_path = str(email_file)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        return client

    @pytest.mark.asyncio
    async def test_bind_session_changes_visible_tools(self, two_world_client):
        """After binding, tools/list for that session must show the bound world's tools."""
        async with two_world_client as c:
            email_path = c._transport.app.state.email_manifest_path

            # Bind session "s1" to email world
            bind_resp = await c.post(
                "/mcp/sessions/s1/bind",
                json={"manifest_path": email_path},
            )
            assert bind_resp.status_code == 200
            bind_data = bind_resp.json()
            assert bind_data["status"] == "bound"
            assert bind_data["workflow_id"] == "email-world"
            assert "send_email" in bind_data["visible_tools"]

            # tools/list with session s1 must show send_email
            tools_resp = await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {
                    "_meta": {"session_id": "s1"}
                }},
            )
            assert tools_resp.status_code == 200
            tool_names = [t["name"] for t in tools_resp.json()["result"]["tools"]]
            assert "send_email" in tool_names
            assert "read_file" not in tool_names

    @pytest.mark.asyncio
    async def test_session_binding_does_not_affect_default(self, two_world_client):
        """Binding one session must not change another session's visible tools."""
        async with two_world_client as c:
            email_path = c._transport.app.state.email_manifest_path

            # Bind session "s1" to email world
            await c.post("/mcp/sessions/s1/bind", json={"manifest_path": email_path})

            # tools/list without session_id still shows default world
            tools_resp = await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            tool_names = [t["name"] for t in tools_resp.json()["result"]["tools"]]
            assert "read_file" in tool_names
            assert "send_email" not in tool_names

    @pytest.mark.asyncio
    async def test_unbind_session_reverts_to_default(self, two_world_client):
        """DELETE /mcp/sessions/{id} must revert the session to the default world."""
        async with two_world_client as c:
            email_path = c._transport.app.state.email_manifest_path

            # Bind then unbind
            await c.post("/mcp/sessions/s1/bind", json={"manifest_path": email_path})
            del_resp = await c.delete("/mcp/sessions/s1")
            assert del_resp.status_code == 200
            assert del_resp.json()["status"] == "unbound"

            # tools/list for s1 must now show default world
            tools_resp = await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {
                    "_meta": {"session_id": "s1"}
                }},
            )
            tool_names = [t["name"] for t in tools_resp.json()["result"]["tools"]]
            assert "read_file" in tool_names
            assert "send_email" not in tool_names

    @pytest.mark.asyncio
    async def test_list_sessions_endpoint(self, two_world_client):
        """GET /mcp/sessions must list all active bindings."""
        async with two_world_client as c:
            email_path = c._transport.app.state.email_manifest_path

            # Initially empty
            list_resp = await c.get("/mcp/sessions")
            assert list_resp.status_code == 200
            data = list_resp.json()
            assert data["session_count"] == 0
            assert data["sessions"] == {}

            # Bind a session
            await c.post("/mcp/sessions/alice/bind", json={"manifest_path": email_path})

            list_resp2 = await c.get("/mcp/sessions")
            data2 = list_resp2.json()
            assert data2["session_count"] == 1
            assert data2["sessions"]["alice"] == "email-world"

    @pytest.mark.asyncio
    async def test_bind_bad_manifest_returns_400(self, two_world_client):
        """Binding a session to a nonexistent manifest must return 400 (fail closed)."""
        async with two_world_client as c:
            resp = await c.post(
                "/mcp/sessions/s1/bind",
                json={"manifest_path": "/nonexistent/path/manifest.yaml"},
            )
            assert resp.status_code == 400
            assert resp.json()["status"] == "error"

    @pytest.mark.asyncio
    async def test_session_tool_call_enforced_against_session_world(self, two_world_client):  # noqa: E501
        """tools/call must be enforced against the session's bound manifest."""
        async with two_world_client as c:
            email_path = c._transport.app.state.email_manifest_path

            # Bind s1 to email world (only send_email)
            await c.post("/mcp/sessions/s1/bind", json={"manifest_path": email_path})

            # read_file is not in email world → must be denied for s1
            call_resp = await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                    "name": "read_file",
                    "arguments": {"path": "/tmp/x.txt"},
                    "_meta": {"session_id": "s1"},
                }},
            )
            data = call_resp.json()
            assert "error" in data, f"Expected denial for s1, got: {data}"
            assert data["error"]["code"] in (-32001, -32002)


# ---------------------------------------------------------------------------
# Group 8: SSE integration via real uvicorn server (Option E)
# ---------------------------------------------------------------------------

class TestSSEIntegration:
    """
    Full SSE streaming round-trip tests against a real uvicorn server.

    httpx ASGI transport buffers the entire HTTP response body before returning
    headers, making it impossible to test infinite SSE streams. These tests
    start a real uvicorn server in a daemon thread and use http.client +
    threading to read SSE events line-by-line, which is the only reliable way
    to test actual streaming behaviour.

    Protocol invariants tested:
    - GET /mcp/sse returns Content-Type: text/event-stream
    - The first SSE event is 'endpoint' with data=/mcp/messages?session_id=<uuid>
    - Full round-trip: open SSE → read endpoint → POST request → read message event
    - POST /mcp/messages after SSE disconnect returns 404 (session cleaned up)
    """

    HOST = "127.0.0.1"
    PORT = 18095

    # ------------------------------------------------------------------ #
    # Fixtures                                                             #
    # ------------------------------------------------------------------ #

    @pytest.fixture(scope="class")
    def live_server(self, tmp_path_factory):
        """
        Start a real uvicorn gateway and yield (host, port, base_url).

        Uses scope="class" so all tests in the group share one server instance
        (faster) rather than paying the startup cost per test.
        """
        import time
        import threading
        import http.client

        pytest.importorskip("uvicorn")
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        tmp_path = tmp_path_factory.mktemp("sse_integration")
        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: sse-integration-world\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file)

        import uvicorn
        config = uvicorn.Config(
            app, host=self.HOST, port=self.PORT, log_level="error"
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        # Poll the health endpoint until the server is ready (max 5 s).
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection(self.HOST, self.PORT, timeout=1)
                conn.request("GET", "/mcp/health")
                conn.getresponse().read()
                conn.close()
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("SSE integration server did not start within 5 s")

        yield (self.HOST, self.PORT, f"http://{self.HOST}:{self.PORT}")

        server.should_exit = True
        time.sleep(0.2)

    # ------------------------------------------------------------------ #
    # SSE helpers                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _collect_sse_events(
        host: str,
        port: int,
        path: str,
        n_events: int,
        timeout: float = 5.0,
    ) -> list[dict]:
        """
        Open an SSE connection and collect up to n_events parsed events.

        Returns a list of dicts with keys 'event' (str) and 'data' (str).
        Runs the blocking HTTP read in a daemon thread so the main test
        thread can time-out cleanly.
        """
        import http.client
        import threading
        import queue as queue_mod

        result_q: queue_mod.Queue = queue_mod.Queue()

        def _reader():
            try:
                conn = http.client.HTTPConnection(host, port, timeout=timeout)
                conn.request("GET", path, headers={"Accept": "text/event-stream"})
                resp = conn.getresponse()
                event_type = None
                event_data = None
                while True:
                    raw = resp.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        event_data = line[6:]
                    elif line.startswith(":"):
                        pass   # heartbeat comment — ignore
                    elif line == "" and event_type is not None:
                        result_q.put({"event": event_type, "data": event_data})
                        event_type = None
                        event_data = None
                conn.close()
            except Exception as exc:
                result_q.put({"_error": str(exc)})

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        events = []
        for _ in range(n_events):
            try:
                ev = result_q.get(timeout=timeout)
                if "_error" in ev:
                    raise RuntimeError(f"SSE reader error: {ev['_error']}")
                events.append(ev)
            except queue_mod.Empty:
                break
        return events

    @staticmethod
    def _post_json(host: str, port: int, path: str, body: dict) -> tuple[int, dict]:
        """Send a JSON POST to the live server; return (status_code, parsed_body)."""
        import http.client
        payload = json.dumps(body).encode()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST", path, body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        status = resp.status
        data = json.loads(resp.read())
        conn.close()
        return status, data

    # ------------------------------------------------------------------ #
    # Tests                                                                #
    # ------------------------------------------------------------------ #

    def test_sse_content_type(self, live_server):
        """GET /mcp/sse must return Content-Type: text/event-stream."""
        import http.client
        host, port, _ = live_server
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/mcp/sse", headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        content_type = resp.getheader("Content-Type", "")
        # Read a small chunk then abandon (we only need the headers here)
        resp.read(64)
        conn.close()
        assert "text/event-stream" in content_type, (
            f"Expected text/event-stream, got {content_type!r}"
        )

    def test_sse_first_event_is_endpoint(self, live_server):
        """The first SSE event must be 'endpoint' with a session URL."""
        host, port, _ = live_server
        events = self._collect_sse_events(host, port, "/mcp/sse", n_events=1)
        assert len(events) == 1, f"Expected 1 event, got {events}"
        ev = events[0]
        assert ev["event"] == "endpoint", f"Expected 'endpoint' event, got {ev}"
        assert "/mcp/messages?session_id=" in ev["data"], (
            f"Endpoint data does not contain session URL: {ev['data']}"
        )

    def test_sse_endpoint_url_has_uuid_session_id(self, live_server):
        """The endpoint event's session_id must look like a UUID."""
        import re
        host, port, _ = live_server
        events = self._collect_sse_events(host, port, "/mcp/sse", n_events=1)
        data = events[0]["data"]
        # data is "/mcp/messages?session_id=<uuid>"
        m = re.search(r"session_id=([0-9a-f-]{30,})", data)
        assert m is not None, f"No UUID-like session_id found in {data!r}"

    def test_sse_full_round_trip(self, live_server):
        """
        Full SSE round-trip:
        1. Open GET /mcp/sse → read endpoint event → extract session_id
        2. POST tools/list to /mcp/messages?session_id=<id>
        3. Read the resulting 'message' event from the SSE stream.

        The SSE reader runs in a daemon thread and forwards each event to a
        shared queue as soon as it arrives (not after collecting n_events).
        This avoids the deadlock where the reader waits for event 2 before
        the main thread can POST to trigger event 2.
        """
        import http.client
        import threading
        import queue as queue_mod

        host, port, _ = live_server
        event_q: queue_mod.Queue = queue_mod.Queue()

        def _streaming_reader():
            """Connect to SSE and push each parsed event into event_q immediately."""
            try:
                conn = http.client.HTTPConnection(host, port, timeout=10)
                conn.request("GET", "/mcp/sse", headers={"Accept": "text/event-stream"})
                resp = conn.getresponse()
                event_type = None
                event_data = None
                while True:
                    raw = resp.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        event_data = line[6:]
                    elif line.startswith(":"):
                        pass   # heartbeat comment
                    elif line == "" and event_type is not None:
                        # Emit event immediately — do not wait to batch
                        event_q.put({"event": event_type, "data": event_data})
                        event_type = None
                        event_data = None
                conn.close()
            except Exception as exc:
                event_q.put({"_error": str(exc)})

        t = threading.Thread(target=_streaming_reader, daemon=True)
        t.start()

        # Step 1: get the endpoint event (the server yields it immediately on connect)
        try:
            endpoint_event = event_q.get(timeout=5.0)
        except queue_mod.Empty:
            pytest.fail("Timed out waiting for SSE endpoint event")

        if "_error" in endpoint_event:
            pytest.fail(f"SSE reader error: {endpoint_event['_error']}")

        assert endpoint_event["event"] == "endpoint", (
            f"Expected 'endpoint' event, got {endpoint_event}"
        )
        messages_path = endpoint_event["data"]   # /mcp/messages?session_id=<uuid>

        # Step 2: POST a tools/list request via the SSE messages endpoint.
        # Now that the main thread has the session_id it can POST.
        status, post_body = self._post_json(
            host, port, messages_path,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert status == 202, f"Expected 202, got {status}: {post_body}"
        assert post_body.get("status") == "accepted"

        # Step 3: the JSON-RPC response arrives as a 'message' event on the stream.
        # The server puts the response in the session queue, sse_stream yields it.
        try:
            message_event = event_q.get(timeout=5.0)
        except queue_mod.Empty:
            pytest.fail("Timed out waiting for SSE message event after POST")

        if "_error" in message_event:
            pytest.fail(f"SSE reader error after POST: {message_event['_error']}")

        assert message_event["event"] == "message", (
            f"Expected 'message' event, got {message_event}"
        )
        result = json.loads(message_event["data"])
        assert "result" in result, f"Expected JSON-RPC result, got: {result}"
        assert "tools" in result["result"], f"tools/list result missing 'tools': {result}"
        tool_names = [t["name"] for t in result["result"]["tools"]]
        assert "read_file" in tool_names, f"read_file not in {tool_names}"

    def test_sse_session_removed_after_disconnect(self, live_server):
        """
        After the SSE connection closes, POST /mcp/messages must return 404.

        Simulate disconnect by opening the SSE stream, reading the endpoint
        event, closing the connection, then attempting to POST.
        """
        import http.client
        import time

        host, port, _ = live_server

        # Open SSE, read endpoint event, capture session_id, close abruptly.
        session_id = None
        conn = http.client.HTTPConnection(host, port, timeout=5)
        try:
            conn.request("GET", "/mcp/sse", headers={"Accept": "text/event-stream"})
            resp = conn.getresponse()
            event_type = None
            event_data = None
            while True:
                line = resp.readline().decode("utf-8").rstrip("\r\n")
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                elif line == "" and event_type is not None:
                    if event_type == "endpoint":
                        # /mcp/messages?session_id=<uuid>
                        session_id = event_data.split("session_id=")[-1]
                        break
        finally:
            conn.close()   # abrupt close — simulates client disconnect

        assert session_id, "Could not extract session_id from SSE stream"

        # Give the server a moment to run the finally block in sse_stream.
        time.sleep(0.3)

        # POST to the now-dead session must return 404.
        status, body = self._post_json(
            host, port, f"/mcp/messages?session_id={session_id}",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert status == 404, (
            f"Expected 404 after SSE disconnect, got {status}: {body}"
        )


# ---------------------------------------------------------------------------
# Group 7: SSE transport
# ---------------------------------------------------------------------------

class TestSSETransport:
    """
    Tests for the MCP SSE transport (GET /mcp/sse + POST /mcp/messages).

    Protocol invariants tested:
    - GET /mcp/sse returns text/event-stream with an 'endpoint' event
    - The endpoint event payload is /mcp/messages?session_id=<uuid>
    - POST /mcp/messages with a valid session_id returns 202 Accepted
    - The JSON-RPC response is delivered over the SSE stream as a 'message' event
    - POST /mcp/messages with an unknown session_id returns 404
    - SSESessionStore correctly tracks and cleans up sessions

    SSE streams are tested by opening the stream, posting a request from a
    concurrent task, then reading the response event from the stream.
    """

    @pytest.fixture
    def sse_client(self, tmp_path):
        """httpx AsyncClient for a gateway with the default read_file world."""
        pytest.importorskip("httpx")
        from httpx import AsyncClient, ASGITransport
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: sse-test-world\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    # --- SSESessionStore unit tests ---

    def test_create_session_returns_uuid_and_queue(self):
        """create_session must return a non-empty UUID and a Queue."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        import asyncio
        store = SSESessionStore()
        session_id, queue = store.create_session()
        assert session_id and len(session_id) > 8
        assert isinstance(queue, asyncio.Queue)

    def test_get_queue_returns_same_queue(self):
        """get_queue must return the same Queue that was created."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        store = SSESessionStore()
        session_id, queue = store.create_session()
        assert store.get_queue(session_id) is queue

    def test_get_queue_unknown_session_returns_none(self):
        """get_queue for an unknown session_id must return None."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        store = SSESessionStore()
        assert store.get_queue("does-not-exist") is None

    def test_remove_session_cleans_up(self):
        """remove_session must remove the session; subsequent get_queue returns None."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        store = SSESessionStore()
        session_id, _ = store.create_session()
        assert store.session_count() == 1
        store.remove_session(session_id)
        assert store.session_count() == 0
        assert store.get_queue(session_id) is None

    def test_remove_nonexistent_session_is_idempotent(self):
        """remove_session on an unknown session_id must not raise."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        store = SSESessionStore()
        store.remove_session("ghost")  # must not raise

    def test_multiple_sessions_are_independent(self):
        """Multiple concurrent sessions must have independent queues."""
        from agent_hypervisor.hypervisor.mcp_gateway import SSESessionStore
        store = SSESessionStore()
        id1, q1 = store.create_session()
        id2, q2 = store.create_session()
        assert id1 != id2
        assert q1 is not q2
        assert store.session_count() == 2

    # --- sse_stream generator unit tests ---

    @pytest.mark.asyncio
    async def test_sse_stream_first_event_is_endpoint(self):
        """sse_stream must yield an 'endpoint' event as the first chunk."""
        from agent_hypervisor.hypervisor.mcp_gateway.sse_transport import (
            SSESessionStore, sse_stream,
        )
        import asyncio

        store = SSESessionStore()
        session_id, queue = store.create_session()
        endpoint_url = f"/mcp/messages?session_id={session_id}"

        gen = sse_stream(session_id, queue, endpoint_url, store)
        first_chunk = await gen.__anext__()

        assert "event: endpoint" in first_chunk
        assert endpoint_url in first_chunk

        # Sentinel to stop the generator cleanly
        await queue.put(None)
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_sse_stream_delivers_message_events(self):
        """sse_stream must yield 'message' events for payloads placed in the queue."""
        from agent_hypervisor.hypervisor.mcp_gateway.sse_transport import (
            SSESessionStore, sse_stream,
        )
        import asyncio

        store = SSESessionStore()
        session_id, queue = store.create_session()
        gen = sse_stream(session_id, queue, "/ep", store)

        # Consume endpoint event
        await gen.__anext__()

        # Put a payload in the queue
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        await queue.put(payload)
        message_chunk = await gen.__anext__()

        assert "event: message" in message_chunk
        assert payload in message_chunk

        await queue.put(None)
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_sse_stream_cleanup_on_sentinel(self):
        """sse_stream must remove the session from the store when sentinel is received."""
        from agent_hypervisor.hypervisor.mcp_gateway.sse_transport import (
            SSESessionStore, sse_stream,
        )
        import asyncio

        store = SSESessionStore()
        session_id, queue = store.create_session()
        gen = sse_stream(session_id, queue, "/ep", store)

        await gen.__anext__()  # endpoint event
        assert store.get_queue(session_id) is not None

        await queue.put(None)  # sentinel
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

        assert store.get_queue(session_id) is None

    # --- HTTP endpoint tests ---

    def test_sse_endpoints_registered_and_store_initialized(self, tmp_path):
        """
        GET /mcp/sse and POST /mcp/messages must be registered as routes.
        The app must initialize an SSESessionStore on app.state.sse_store.

        Note: httpx ASGI transport collects the entire response body before
        returning headers, making it unsuitable for testing infinite SSE streams.
        The actual streaming format is covered by the sse_stream generator tests.
        """
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: sse-route-test\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file)

        route_paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/mcp/sse" in route_paths, f"Missing /mcp/sse in routes: {route_paths}"
        assert "/mcp/messages" in route_paths, \
            f"Missing /mcp/messages in routes: {route_paths}"

        assert hasattr(app.state, "sse_store"), "app.state.sse_store not initialized"
        assert app.state.sse_store.session_count() == 0

    @pytest.mark.asyncio
    async def test_sse_messages_unknown_session_returns_404(self, sse_client):
        """POST /mcp/messages with an unknown session_id must return 404."""
        async with sse_client as c:
            resp = await c.post(
                "/mcp/messages?session_id=nonexistent",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sse_full_round_trip_via_queue(self, sse_client):
        """
        Full SSE round-trip via direct queue inspection.

        Directly registers a session in the SSE store (simulating GET /mcp/sse)
        and posts a request to POST /mcp/messages. Verifies that the response
        is placed in the session queue — i.e., it would have been delivered
        over the SSE stream.

        This tests the dispatch+routing logic without needing to stream SSE
        events (which requires a real HTTP server for clean async semantics).
        """
        from httpx import AsyncClient, ASGITransport
        import asyncio

        app = sse_client._transport.app  # type: ignore[attr-defined]
        store = app.state.sse_store

        # Simulate GET /mcp/sse: register a session in the store
        session_id, queue = store.create_session()
        try:
            c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

            # POST the initialize request via SSE messages endpoint
            post_resp = await c.post(
                f"/mcp/messages?session_id={session_id}",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            await c.aclose()

            assert post_resp.status_code == 202
            assert post_resp.json()["status"] == "accepted"

            # Response must be in the queue (would have gone to SSE stream)
            assert not queue.empty(), "Response was not placed in SSE queue"
            payload = queue.get_nowait()
            data = json.loads(payload)
            assert "result" in data, f"Expected result, got: {data}"
            assert "capabilities" in data["result"]
            assert "serverInfo" in data["result"]
        finally:
            store.remove_session(session_id)

    @pytest.mark.asyncio
    async def test_sse_tool_denial_delivered_to_queue(self, sse_client):
        """
        tools/call to an undeclared tool must route a JSON-RPC error to the
        SSE queue — i.e., it would have been delivered over the SSE stream.

        HTTP response must be 202 Accepted (the denial is in the SSE stream).
        """
        from httpx import AsyncClient, ASGITransport

        app = sse_client._transport.app  # type: ignore[attr-defined]
        store = app.state.sse_store

        session_id, queue = store.create_session()
        try:
            c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

            post_resp = await c.post(
                f"/mcp/messages?session_id={session_id}",
                json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "http_post", "arguments": {"url": "http://x"}},
                },
            )
            await c.aclose()

            # HTTP level: always 202 for SSE transport (denial goes over stream)
            assert post_resp.status_code == 202

            assert not queue.empty(), "No response in SSE queue"
            payload = queue.get_nowait()
            data = json.loads(payload)
            assert "error" in data, f"Expected error in SSE queue payload, got: {data}"
            assert data["error"]["code"] in (-32001, -32002)
        finally:
            store.remove_session(session_id)
