"""Tests for integrations/mcp/server.py."""

from safe_agent_runtime_pro.integrations.mcp.server import ProxyMCPServer


class _StubProxy:
    def __init__(self):
        self.calls: list = []

    def handle(self, tool, params, *, source, taint):
        self.calls.append({"tool": tool, "params": params, "source": source, "taint": taint})
        return {"answer": f"result-{tool}"}


def _make_server() -> tuple[ProxyMCPServer, _StubProxy]:
    """Build a ProxyMCPServer with an injected stub proxy."""
    stub = _StubProxy()
    server = ProxyMCPServer.__new__(ProxyMCPServer)
    server._proxy = stub
    return server, stub


def test_handle_routes_through_proxy():
    server, stub = _make_server()
    result = server.handle("read_data", {"key": "v"})
    assert stub.calls[0]["tool"] == "read_data"
    assert result == {"answer": "result-read_data"}


def test_handle_passes_taint():
    server, stub = _make_server()
    server.handle("summarize", {}, taint=True)
    assert stub.calls[0]["taint"] is True


def test_handle_uses_mcp_source():
    server, stub = _make_server()
    server.handle("read_data", {})
    assert stub.calls[0]["source"] == "mcp"
