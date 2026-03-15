# Integrations

This document explains how external agent and tool stacks can connect to
the Agent Hypervisor gateway, and how the approval workflow operates.

---

## How External Stacks Call the Gateway

The gateway is a plain HTTP server. Any agent framework — LangChain, LangGraph,
AutoGen, or a hand-written tool loop — can call it by sending a JSON POST to
`/tools/execute`.

The only requirement is that each argument carries a provenance label
(`source` field). The gateway uses this to enforce policy and decide whether
to execute, block, or require approval.

### GatewayClient (Python)

The `GatewayClient` in `src/agent_hypervisor/gateway_client.py` wraps the
HTTP API with a simple Python interface:

```python
from agent_hypervisor.gateway_client import GatewayClient, arg

client = GatewayClient("http://localhost:8080")

# Execute a tool
response = client.execute_tool(
    tool="send_email",
    arguments={
        "to":      arg("alice@company.com", "user_declared", role="recipient_source"),
        "subject": arg("Q3 Report",          "system"),
        "body":    arg("See attached.",       "system"),
    },
)
print(response["verdict"])  # "allow" | "deny" | "ask"
```

The `arg()` helper builds the `ArgSpec` dict:

```python
arg(value, source, *, parents=None, role=None, label="")
```

| `source`              | Meaning                                              |
|-----------------------|------------------------------------------------------|
| `"external_document"` | Content from a file, email, or web page — untrusted |
| `"derived"`           | Computed or extracted from parent values             |
| `"user_declared"`     | Declared by the operator in the task manifest        |
| `"system"`            | Hardcoded by the system — always trusted             |

### Wrapped Tool Pattern

```python
guarded_send = client.wrap_tool("send_email")

response = guarded_send(
    to=arg("alice@company.com", "user_declared"),
    subject=arg("Report", "system"),
    body=arg("See attached.", "system"),
)
```

`wrap_tool()` returns a callable that routes calls through the gateway.
The returned callable accepts keyword arguments (each an `arg()` dict) and
returns the same response dict as `execute_tool()`.

### LangChain-style Decorator

For frameworks that use decorated functions as tools:

```python
from agent_hypervisor.gateway_client import GatewayClient, arg

client = GatewayClient("http://localhost:8080")

def gateway_tool(client, tool_name):
    def decorator(fn):
        def wrapper(**kwargs):
            arguments = {k: v if isinstance(v, dict) and "source" in v
                         else arg(v, "system")
                         for k, v in kwargs.items()}
            response = client.execute_tool(tool_name, arguments)
            if response["verdict"] == "allow":
                return response.get("result")
            elif response["verdict"] == "deny":
                return f"[BLOCKED] {response['reason']}"
            else:  # ask
                return {"approval_required": True,
                        "approval_id": response["approval_id"]}
        wrapper.__name__ = tool_name
        return wrapper
    return decorator

@gateway_tool(client, "send_email")
def send_email(to, subject, body):
    pass  # gateway adapter handles execution
```

See `examples/integrations/langchain_gateway_example.py` for a full working demo.

---

## How Allow / Deny / Ask Behaves

Every tool call produces one of three verdicts:

| Verdict | HTTP Status | Meaning                                                |
|---------|-------------|--------------------------------------------------------|
| `allow` | 200         | Policy passed. Tool executed. Result in response.      |
| `deny`  | 403         | Blocked by policy or provenance rule. Not executed.    |
| `ask`   | 200         | Approval required. `approval_id` returned. Not yet executed. |

### Allow

```json
{
  "verdict": "allow",
  "reason": "Tool 'read_file' is read-only and granted",
  "matched_rule": "allow-read-file",
  "policy_version": "a3f9c1b2",
  "trace_id": "7e4d1a9f",
  "result": {"path": "report.txt", "content": "..."},
  "approval_id": null,
  "approval_required": false
}
```

### Deny

```json
{
  "verdict": "deny",
  "reason": "Recipient provenance traces to external_document — external documents cannot authorize outbound email",
  "matched_rule": "deny-email-external-recipient",
  "policy_version": "a3f9c1b2",
  "trace_id": "8b2c4f10",
  "result": null,
  "approval_id": null,
  "approval_required": false
}
```

