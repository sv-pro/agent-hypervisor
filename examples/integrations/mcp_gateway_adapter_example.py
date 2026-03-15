"""
mcp_gateway_adapter_example.py — MCP-facing gateway adapter shim.

Implements a minimal subset of the Model Context Protocol (MCP) over HTTP
and proxies tool execution through the Agent Hypervisor gateway.

Architecture
------------

    MCP client (Claude Desktop / Cursor / any MCP host)
         │
         │  JSON-RPC 2.0 over HTTP  (port 9090)
         ▼
    ┌──────────────────────────────────────┐
    │        MCP Gateway Adapter           │
    │                                      │
    │  • tools/list  → gateway /tools/list │
    │  • tools/call  → gateway /execute    │
    │                                      │
    │  All args tagged "user_declared"     │
    │  (from an authorised agent host)     │
    └──────────────────────────────────────┘
         │
         │  HTTP  (port 8080)
         ▼
    Agent Hypervisor Gateway
    (provenance + policy enforcement)

MCP protocol subset implemented
--------------------------------

    initialize    — required handshake (server declares capabilities)
    tools/list    — proxy to gateway, return MCP-formatted tool schemas
    tools/call    — proxy to gateway, return MCP-formatted result

Provenance mapping
------------------

Arguments arriving through MCP are tagged ``user_declared`` because they
come from an authorised agent host, not from an untrusted external document.
This is the correct provenance class for an agent acting on user intent.

The gateway still enforces the full policy + firewall, so:
  • deny  → MCP ``isError: true`` with the block reason
  • ask   → MCP ``isError: false`` with an ``approval_required`` note
  • allow → MCP ``isError: false`` with the tool result

Usage
-----

    # Terminal 1 — start the gateway
    python scripts/run_gateway.py

    # Terminal 2 — start this MCP adapter shim
    python examples/integrations/mcp_gateway_adapter_example.py

    # Terminal 3 — run the built-in demo
    python examples/integrations/mcp_gateway_adapter_example.py --demo

No external dependencies.  Uses urllib.request and http.server from stdlib.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GATEWAY_URL = "http://127.0.0.1:8080"
MCP_HOST = "127.0.0.1"
MCP_PORT = 9090

# MCP server metadata
SERVER_INFO = {
    "name": "agent-hypervisor-mcp-adapter",
    "version": "0.1.0",
}

# Capabilities we advertise to MCP clients
SERVER_CAPABILITIES = {
    "tools": {},
}


# ---------------------------------------------------------------------------
# Gateway HTTP helpers (stdlib, no requests/httpx)
# ---------------------------------------------------------------------------

def _gateway_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make one HTTP request to the gateway."""
    url = GATEWAY_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())
        except Exception:
            detail = {"detail": str(exc)}
        return {"_http_error": exc.code, **detail}


# ---------------------------------------------------------------------------
# MCP protocol helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _text_content(text: str) -> dict:
    return {"type": "text", "text": text}


# ---------------------------------------------------------------------------
# MCP method handlers
# ---------------------------------------------------------------------------

def handle_initialize(params: dict) -> dict:
    """MCP initialize handshake."""
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": SERVER_INFO,
        "capabilities": SERVER_CAPABILITIES,
    }


def handle_tools_list() -> dict:
    """Return tools registered in the gateway as MCP tool schemas."""
    resp = _gateway_request("POST", "/tools/list")
    tools = resp.get("tools", [])

    mcp_tools = []
    for t in tools:
        mcp_tools.append({
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "inputSchema": {
                "type": "object",
                "properties": {
                    # Generic schema: each argument is a string value.
                    # Real adapters would expose per-tool schemas.
                    "args": {
                        "type": "object",
                        "description": "Tool arguments (key: value pairs)",
                    },
                },
            },
        })

    return {"tools": mcp_tools}


def handle_tools_call(params: dict) -> dict:
    """
    Execute a tool via the gateway and return an MCP-formatted result.

    All arguments from the MCP client are tagged "user_declared" because
    they originate from an authorised agent host, not an external document.

    Verdict mapping:
      allow → isError: false,  content with result
      deny  → isError: true,   content with block reason
      ask   → isError: false,  content with approval_required notice
    """
    tool_name = params.get("name", "")
    raw_args: dict = params.get("arguments", {})

    # Tag every argument as user_declared provenance
    gateway_args = {
        k: {"value": v, "source": "user_declared"}
        for k, v in raw_args.items()
    }

    resp = _gateway_request("POST", "/tools/execute", {
        "tool": tool_name,
        "arguments": gateway_args,
        "call_id": f"mcp-{tool_name}",
    })

    verdict = resp.get("verdict", "deny")

    if verdict == "allow":
        result_text = json.dumps(resp.get("result"), indent=2) if resp.get("result") else "(no output)"
        return {
            "content": [_text_content(result_text)],
            "isError": False,
        }

    if verdict == "deny":
        reason = resp.get("reason", "Blocked by gateway policy")
        return {
            "content": [_text_content(f"[BLOCKED] {reason}")],
            "isError": True,
        }

    # verdict == "ask"
    approval_id = resp.get("approval_id", "unknown")
    reason = resp.get("reason", "Approval required")
    return {
        "content": [_text_content(
            f"[APPROVAL REQUIRED] {reason}\n"
            f"approval_id: {approval_id}\n"
            f"To approve:  POST {GATEWAY_URL}/approvals/{approval_id}  "
            f'body: {{"approved": true, "actor": "reviewer"}}\n'
            f"To reject:   same URL with approved: false"
        )],
        "isError": False,
        "_approval_id": approval_id,
        "_approval_required": True,
    }


