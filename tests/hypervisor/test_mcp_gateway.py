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
