# MCP Integration Guide

Agent Hypervisor can sit between any MCP-compatible agent runtime and tool
execution. This page explains how to run the gateway, how to route MCP tool
calls through it, and how approvals and traces work in the MCP flow.

---

## Architecture

```
Agent (MCP client: Claude Desktop, Cursor, custom runtime)
  │
  │  JSON-RPC 2.0 over HTTP  (port 9090)
  ▼
MCP Adapter  (examples/integrations/mcp_gateway_full_example.py)
  │
  │  POST /tools/execute  {tool, arguments with provenance labels}
  ▼
Agent Hypervisor Gateway  (port 8080)
  │
  ├── Provenance-Aware Policy enforcement
  ├── Approval Workflow
  └── Trace Audit
  │
  ▼
Tool Execution (send_email, read_file, http_post, ...)
```

The MCP adapter is a thin shim that:

1. Implements the MCP protocol (`initialize`, `tools/list`, `tools/call`)
2. Translates MCP tool calls to gateway requests with provenance labels
3. Maps gateway verdicts (`allow` / `deny` / `ask`) back to MCP responses

---

## Quickstart

### Step 1 — Start the gateway

```bash
python scripts/run_gateway.py
```

The gateway starts on `http://127.0.0.1:8080` by default.
Configuration is in `gateway_config.yaml`.

### Step 2 — Start the MCP adapter

```bash
python examples/integrations/mcp_gateway_full_example.py
```

The adapter starts on `http://127.0.0.1:9090` by default.
It proxies all MCP tool calls to the gateway.

### Step 3 — Run the built-in demo

```bash
python examples/integrations/mcp_gateway_full_example.py --demo
```

This runs the canonical governance scenario:

```
external_document
  → agent proposes send_email
  → MCP adapter → gateway → provenance check
  → verdict = ask
  → approval granted
  → tool executed
  → trace stored
```

---

## Routing Tool Calls Through the Gateway

Any MCP-compatible client can connect to the adapter. The adapter handles
three MCP methods:

| MCP method              | Gateway endpoint       | What happens                         |
|-------------------------|------------------------|--------------------------------------|
| `initialize`            | (local)                | MCP handshake, declare capabilities  |
| `tools/list`            | `POST /tools/list`     | Return gateway-registered tools      |
| `tools/call`            | `POST /tools/execute`  | Execute with provenance enforcement  |

### tools/call — Provenance Mapping

When the MCP client calls `tools/call`, the adapter maps each argument to a
provenance class before forwarding to the gateway:

```
Argument key pattern       → Provenance class
─────────────────────────────────────────────
key ends in "_external"    → external_document
all other keys             → user_declared
```

This mapping reflects the security boundary at the MCP adapter:

- Arguments arriving from an authorized agent host are `user_declared`
  (the agent is acting on user intent, not on untrusted document content)
- Arguments explicitly flagged as coming from external sources are
  `external_document` (untrusted content from files, web pages, emails)

The gateway then applies provenance-aware policy to the labeled arguments.

### Example: declaring external content

```python
# MCP client sends:
{
    "name": "send_email",
    "arguments": {
        "to_external": "address-from-document@example.com",  # ← external
        "subject": "Report",                                  # ← user_declared
        "body": "See attached.",                              # ← user_declared
    }
}

# Adapter maps to gateway request:
{
    "tool": "send_email",
    "arguments": {
        "to":      {"value": "address-from-document@example.com",
                    "source": "external_document"},
        "subject": {"value": "Report", "source": "user_declared"},
        "body":    {"value": "See attached.", "source": "user_declared"},
    }
}

# Gateway verdict: deny
# reason: recipient traces to external_document (deny-email-external-recipient)
```

---

## Verdicts and MCP Responses

The gateway returns one of three verdicts. The adapter translates each to an
MCP `tools/call` response:

### allow

Tool executed successfully.

```json
{
    "content": [{"type": "text", "text": "<tool result>"}],
    "isError": false
}
```

### deny

Tool blocked by policy.

```json
{
    "content": [{"type": "text", "text": "[BLOCKED BY AGENT HYPERVISOR]\nreason: ..."}],
    "isError": true
}
```

The MCP client sees `isError: true`. The block is permanent for this call.
A trace entry is written to the audit log.

### ask

Tool held for human approval.

