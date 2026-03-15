# Gateway Architecture

The Agent Hypervisor Tool Gateway is an **execution governance layer**
that sits between an AI agent runtime and the external systems the agent
can affect.  Every tool call is evaluated against provenance policy before
execution.  Nothing executes without passing the enforcement pipeline.

```
  Agent Runtime  (LLM + tool loop)
       │
       │  POST /tools/execute
       │  {tool, arguments: {arg: {value, source, parents, role}}}
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │           Agent Hypervisor Gateway                      │
  │                                                         │
  │  ┌─────────────────────────────────────────────────┐   │
  │  │  Enforcement Pipeline                           │   │
  │  │                                                 │   │
  │  │  1. Build ValueRef graph from ArgSpec inputs    │   │
  │  │  2. PolicyEngine.evaluate()      ──► verdict    │◄──┤── YAML rules
  │  │  3. ProvenanceFirewall.check()   ──► verdict    │◄──┤── structural rules
  │  │  4. Combine: deny > ask > allow                 │   │
  │  │  5. Write TraceEntry + policy_version link      │───┤──► TraceStore
  │  └──────────────────┬──────────────────────────────┘   │
  │                     │                                   │
  │         ┌───────────┼──────────────┐                    │
  │         ▼           ▼              ▼                    │
  │       deny         ask           allow                  │
  │       403          200            200                   │
  │                 ┌──────┐      ┌───────┐                 │
  │                 │Appro-│      │Execute│                 │
  │                 │val   │      │adapter│                 │
  │                 │Record│      └───┬───┘                 │
  │                 └──┬───┘          │                     │
  │          ApprovalStore            │── result            │
  └────────────────────┼──────────────┼─────────────────────┘
                       ▼              ▼
              POST /approvals/{id}  External Systems
              (reviewer decides)    (email · HTTP · filesystem)
```

**Approval path:**  When verdict is `ask`, an `ApprovalRecord` is stored
(`.data/approvals/`) and an `approval_id` returned.  A reviewer posts to
`POST /approvals/{id}` to approve (execute) or reject.  Both outcomes
produce a trace entry with the reviewer identity and original verdict.

**Trace persistence:**  Every evaluation writes to `.data/traces.jsonl`.
Traces carry the `policy_version` active at decision time.  All data
survives process restarts.

**Policy versioning:**  Every distinct policy content fingerprint is
recorded in `.data/policy_history.jsonl`.  `GET /policy/history` returns
the version timeline.  Historical traces remain linked to the version that
produced them.

---

## The Tool Hub Concept

Without a gateway, an agent calls tools directly. There is no centralized point
where policy is enforced, traces are recorded, or provenance is checked.

```
Agent ──────── send_email()    ← no control
Agent ──────── http_post()     ← no control
Agent ──────── read_file()     ← no control
```

With the gateway, every tool call passes through a single enforcement point:

```
Agent
 ↓  POST /tools/execute
Tool Gateway
 ↓  PolicyEngine + ProvenanceFirewall
Provenance Firewall
 ↓  allow / deny / ask
Tool Adapter
 ↓
External System  (email · HTTP · filesystem)
```

This is the **execution switch**: a hub through which all agent tool calls must
pass, where access policy is evaluated deterministically.

---