### Ask

```json
{
  "verdict": "ask",
  "reason": "Recipient 'alice@company.com' traces to declared source 'gateway_trusted' — confirmation required before sending",
  "matched_rule": "firewall:ask",
  "policy_version": "a3f9c1b2",
  "trace_id": "9c3d5f21",
  "result": null,
  "approval_id": "ab3f9c1d",
  "approval_required": true
}
```

---

## Approval Workflow

When the gateway returns `verdict: "ask"`, the tool has not been executed.
The request is stored in memory as a pending `ApprovalRecord`.

### Step 1 — Receive the ask response

```python
response = client.execute_tool("send_email", {...})
if response["verdict"] == "ask":
    approval_id = response["approval_id"]
    print(f"Approval required: {approval_id}")
```

### Step 2 — Inspect the pending approval

```python
record = client.get_approval(approval_id)
print(f"Tool: {record['tool']}")
print(f"Reason: {record['reason']}")
print(f"Arg provenance: {record['arg_provenance']}")
```

### Step 3 — List all pending approvals

```python
pending = client.get_approvals(status="pending")
for p in pending:
    print(f"[{p['approval_id']}] {p['tool']} — {p['reason']}")
```

### Step 4 — Approve (execute) or Reject

```python
# Approve — gateway executes the stored request
result = client.submit_approval(approval_id, approved=True, actor="alice-reviewer")
print(result["verdict"])  # "allow"
print(result["result"])   # tool output

# Reject — request is denied
result = client.submit_approval(approval_id, approved=False, actor="security-team")
print(result["verdict"])  # "deny"
```

### HTTP API for approvals

```
GET  /approvals               — list approvals (filter: ?status=pending)
GET  /approvals/{approval_id} — fetch one approval record
POST /approvals/{approval_id} — approve or reject

POST body:
  { "approved": true, "actor": "alice-reviewer" }
```

### Approval status lifecycle

```
pending → approved → executed   (happy path)
pending → rejected              (reviewer declines)
```

A resolved approval cannot be re-resolved (returns 409 Conflict).

### Trace entries for approvals

Each approval lifecycle event produces a trace entry:

1. **Original ask** — trace_id=X, final_verdict=ask, approval_id=Y, approval_status=pending
2. **After resolution** — new trace_id, original_verdict=ask, final_verdict=allow/deny,
   approved_by=actor, approval_id=Y, approval_status=executed/rejected

```json
{
  "trace_id": "9c3d5f21",
  "tool": "send_email",
  "final_verdict": "ask",
  "approval_id": "ab3f9c1d",
  "approval_status": "pending",
  "original_verdict": null
}
{
  "trace_id": "2d7a8e14",
  "tool": "send_email",
  "final_verdict": "allow",
  "approval_id": "ab3f9c1d",
  "approval_status": "executed",
  "approved_by": "alice-reviewer",
  "original_verdict": "ask"
}
```

---

## Running the Examples

```bash
# Start the gateway
python scripts/run_gateway.py

# Framework-agnostic integration demo (allow / deny / ask)
python examples/integrations/langchain_gateway_example.py

# Approval workflow demo (approve and reject flows)
python examples/integrations/approval_flow_example.py
```

Both examples start the gateway in a background thread automatically if
no running instance is found on the configured port.

---

## Raw HTTP (curl)

```bash
# Execute a tool
curl -s -X POST http://127.0.0.1:8080/tools/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "tool": "send_email",
    "arguments": {
      "to":      {"value": "alice@company.com", "source": "user_declared"},
      "subject": {"value": "Report", "source": "system"},
      "body":    {"value": "See attached.", "source": "system"}
    }
  }' | python -m json.tool

# Approve a pending request
curl -s -X POST http://127.0.0.1:8080/approvals/ab3f9c1d \
  -H 'Content-Type: application/json' \
  -d '{"approved": true, "actor": "alice-reviewer"}' | python -m json.tool

# List pending approvals
curl -s 'http://127.0.0.1:8080/approvals?status=pending' | python -m json.tool

# View traces
curl -s http://127.0.0.1:8080/traces | python -m json.tool

# Reload policy
curl -s -X POST http://127.0.0.1:8080/policy/reload | python -m json.tool
```