```json
{
    "content": [{"type": "text", "text": "[APPROVAL REQUIRED — AGENT HYPERVISOR]\napproval_id: ..."}],
    "isError": false,
    "_approval_id": "...",
    "_approval_required": true
}
```

The tool has not executed. The agent or an external reviewer must approve
or reject via the gateway's approval API.

---

## Approval Workflow

When the verdict is `ask`, a pending approval record is created in the
gateway and the `approval_id` is returned.

### Inspect the pending request

```bash
curl http://localhost:8080/approvals/<approval_id>
```

The response shows the full tool call: tool name, all arguments and their
provenance labels, and the policy rule that triggered the ask verdict.

### Approve or reject

```bash
# Approve
curl -X POST http://localhost:8080/approvals/<approval_id> \
     -H "Content-Type: application/json" \
     -d '{"approved": true, "actor": "reviewer-name"}'

# Reject
curl -X POST http://localhost:8080/approvals/<approval_id> \
     -H "Content-Type: application/json" \
     -d '{"approved": false, "actor": "reviewer-name"}'
```

After approval, the tool executes and the result is returned. After
rejection, the call is permanently blocked. Both outcomes produce a trace
entry that includes the reviewer's identity and the original verdict.

Pending approvals survive gateway restarts — they are persisted to the
`storage.path/approvals/` directory.

---

## Traces and Audit

Every tool call — regardless of verdict — produces a trace entry in the
gateway's trace log.

```bash
# View recent traces
curl http://localhost:8080/traces

# View all approval records
curl http://localhost:8080/approvals

# View policy version history
curl http://localhost:8080/policy/history
```

Each trace entry includes:

| Field            | Description                                               |
|------------------|-----------------------------------------------------------|
| `trace_id`       | Unique identifier for this execution attempt              |
| `tool`           | Tool name                                                 |
| `final_verdict`  | `allow`, `deny`, or `ask`                                 |
| `matched_rule`   | Policy rule that produced the verdict                     |
| `policy_version` | Policy version active at decision time                    |
| `approved_by`    | Reviewer identity (for approved `ask` verdicts)           |
| `original_verdict` | `ask` (if the final allow came after approval)          |
| `timestamp`      | ISO 8601 timestamp                                        |

Traces are written to `storage.path/traces.jsonl` (append-only JSONL).
They survive gateway restarts and are never modified after writing.

---

## Configuration

### Gateway configuration (`gateway_config.yaml`)

```yaml
tools:
  - send_email
  - read_file
  - http_post

policy_file: policies/default_policy.yaml

server:
  host: "127.0.0.1"
  port: 8080

storage:
  backend: jsonl
  path: .data
```

### Policy example (`policies/default_policy.yaml`)

```yaml
rules:
  # Read-only tools: always allowed
  - id: allow-read-file
    tool: read_file
    verdict: allow

  # External document recipient → deny outbound email
  - id: deny-email-external-recipient
    tool: send_email
    argument: to
    provenance: external_document
    verdict: deny

  # Declared recipient → ask for human confirmation
  - id: ask-email-declared-recipient
    tool: send_email
    argument: to
    provenance: user_declared
    verdict: ask
```

Policy is hot-reloadable without restarting the gateway:

```bash
curl -X POST http://localhost:8080/policy/reload
```

Each reload creates a new policy version entry in the history log.
All trace entries link to the policy version that produced them.

---

## Command-Line Reference

```bash
# Start gateway
python scripts/run_gateway.py

# Start MCP adapter (gateway must be running)
python examples/integrations/mcp_gateway_full_example.py

# Custom gateway URL and adapter port
python examples/integrations/mcp_gateway_full_example.py \
    --gateway http://my-gateway:8080 \
    --port 9091

# Run canonical demo
python examples/integrations/mcp_gateway_full_example.py --demo

# Full showcase demo (includes MCP scenario)
python scripts/run_showcase_demo.py

# Policy tuner report (analyze trace data)
python scripts/run_policy_tuner.py
```

---

## Further Reading

- [execution_governance.md](execution_governance.md) — architecture, canonical scenario, threat model
- [gateway_architecture.md](gateway_architecture.md) — full HTTP API and enforcement pipeline
- [policy_engine.md](policy_engine.md) — declarative policy rule evaluation
- [provenance_model.md](provenance_model.md) — ValueRef, derivation chains
- [audit_model.md](audit_model.md) — trace / approval / policy version schema
- [policy_tuner.md](policy_tuner.md) — governance-time analysis and suggestions