## Full Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Agent / Client                            │
│        POST /tools/execute  {tool, arguments: {arg: ArgSpec}}    │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Tool Gateway                             │
│                    (gateway_server.py)                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    ExecutionRouter                         │  │
│  │                  (execution_router.py)                     │  │
│  │                                                            │  │
│  │  1. Look up tool in ToolRegistry                           │  │
│  │  2. Convert ArgSpec → ValueRef (with provenance labels)    │  │
│  │  3. Build ToolCall(tool, args: dict[str, ValueRef])        │  │
│  │                                                            │  │
│  │  4. PolicyEngine.evaluate(call, registry)                  │  │◄── hot-reloadable YAML
│  │     declarative rules: allow / deny / ask                  │  │
│  │                                                            │  │
│  │  5. ProvenanceFirewall.check(call, registry)               │  │◄── structural rules
│  │     RULE-01–05: structural provenance checks               │  │    (task manifest)
│  │                                                            │  │
│  │  6. Combine: deny > ask > allow                            │  │
│  │                                                            │  │
│  │  7. Write TraceEntry (always, regardless of verdict)       │  │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│         ┌─────────────┼───────────────┐                          │
│         ▼             ▼               ▼                          │
│       deny           ask            allow                        │
│       403           200             200                          │
│                  approval_         execute                       │
│                  required         adapter                        │
└──────────────────────────────────────────────────────────────────┘
                                  │ allow
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Tool Registry                             │
│                      (tool_registry.py)                          │
│                                                                  │
│    send_email  ──►  _adapter_send_email()   (simulated SMTP)     │
│    http_post   ──►  _adapter_http_post()    (simulated HTTP)     │
│    read_file   ──►  _adapter_read_file()    (filesystem read)    │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
                         External Systems
                   (email · HTTP API · filesystem)
```

---

## Provenance-Based Decisions

Every request argument carries a provenance label:

| `source` field    | ProvenanceClass     | Trust level |
|-------------------|---------------------|-------------|
| `external_document` | External content  | Untrusted   |
| `derived`         | Computed from parents | Inherited |
| `user_declared`   | Operator-declared  | Trusted     |
| `system`          | Gateway internals  | Trusted     |

The gateway converts these labels into `ValueRef` objects and passes them to
the enforcement engines. The enforcement engines walk the full derivation chain
— not just the immediate label — so provenance laundering is detected.

**Example: malicious email request blocked**

Request:
```json
{
  "tool": "send_email",
  "arguments": {
    "to": {
      "value": "attacker@evil.com",
      "source": "external_document",
      "label": "malicious_doc.txt"
    }
  }
}
```

Firewall evaluation:
```
to = "attacker@evil.com"
  provenance: external_document:malicious_doc.txt
  chain contains external_document → RULE-01 fires
verdict: deny
```

Response:
```json
{
  "verdict": "deny",
  "reason": "Recipient provenance traces to external_document — external documents cannot authorize outbound email",
  "matched_rule": "firewall:RULE-01",
  "policy_version": "a3f9c1b2",
  "trace_id": "7e4d1a9f"
}
```

**Example: clean email request requiring confirmation**

Request:
```json
{
  "tool": "send_email",
  "arguments": {
    "to": {
      "value": "alice@company.com",
      "source": "user_declared",
      "role": "recipient_source"
    }
  }
}
```

Firewall evaluation:
```
to = "alice@company.com"
  provenance: user_declared:gateway_trusted
  chain has user_declared with recipient_source role
  require_confirmation = true → RULE-05 → ask
verdict: ask
```

Response:
```json
{
  "verdict": "ask",
  "reason": "Recipient 'alice@company.com' traces to declared source 'gateway_trusted' — confirmation required",
  "matched_rule": "firewall:ask",
  "policy_version": "a3f9c1b2",
  "trace_id": "8b2c4f10"
}
```

---

## Persistence Layer

Gateway decisions survive process restarts.  Three durable stores back
the three kinds of mutable state:

```
.data/
├── traces.jsonl              ← append-only evaluation log (JSONL)
├── policy_history.jsonl      ← append-only version history (JSONL)
└── approvals/
    ├── {approval_id}.json    ← one JSON file per approval record
    └── …