# ---------------------------------------------------------------------------
# HTTP request handler (MCP over HTTP)
# ---------------------------------------------------------------------------

class MCPHandler(BaseHTTPRequestHandler):
    """
    Minimal MCP JSON-RPC 2.0 handler over HTTP POST.

    MCP over HTTP sends all JSON-RPC requests as POST to the root path.
    """

    def log_message(self, fmt, *args):  # suppress default access log
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length else b"{}"

        try:
            rpc = json.loads(body_bytes)
        except json.JSONDecodeError:
            self._send(400, _error(None, -32700, "Parse error"))
            return

        req_id = rpc.get("id")
        method = rpc.get("method", "")
        params = rpc.get("params", {})

        try:
            if method == "initialize":
                result = handle_initialize(params)
            elif method == "tools/list":
                result = handle_tools_list()
            elif method == "tools/call":
                result = handle_tools_call(params)
            elif method == "notifications/initialized":
                # MCP clients send this notification after initialize; no response needed.
                self._send(204, b"")
                return
            else:
                self._send(200, _error(req_id, -32601, f"Method not found: {method!r}"))
                return
        except Exception as exc:
            self._send(200, _error(req_id, -32603, f"Internal error: {exc}"))
            return

        self._send(200, _ok(req_id, result))

    def _send(self, code: int, payload):
        if isinstance(payload, dict):
            body = json.dumps(payload).encode()
            content_type = "application/json"
        elif isinstance(payload, bytes):
            body = payload
            content_type = "text/plain"
        else:
            body = str(payload).encode()
            content_type = "text/plain"

        self.send_response(code)
        if body:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


# ---------------------------------------------------------------------------
# Demo: exercise the adapter without a real MCP client
# ---------------------------------------------------------------------------

def run_demo():
    """
    Start the adapter shim and run a short demonstration against it.

    The demo starts the shim in a background thread and sends three
    JSON-RPC requests directly to verify the MCP ↔ gateway translation.
    """
    # Start shim in background
    server = HTTPServer((MCP_HOST, MCP_PORT), MCPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    base = f"http://{MCP_HOST}:{MCP_PORT}"

    def rpc(req_id, method, params=None):
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        req = urllib.request.Request(
            base,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    print("=" * 60)
    print("MCP Gateway Adapter — Demo")
    print("=" * 60)

    # 1. initialize
    print("\n[1] initialize (MCP handshake)")
    r = rpc(1, "initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "demo"}})
    print(f"    server: {r['result']['serverInfo']['name']} v{r['result']['serverInfo']['version']}")
    print(f"    capabilities: {list(r['result']['capabilities'].keys())}")

    # 2. tools/list
    print("\n[2] tools/list")
    r = rpc(2, "tools/list")
    tools = r["result"]["tools"]
    for t in tools:
        print(f"    • {t['name']}: {t['description'][:60]}")

    # 3. tools/call — read_file (always allowed)
    print("\n[3] tools/call — read_file (allowed)")
    r = rpc(3, "tools/call", {"name": "read_file", "arguments": {"path": "/etc/hostname"}})
    result = r["result"]
    print(f"    isError:  {result['isError']}")
    print(f"    content:  {result['content'][0]['text'][:80]}")

    # 4. tools/call — send_email with user_declared recipient (ask expected)
    print("\n[4] tools/call — send_email with user_declared recipient (expect: ask)")
    r = rpc(4, "tools/call", {
        "name": "send_email",
        "arguments": {"to": "alice@example.com", "subject": "Report", "body": "See attached."},
    })
    result = r["result"]
    print(f"    isError:             {result['isError']}")
    print(f"    approval_required:   {result.get('_approval_required', False)}")
    approval_id = result.get("_approval_id")
    if approval_id:
        print(f"    approval_id:         {approval_id}")
        print(f"    content preview:     {result['content'][0]['text'][:120]}")

    print("\n" + "=" * 60)
    print("Demo complete.  Gateway enforcement applied to all MCP calls.")
    print("=" * 60)
    server.shutdown()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Must declare before any use within this function
    global GATEWAY_URL, MCP_PORT  # noqa: PLW0603

    parser = argparse.ArgumentParser(description="MCP gateway adapter shim")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a built-in demonstration instead of starting the server",
    )
    parser.add_argument(
        "--gateway",
        default=None,
        help=f"Gateway base URL (default: {GATEWAY_URL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"MCP adapter listen port (default: {MCP_PORT})",
    )
    args = parser.parse_args()

    if args.gateway:
        GATEWAY_URL = args.gateway
    if args.port:
        MCP_PORT = args.port

    if args.demo:
        # Verify gateway is reachable first
        try:
            _gateway_request("GET", "/")
        except Exception as exc:
            print(f"Gateway not reachable at {GATEWAY_URL}: {exc}", file=sys.stderr)
            print("Start it with:  python scripts/run_gateway.py", file=sys.stderr)
            sys.exit(1)
        run_demo()
        return

    print(f"MCP gateway adapter listening on http://{MCP_HOST}:{MCP_PORT}")
    print(f"Proxying to gateway at {GATEWAY_URL}")
    print("Press Ctrl-C to stop.\n")
    server = HTTPServer((MCP_HOST, MCP_PORT), MCPHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
