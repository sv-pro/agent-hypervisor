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
    async def test_session_tool_call_enforced_against_session_world(self, two_world_client):
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