```

**TraceStore** — appends one JSON line per evaluation.  `GET /traces`
reads from the file, so traces are available after restart.

**ApprovalStore** — one JSON file per approval.  On startup, pending
approvals are loaded back into memory so they can be resolved normally.

**PolicyStore** — appends one JSON line per distinct policy version.
Content-hash deduplication prevents duplicate entries on restart.

See [docs/audit_model.md](audit_model.md) for the complete field-level
specification and example records.

---

## Policy Hot Reload and Version History

The PolicyEngine loads rules from a YAML file at startup. Every distinct
policy content fingerprint is recorded in `PolicyStore`.

To update the policy without restarting:

1. Edit `policies/default_policy.yaml`
2. `POST /policy/reload`
3. New rules apply immediately to all subsequent requests

The `POST /policy/reload` response includes a `changed` flag:
```json
{
  "status": "reloaded",
  "policy_version": "b4d7e29a",
  "changed": true,
  "rule_count": 6,
  "policy_file": "policies/default_policy.yaml",
  "timestamp": "2026-03-15T12:34:56+00:00"
}
```

`changed: false` means the file content was identical to the last
recorded version — no new version entry was created.

**Version history** is available at `GET /policy/history`:
```json
{
  "current_version": "b4d7e29a",
  "history": [
    {
      "version_id": "b4d7e29a",
      "timestamp": "2026-03-15T12:34:56+00:00",
      "policy_file": "policies/default_policy.yaml",
      "content_hash": "b4d7e29a…",
      "rule_count": 6
    },
    {
      "version_id": "deadbeef",
      "timestamp": "2026-03-15T10:00:00+00:00",
      "rule_count": 4
    }
  ]
}
```

**Policy version is included in every trace entry**, so you can correlate
each decision with the exact policy that was active when it was made:

```bash
jq 'select(.policy_version == "deadbeef")' .data/traces.jsonl
```

**Demo: policy change changes behavior**

Start with the default policy (`deny-email-external-recipient` rule).
A malicious request is denied.

Edit the policy to remove the deny rule. Reload:
```
POST /policy/reload
```

The same malicious request now reaches the ProvenanceFirewall. RULE-01 still
fires (structural rule, not hot-reloadable). This demonstrates that the
PolicyEngine and ProvenanceFirewall are complementary layers — policy reload
changes the declarative rules but not the structural invariants.

---

## Trace Auditing

Every tool execution attempt is recorded to a **persistent JSONL log**,
regardless of verdict. Traces survive process restarts. Available at
`GET /traces`.

Example trace entry:
```json
{
  "trace_id": "7e4d1a9f",
  "timestamp": "2024-01-15T12:34:56.123456+00:00",
  "tool": "send_email",
  "call_id": "gw-7e4d1a9f",
  "policy_engine_verdict": "deny",
  "firewall_verdict": "deny",
  "final_verdict": "deny",
  "reason": "Recipient provenance traces to external_document",
  "matched_rule": "deny-email-external-recipient",
  "policy_version": "a3f9c1b2",
  "arg_provenance": {
    "to": "external_document:malicious_doc.txt",
    "subject": "system:system",
    "body": "system:system"
  },
  "result_summary": null
}
```

Trace fields:
- `policy_engine_verdict` — what the declarative rules said
- `firewall_verdict` — what the structural firewall said
- `final_verdict` — the winning verdict (deny > ask > allow)
- `arg_provenance` — full provenance chain for each argument
- `matched_rule` — the specific rule that determined the final verdict
- `approval_id` — set when this trace is part of an approval flow
- `approval_status` — pending | approved | rejected | executed
- `approved_by` — actor who resolved the approval
- `original_verdict` — the pre-resolution verdict (ask) when final differs

Traces provide a complete audit trail for security review, incident response,
and policy tuning. See [docs/integrations.md](integrations.md) for approval
trace examples.

---

## Approval Workflow

When verdict is `ask`, the tool is not executed. A pending `ApprovalRecord`
is created and the `approval_id` is returned to the caller.

```
POST /tools/execute → verdict=ask, approval_id=X
     │
     ├── GET  /approvals             (reviewer inspects all pending)
     ├── GET  /approvals/{X}         (reviewer fetches one record)
     └── POST /approvals/{X}         (reviewer decides)
              │
              ├── {approved: true}   → tool executed → verdict=allow
              └── {approved: false}  → denied         → verdict=deny
```

Both outcomes produce a new trace entry with `original_verdict=ask` and the
reviewer's identity (`approved_by`). The approval record transitions:

```
pending → approved → executed   (happy path)
pending → rejected              (reviewer declines)
```

A resolved approval returns 409 Conflict if resolved again.

---

## HTTP API Reference

### `GET /`
Gateway status, registered tools, and current policy version.

### `POST /tools/list`
List all registered tools with name, description, and side_effect_class.

### `POST /tools/execute`
Execute a tool with provenance-based access control.

**Request:**
```json
{
  "tool": "send_email",
  "arguments": {
    "<arg_name>": {
      "value": "<arg_value>",
      "source": "external_document | derived | user_declared | system",
      "parents": ["<parent_arg_name>"],
      "role": "<optional_role>",
      "label": "<human-readable origin>"
    }
  },
  "call_id": "<optional_client_id>",
  "provenance": {"session_id": "..."}
}
```

**Response:**
```json
{
  "verdict": "allow | deny | ask",
  "reason": "<explanation>",
  "matched_rule": "<rule_id>",
  "policy_version": "<hash>",
  "trace_id": "<id>",
  "result": "<tool_output_or_null>",
  "approval_id": "<id_when_ask>",
  "approval_required": false
}
```

HTTP status: 200 for allow/ask, 403 for deny.

### `POST /policy/reload`
Hot-reload policy rules from disk.  Records a new policy version if content changed.
Returns `{status, policy_version, changed, rule_count, policy_file, timestamp}`.

### `GET /policy/history?limit=N`
Return policy version history, newest first.
Returns `{current_version, history: [{version_id, timestamp, policy_file, content_hash, rule_count}]}`.

### `GET /traces?limit=N`
Return up to N recent trace entries (newest first, default 50, max 500).

### `GET /approvals?status=pending&limit=N`
Return approval records filtered by status.

### `GET /approvals/{approval_id}`
Return one approval record. Returns 404 if not found.

### `POST /approvals/{approval_id}`
Resolve a pending approval.

**Request:** `{"approved": true, "actor": "alice-reviewer"}`

Returns the tool result (if approved) or a deny response (if rejected).
Returns 404 if not found, 409 if already resolved.

---

## Running the Gateway

```bash
# Start with default config
python scripts/run_gateway.py

# Start with custom config
python scripts/run_gateway.py --config gateway_config.yaml

# Override port
python scripts/run_gateway.py --port 9000
```

The gateway listens on `http://127.0.0.1:8080` by default.

---

## Component Map

```
src/agent_hypervisor/gateway/
  __init__.py           package entry point
  config_loader.py      GatewayConfig, StorageConfig, load_config()
  tool_registry.py      ToolDefinition, ToolRegistry, built-in adapters
  execution_router.py   ExecutionRouter — enforcement pipeline, approval store
                        ApprovalRecord, TraceEntry (approval lifecycle fields)
  gateway_server.py     FastAPI app — all HTTP endpoints

src/agent_hypervisor/
  gateway_client.py     GatewayClient — Python HTTP client (stdlib only)
  storage/
    __init__.py         TraceStore, ApprovalStore, PolicyStore exports
    trace_store.py      Append-only JSONL trace log
    approval_store.py   Per-file JSON approval store
    policy_store.py     Append-only JSONL policy version history

gateway_config.yaml     root-level configuration (includes storage: section)
scripts/run_gateway.py  CLI entrypoint

examples/integrations/
  langchain_gateway_example.py   framework-agnostic integration demo
  approval_flow_example.py       full approval workflow demo
  mcp_gateway_adapter_example.py MCP JSON-RPC adapter shim

docs/
  gateway_architecture.md  this file
  audit_model.md           trace / approval / policy version field reference
  integrations.md          GatewayClient, MCP adapter, integration patterns
```
